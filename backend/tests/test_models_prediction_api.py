"""Route-level regression tests for the predictive endpoint.

These exercise the real HTTP surface: a demo can be admitted and predicted on
without first visiting the Study screen, and the endpoint must return a stored
run rather than an unhandled exception.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app


def test_prediction_route_seeds_demo_study_and_returns_a_run() -> None:
    with TestClient(create_app()) as client:
        loaded = client.post("/api/demos/clean_control/load")
        assert loaded.status_code == 200, loaded.text
        dataset_id = loaded.json()["dataset"]["dataset_id"]

        response = client.post(
            f"/api/datasets/{dataset_id}/models/prediction",
            json={
                "task": "classification",
                "outcome": "label",
                "predictors": ["x1", "x2", "x3", "segment"],
                "positive_level": "1",
                "split_source": "existing",
                "split_strategy": "stratified",
                "test_fraction": 0.25,
                "seed": 12345,
                "validation_fraction": 0.2,
                "models": ["baseline", "logistic"],
                "subgroup_column": "segment",
                "subgroup_bins": [],
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["kind"] == "prediction_model"
        assert payload["split"]["source"] == "existing"
        assert payload["split"]["summary"]["split_column"] == "split"
        assert payload["split"]["summary"]["train_value"] == "train"
        assert payload["specification"]["test_evaluations"] == 1
        assert payload["evaluation"]["n"] == payload["split"]["partitions"]["test"] == 60
        assert sum(sum(row) for row in payload["evaluation"]["metrics"]["confusion_matrix"]) == 60
        assert payload["run_id"].startswith("run-")

        stored = client.get(f"/api/models/runs/{payload['run_id']}")
        assert stored.status_code == 200, stored.text
        assert stored.json()["run_id"] == payload["run_id"]

        # The export is strict JSON: no NaN or infinity may hide in a metric,
        # curve threshold or provenance field.
        json.dumps(payload, allow_nan=False)
        exported = client.get(f"/api/models/runs/{payload['run_id']}/export")
        assert exported.status_code == 200, exported.text
        assert exported.headers["content-type"].startswith("application/json")
        assert json.loads(exported.text)["run_id"] == payload["run_id"]
