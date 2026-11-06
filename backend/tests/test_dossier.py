"""S7 dossier composition and export contracts.

These tests assert the report is assembled from the named stored runs, preserves
not-evaluated states, and cannot silently turn missing analyses into clean ones.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from app.reports.dossier import SECTION_IDS, build_dossier


@pytest.fixture()
def client():
    from app.api.deps import reset_context
    from app.main import create_app

    reset_context()
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def loaded_demo(client):
    response = client.post("/api/demos/repeated_entity/load")
    assert response.status_code == 200, response.text
    return response.json()


def _audit(client, loaded_demo):
    response = client.post(
        "/api/audit",
        json={
            "dataset_id": loaded_demo["dataset"]["dataset_id"],
            "roles": loaded_demo["suggested_roles"],
            "config": loaded_demo["recommended_audit_config"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _comparison(client, loaded_demo):
    response = client.post(
        "/api/splits/compare",
        json={
            "dataset_id": loaded_demo["dataset"]["dataset_id"],
            "roles": loaded_demo["suggested_roles"],
            "config": loaded_demo["recommended_audit_config"],
            "strategies": [
                {"kind": "group", "label": "Group holdout", "test_fraction": 0.25, "seed": 7},
                {"kind": "random", "label": "Random holdout", "test_fraction": 0.25, "seed": 7},
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _statistics(client, loaded_demo):
    response = client.post(
        f"/api/datasets/{loaded_demo['dataset']['dataset_id']}/models/statistics",
        json={
            "task": "ols",
            "outcome": "monthly_spend",
            "predictors": ["tenure_months", "support_tickets"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _prediction(client, loaded_demo):
    response = client.post(
        f"/api/datasets/{loaded_demo['dataset']['dataset_id']}/models/prediction",
        json={
            "task": "classification",
            "outcome": "churned",
            "predictors": [
                "tenure_months",
                "monthly_spend",
                "support_tickets",
                "avg_session_minutes",
            ],
            "positive_level": "yes",
            "split_source": "existing",
            "subgroup_column": "split",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _dossier(client, loaded_demo, **overrides):
    body = {
        "sections": list(SECTION_IDS),
        "audit_run_id": None,
        "comparison_run_id": None,
        "model_run_ids": [],
        **overrides,
    }
    response = client.post(
        f"/api/datasets/{loaded_demo['dataset']['dataset_id']}/reports/dossier",
        json=body,
    )
    return response


def test_complete_dossier_ties_every_section_to_stored_runs(client, loaded_demo):
    audit = _audit(client, loaded_demo)
    comparison = _comparison(client, loaded_demo)
    model = _statistics(client, loaded_demo)
    response = _dossier(
        client,
        loaded_demo,
        audit_run_id=audit["run_id"],
        comparison_run_id=comparison["run_id"],
        model_run_ids=[model["run_id"]],
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["report_kind"] == "dossier"
    assert body["schema_version"] == "1.1.0"  # S10-B: additive sections
    assert body["request"]["audit_run_id"] == audit["run_id"]
    assert body["request"]["comparison_run_id"] == comparison["run_id"]
    assert body["request"]["model_run_ids"] == [model["run_id"]]
    assert body["included_sections"] == list(SECTION_IDS)
    assert set(body["sections"]) == set(SECTION_IDS)

    # Counts and denominators are copied from the audit, not recomputed here.
    assert body["summary"]["findings_total"] == len(audit["result"]["findings"])
    assert body["summary"]["not_evaluated_count"] == len(audit["result"]["evaluation"]["not_evaluated"])
    assert body["summary"]["findings_by_severity"] == audit["result"]["evaluation"]["findings_by_severity"]
    assert body["summary"]["audit_headline"] == audit["result"]["evaluation"]["headline"]
    assert body["sections"]["audit"]["data"]["run_id"] == audit["run_id"]
    assert body["sections"]["findings"]["data"]["total"] == len(audit["result"]["findings"])
    assert body["sections"]["comparison"]["data"]["run_id"] == comparison["run_id"]
    assert body["sections"]["models"]["data"]["total"] == 1
    model_data = body["sections"]["models"]["data"]["runs"][0]
    assert model_data["run_id"] == model["run_id"]
    assert model_data["kind"] == "statistical_model"
    assert len(model_data["coefficients"]) == len(model["coefficients"])
    assert model_data["fit"]["r_squared"] == model["fit"]["r_squared"]
    assert (
        body["sections"]["reproducibility"]["data"]["dataset_sha256"]
        == (loaded_demo["dataset"]["fingerprint_sha256"])
    )
    assert body["integrity"]["raw_data_embedded"] is False
    assert body["integrity"]["row_predictions_embedded"] is False


def test_missing_runs_are_explicitly_unavailable_not_clean(client, loaded_demo):
    response = _dossier(client, loaded_demo)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["summary"]["audit_headline"] is None
    assert body["summary"]["findings_total"] == 0
    assert body["sections"]["audit"]["available"] is False
    assert body["sections"]["scorecard"]["available"] is False
    assert body["sections"]["findings"]["available"] is False
    assert body["sections"]["comparison"]["available"] is False
    assert body["sections"]["models"]["available"] is False
    assert "No audit run" in body["sections"]["audit"]["reason"]
    assert "No split comparison" in body["sections"]["comparison"]["reason"]
    assert "No model run" in body["sections"]["models"]["reason"]
    assert any("No audit run is included" in caution for caution in body["summary"]["cautions"])


def test_not_evaluated_checks_survive_into_limitations_and_summary(client, loaded_demo):
    audit = _audit(client, loaded_demo)
    body = _dossier(client, loaded_demo, audit_run_id=audit["run_id"]).json()
    not_evaluated = audit["result"]["evaluation"]["not_evaluated"]
    assert body["sections"]["limitations"]["data"]["not_evaluated"] == not_evaluated
    assert body["summary"]["not_evaluated_count"] == len(not_evaluated)
    assert any("not evaluated" in item.lower() for item in body["summary"]["cautions"])


def test_html_export_is_self_contained_printable_and_escaped(client, loaded_demo):
    audit = _audit(client, loaded_demo)
    response = client.post(
        f"/api/datasets/{loaded_demo['dataset']['dataset_id']}/reports/dossier?format=html",
        json={"sections": list(SECTION_IDS), "audit_run_id": audit["run_id"]},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert 'attachment; filename="splitscope-dossier-' in response.headers["content-disposition"]
    html = response.text
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "<script" not in html.lower()
    assert "@media print" in html
    assert "Evidence integrity" in html
    assert "not evaluated" in html.lower()
    assert loaded_demo["dataset"]["fingerprint_sha256"] in html
    assert "SS-ENT-001" in html
    # Severity badges are markup generated by the renderer; they must not be
    # escaped into visible `<span class=…>` text in the printable artifact.
    assert '<span class="badge high">high</span>' in html
    assert "&lt;span class=&quot;badge" not in html


def test_json_export_is_the_same_contract_and_downloadable(client, loaded_demo):
    audit = _audit(client, loaded_demo)
    response = client.post(
        f"/api/datasets/{loaded_demo['dataset']['dataset_id']}/reports/dossier?format=json",
        json={"sections": ["summary", "audit"], "audit_run_id": audit["run_id"]},
    )
    assert response.status_code == 200, response.text
    assert 'attachment; filename="splitscope-dossier-' in response.headers["content-disposition"]
    body = json.loads(response.text)
    assert body["included_sections"] == ["summary", "audit"]
    assert body["sections"]["summary"]["included"] is True
    assert body["sections"]["findings"]["included"] is False
    assert body["summary"]["findings_total"] == len(audit["result"]["findings"])


def test_section_selection_is_server_ordered_and_cannot_be_empty(client, loaded_demo):
    response = _dossier(client, loaded_demo, sections=["reproducibility", "summary", "study"])
    assert response.status_code == 200, response.text
    assert response.json()["included_sections"] == ["summary", "study", "reproducibility"]

    empty = _dossier(client, loaded_demo, sections=[])
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "validation_error"

    unknown = _dossier(client, loaded_demo, sections=["summary", "made_up"])
    assert unknown.status_code == 422
    assert "made_up" in unknown.json()["error"]["message"]


def test_wrong_run_kind_and_foreign_dataset_are_rejected(client, loaded_demo):
    audit = _audit(client, loaded_demo)
    wrong_kind = _dossier(client, loaded_demo, comparison_run_id=audit["run_id"])
    assert wrong_kind.status_code == 422
    assert "not a split comparison" in wrong_kind.json()["error"]["message"]

    rows = ["a,b,split"] + [f"{index},{index * 2},{'train' if index % 3 else 'test'}" for index in range(24)]
    other = client.post(
        "/api/datasets",
        files={
            "file": (
                "other.csv",
                io.BytesIO(("\n".join(rows) + "\n").encode()),
                "text/csv",
            )
        },
    )
    assert other.status_code == 201, other.text
    other_id = other.json()["dataset"]["dataset_id"]
    foreign = client.post(
        f"/api/datasets/{other_id}/reports/dossier",
        json={"sections": ["summary"], "audit_run_id": audit["run_id"]},
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "not_found"


def test_predictive_model_card_carries_metrics_and_subgroup_caveats(client, loaded_demo):
    audit = _audit(client, loaded_demo)
    prediction = _prediction(client, loaded_demo)
    response = _dossier(
        client,
        loaded_demo,
        audit_run_id=audit["run_id"],
        model_run_ids=[prediction["run_id"]],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    model = body["sections"]["models"]["data"]["runs"][0]

    assert model["run_id"] == prediction["run_id"]
    assert model["kind"] == "prediction_model"
    assert model["evaluation"]["n"] == prediction["evaluation"]["n"]
    assert model["evaluation"]["metrics"] == prediction["evaluation"]["metrics"]
    assert model["selected"]["label"] == prediction["selected"]["label"]
    assert model["split"]["source"] == "existing"
    assert model["subgroups"] is not None
    assert model["subgroups"]["note"] == prediction["subgroups"]["note"]
    assert len(model["subgroups"]["rows"]) == len(prediction["subgroups"]["rows"])
    assert "not causal" in model["note"].lower()

    html = client.post(
        f"/api/datasets/{loaded_demo['dataset']['dataset_id']}/reports/dossier?format=html",
        json={
            "sections": ["summary", "models"],
            "audit_run_id": audit["run_id"],
            "model_run_ids": [prediction["run_id"]],
        },
    ).text
    assert "predictive model" in html.lower()
    assert prediction["run_id"] in html
    assert "Held-out metrics" in html
    assert "Subgroups" in html


def test_html_escapes_hostile_study_title(client, loaded_demo):
    dataset_id = loaded_demo["dataset"]["dataset_id"]
    payload = client.get(f"/api/datasets/{dataset_id}/study").json()
    card = payload["card"]
    card["title"] = '<script>alert("dossier")</script>'
    save = client.put(
        f"/api/datasets/{dataset_id}/study",
        json={"card": card},
    )
    assert save.status_code == 200, save.text
    html = client.post(
        f"/api/datasets/{dataset_id}/reports/dossier?format=html",
        json={"sections": ["summary", "study"]},
    ).text
    assert "<script" not in html.lower()
    assert "&lt;script&gt;" in html


def test_build_dossier_is_deterministic_apart_from_generation_time(loaded_demo):
    # A direct builder check keeps the contract independent of HTTP storage.
    dataset = client_dataset(loaded_demo)
    first = build_dossier(
        dataset=dataset,
        study=None,
        profile=None,
        audit=None,
        comparison=None,
        models=[],
        requested_sections=["summary", "provenance"],
        generated_at_utc="2026-01-01T00:00:00+00:00",
    )
    second = build_dossier(
        dataset=dataset,
        study=None,
        profile=None,
        audit=None,
        comparison=None,
        models=[],
        requested_sections=["summary", "provenance"],
        generated_at_utc="2026-01-01T00:00:00+00:00",
    )
    assert first == second
    assert first["sections"]["provenance"]["data"]["dataset"]["row_count"] == 240


def client_dataset(loaded_demo):
    """A minimal stand-in with the identity fields the builder reads."""
    from dataclasses import dataclass
    from datetime import datetime

    @dataclass
    class Demo:
        demo_id: str

    @dataclass
    class FakeDataset:
        dataset_id: str
        name: str
        source: str
        is_synthetic: bool
        fingerprint_sha256: str
        row_count: int
        column_count: int
        created_at: datetime
        warnings: list[str]
        demo: Demo | None

    dataset = loaded_demo["dataset"]
    return FakeDataset(
        dataset_id=dataset["dataset_id"],
        name=dataset["name"],
        source=dataset["source"],
        is_synthetic=dataset["is_synthetic"],
        fingerprint_sha256=dataset["fingerprint_sha256"],
        row_count=dataset["row_count"],
        column_count=dataset["column_count"],
        created_at=datetime.fromisoformat(dataset["created_at_utc"]),
        warnings=dataset["warnings"],
        demo=Demo(demo_id=loaded_demo["demo"]["demo_id"]),
    )


__all__ = ["SECTION_IDS"]
