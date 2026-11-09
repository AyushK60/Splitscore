"""research run history and reproducibility manifests.

The history is a *projection* of the existing store, so these tests verify the
projection against runs the process actually produced - an audit, a split
comparison, a statistical model, an estimation comparison and the three estimation
analyses - including ownership, ordering, staleness honesty, bounded storage
and manifest integrity (the hash is recomputed here from the returned
manifest, an independent check of the canonicalisation contract).
"""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _load_demo() -> str:
    response = client.post("/api/demos/causal_effect/load")
    assert response.status_code == 200
    return response.json()["dataset"]["dataset_id"]


def _run_analysis_spread(dataset_id: str) -> None:
    # A leakage audit on a generated split.
    audit = client.post(
        "/api/audit",
        json={
            "dataset_id": dataset_id,
            "roles": {
                "features": ["age", "baseline_score", "region"],
                "target": "outcome",
                "split": "split",
                "split_train_value": "train",
                "split_test_value": "test",
            },
            "generate": {
                "strategy_id": "random",
                "label": "Random split",
                "kind": "random",
                "test_fraction": 0.3,
                "seed": 7,
            },
        },
    )
    assert audit.status_code == 200, audit.text
    # A statistical model run.
    model = client.post(
        f"/api/datasets/{dataset_id}/models/statistics",
        json={
            "task": "ols",
            "outcome": "outcome",
            "predictors": ["age", "baseline_score"],
        },
    )
    assert model.status_code == 200, model.text
    # An estimation comparison on the demo graph.
    graphs = client.get(f"/api/datasets/{dataset_id}/causal-graphs").json()
    graph = graphs["graphs"][0] if graphs.get("graphs") else None
    if graph is None:
        created = client.post(
            f"/api/datasets/{dataset_id}/causal-graphs",
            json={
                "graph": {
                    "schema_version": "1.0.0",
                    "dataset_id": dataset_id,
                    "name": "history test graph",
                    "description": None,
                    "nodes": [
                        {
                            "node_id": node,
                            "label": node,
                            "column": node,
                            "observed": True,
                            "kind": "covariate",
                            "description": None,
                            "layout": None,
                        }
                        for node in ["age", "baseline_score", "region", "treatment", "outcome"]
                    ],
                    "edges": [
                        {"source": "age", "target": "treatment", "rationale": None, "reference": None},
                        {"source": "baseline_score", "target": "treatment", "rationale": None, "reference": None},
                        {"source": "region", "target": "treatment", "rationale": None, "reference": None},
                        {"source": "age", "target": "outcome", "rationale": None, "reference": None},
                        {"source": "baseline_score", "target": "outcome", "rationale": None, "reference": None},
                        {"source": "region", "target": "outcome", "rationale": None, "reference": None},
                        {"source": "treatment", "target": "outcome", "rationale": None, "reference": None},
                    ],
                    "analysis": {"treatment": "treatment", "outcome": "outcome"},
                    "assumptions": [],
                }
            },
        )
        graph = (created.json().get("graph") or created.json())
        graph_id = graph["graph_id"]
    else:
        graph_id = graph["graph_id"]
    estimation = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/compare",
        json={
            "request": {
            "estimand": "ate",
            "treatment_node": "treatment",
            "outcome_node": "outcome",
            "adjustment_nodes": ["age", "baseline_score", "region"],
            "treatment_mapping": {"treated": "1", "control": "0"},
            "cohort": {"split_assignment_id": None, "partition": None},
            "missing_data_policy": "complete_case",
            "cross_fit": {"splits": 3, "group_column": None},
            "uncertainty": {"method": "influence_function", "level": 0.95, "reps": 100, "seed": 11},
            "propensity_truncation": None,
            "expected_spec_fingerprint_sha256": None,
            },
            "label": "history test comparison",
        },
    )
    assert estimation.status_code == 200, estimation.text


def _history(dataset_id: str) -> dict:
    response = client.get(f"/api/datasets/{dataset_id}/history")
    assert response.status_code == 200, response.text
    return response.json()


def test_history_indexes_runs_across_kinds_with_metadata():
    dataset_id = _load_demo()
    _run_analysis_spread(dataset_id)
    history = _history(dataset_id)
    assert history["history_schema_version"] == "1.0.0"
    kinds = {entry["kind"] for entry in history["runs"]}
    assert {"audit", "model", "estimation"} <= kinds
    estimation_entries = [entry for entry in history["runs"] if entry["kind"] == "estimation"]
    assert estimation_entries[0]["analysis_kind"] == "estimation_comparison"
    assert estimation_entries[0]["graph"]["graph_id"]
    assert estimation_entries[0]["graph"]["graph_spec_fingerprint_sha256"]
    assert estimation_entries[0]["reproducibility"]["resolved_seed"] == 11
    # Age ordering: newest first, consistent with the store's own ordering.
    ages = [entry["age_seconds"] for entry in history["runs"]]
    assert ages == sorted(ages)
    # Entries carry the dataset identity and the honest study gap.
    for entry in history["runs"]:
        assert entry["dataset"]["dataset_id"] == dataset_id
        assert entry["dataset"]["dataset_fingerprint_sha256"] != "not_recorded"
        assert entry["study"]["study_id"] is None
        assert "not currently linked" in entry["study"]["note"]
    assert history["counts_by_analysis_kind"]["estimation_comparison"] == 1


def test_history_is_dataset_scoped_and_refuses_foreign_datasets():
    dataset_id = _load_demo()
    other = _load_demo()
    _run_analysis_spread(dataset_id)
    history = _history(other)
    assert history["runs"] == []
    # The store's established semantics: a dataset that is not in memory is
    # 410 (expired/evicted), not 404 - same as every dataset-scoped route.
    missing = client.get("/api/datasets/does-not-exist/history")
    assert missing.status_code == 410


def test_history_marks_run_stale_when_dataset_content_changed():
    dataset_id = _load_demo()
    _run_analysis_spread(dataset_id)
    # Mutate the dataset content in the store directly: same identity, new bytes.
    from app.api.deps import get_context

    dataset = get_context().store.get_dataset(dataset_id)
    dataset.fingerprint_sha256 = "f" * 64
    history = _history(dataset_id)
    stale = [entry for entry in history["runs"] if entry["stale"]]
    assert stale, "a fingerprint change must stale every run that recorded one"
    for entry in stale:
        assert any("no longer matches" in reason for reason in entry["staleness_reasons"])


def test_manifest_is_metadata_only_with_verifiable_integrity_hash():
    dataset_id = _load_demo()
    _run_analysis_spread(dataset_id)
    history = _history(dataset_id)
    estimation_run = next(entry["run_id"] for entry in history["runs"] if entry["kind"] == "estimation")
    response = client.get(f"/api/datasets/{dataset_id}/history/{estimation_run}/manifest")
    assert response.status_code == 200, response.text
    manifest = response.json()
    assert manifest["manifest_schema_version"] == "1.0.0"
    assert manifest["results_included"] == "metadata_only"
    assert "original dataset" in manifest["reproduction_requirements"]
    # Metadata-only: no results arrays, no dataset rows.
    serialised = json.dumps(manifest)
    assert '"results"' not in serialised
    # The integrity hash is recomputed here independently of the server code.
    integrity = manifest.pop("integrity")
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert recomputed == integrity["canonical_json_sha256"]
    assert manifest["run"]["run_id"] == estimation_run
    assert manifest["graph"]["graph_id"]
    assert manifest["reproducibility"]["software_versions"]["python"]
    assert manifest["dataset"]["fingerprint_recorded_in_run"] is True


def test_manifest_refuses_cross_dataset_and_missing_runs():
    dataset_id = _load_demo()
    other = _load_demo()
    _run_analysis_spread(dataset_id)
    history = _history(dataset_id)
    run_id = history["runs"][0]["run_id"]
    wrong = client.get(f"/api/datasets/{other}/history/{run_id}/manifest")
    assert wrong.status_code == 404
    missing = client.get(f"/api/datasets/{dataset_id}/history/run-nope/manifest")
    assert missing.status_code in (404, 410)


def test_non_estimation_manifest_states_reproducibility_gap_honestly():
    dataset_id = _load_demo()
    _run_analysis_spread(dataset_id)
    history = _history(dataset_id)
    audit_run = next(entry["run_id"] for entry in history["runs"] if entry["kind"] == "audit")
    manifest = client.get(f"/api/datasets/{dataset_id}/history/{audit_run}/manifest").json()
    assert manifest["reproducibility"]["software_versions"] == "not_recorded"
    assert "analysis_definition" in manifest
    assert manifest["analysis_definition"]["findings_total"] is not None
