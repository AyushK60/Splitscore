"""API tests.

These exercise the real application over HTTP, including the demo journey, the
structured error envelope, the documented limits and the export endpoints.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from .conftest import rows_to_csv


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


def _upload(client, payload: bytes, filename: str = "data.csv"):
    return client.post(
        "/api/datasets",
        files={"file": (filename, io.BytesIO(payload), "text/csv")},
    )


def _split_rows(count: int = 30) -> bytes:
    rows = []
    for index in range(count):
        rows.append(
            {
                "customer_id": f"C-{index % 6}",
                "amount": str(index * 3),
                "label": "1" if index % 2 else "0",
                "split": "train" if index % 3 else "test",
            }
        )
    return rows_to_csv(rows)


# --------------------------------------------------------------------------- #
# Meta endpoints
# --------------------------------------------------------------------------- #


def test_health_reports_versions_limits_and_storage_note(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["app_name"] == "SplitScope"
    assert body["app_version"]
    assert body["audit_schema_version"]
    assert body["limits"]["max_rows"] == 10_000
    assert body["limits"]["max_columns"] == 100
    assert body["limits"]["near_duplicate_max_combined_rows"] == 500
    assert "memory only" in body["storage_note"]
    assert body["store"]["limits"]["ttl_seconds"] > 0


def test_checks_endpoint_serves_the_real_catalogue(client):
    body = client.get("/api/checks").json()
    ids = [check["rule_id"] for check in body["checks"]]
    # The five original checks keep their ids and order; the integrity integrity
    # capabilities follow as separate typed rules.
    assert ids == [
        "SS-DUP-001",
        "SS-ENT-001",
        "SS-CHR-001",
        "SS-TGT-001",
        "SS-NEAR-001",
        "SS-AVL-001",
        "SS-TGT-002",
        "SS-ENT-002",
        "SS-CHR-002",
        "SS-PPF-001",
        "SS-VRU-001",
    ]
    assert sum(1 for check in body["checks"] if check["default_enabled"]) == 10
    assert body["what_this_app_does_not_do"]
    assert "must not be read as passing" in body["no_findings_means"]


def test_demos_endpoint_lists_every_demo_with_a_manifest_entry(client):
    body = client.get("/api/demos").json()
    ids = [demo["demo_id"] for demo in body["demos"]]
    assert ids == [
        "repeated_entity",
        "exact_duplicates",
        "chronology_violation",
        "target_copy",
        "near_duplicates",
        "clean_control",
        "causal_effect",
    ]
    for demo in body["demos"]:
        assert demo["synthetic"] is True
        assert demo["file_present"] is True
        assert len(demo["sha256"]) == 64
        assert demo["row_count"] > 0
        assert demo["expected_findings"]
    assert body["featured_journey"]["demo_id"] == "repeated_entity"


# --------------------------------------------------------------------------- #
# Loading and previewing
# --------------------------------------------------------------------------- #


def test_loading_a_demo_returns_roles_validated_against_it(client, loaded_demo):
    assert loaded_demo["dataset"]["source"] == "demo"
    assert loaded_demo["dataset"]["is_synthetic"] is True
    assert loaded_demo["suggested_roles_confidence"] == "recommended"
    assert loaded_demo["validation"]["ok"] is True
    assert loaded_demo["recommended_audit_config"] is not None
    assert loaded_demo["demo"]["planted_cases"]


def test_dataset_detail_and_preview(client, loaded_demo):
    dataset_id = loaded_demo["dataset"]["dataset_id"]
    detail = client.get(f"/api/datasets/{dataset_id}").json()
    assert detail["dataset"]["row_count"] == 240
    assert detail["column_types"]["customer_id"]["distinct_values"] == 40

    preview = client.get(f"/api/datasets/{dataset_id}/preview?offset=5&limit=2").json()
    assert preview["total_rows"] == 240
    assert preview["row_ids"] == ["row-000006", "row-000007"]
    assert len(preview["rows"]) == 2
    assert len(preview["rows"][0]) == len(preview["columns"])


def test_upload_round_trip_and_role_suggestions(client):
    response = _upload(client, _split_rows())
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["dataset"]["source"] == "upload"
    assert body["dataset"]["is_synthetic"] is False
    assert body["dataset"]["row_count"] == 30
    assert body["suggested_roles"]["split"] == "split"
    assert body["suggested_roles"]["target"] == "label"
    assert body["suggested_roles"]["entity"] == "customer_id"
    assert "amount" in body["suggested_roles"]["features"]
    assert body["role_suggestions"]["reasons"]["split"]


def test_role_validation_endpoint_reports_specific_codes(client, loaded_demo):
    dataset_id = loaded_demo["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/roles/validate",
        json={"roles": {"features": ["customer_id", "missing_col"], "split": "split"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    codes = {issue["code"] for issue in body["issues"]}
    assert "unknown_column" in codes


# --------------------------------------------------------------------------- #
# Audit and comparison
# --------------------------------------------------------------------------- #


def test_audit_endpoint_returns_engine_findings_and_a_run_id(client, loaded_demo):
    response = client.post(
        "/api/audit",
        json={
            "dataset_id": loaded_demo["dataset"]["dataset_id"],
            "roles": loaded_demo["suggested_roles"],
            "config": loaded_demo["recommended_audit_config"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"].startswith("run-")

    result = body["result"]
    assert result["findings"][0]["rule_id"] == "SS-ENT-001"
    assert result["findings"][0]["severity"] == "high"
    assert result["findings"][0]["examples"]
    # The planted entity-overlap finding leads; the total always equals the
    # finding list length (integrity screens may add info-level candidates).
    assert result["findings"][0]["rule_id"] == "SS-ENT-001"
    assert result["evaluation"]["findings_total"] == len(result["findings"])
    # SS-VRU-001 evaluates against the (empty) session history the API supplies;
    # an empty history is a real observation, not a missing one.
    assert {check["rule_id"] for check in result["evaluation"]["not_evaluated"]} == {
        "SS-CHR-001",
        "SS-NEAR-001",
        "SS-AVL-001",
        "SS-CHR-002",
        "SS-PPF-001",
    }
    assert result["diagnostics"]["counts"]["total_rows"] == 240


def test_audit_rejects_a_role_assignment_that_cannot_run(client, loaded_demo):
    response = client.post(
        "/api/audit",
        json={
            "dataset_id": loaded_demo["dataset"]["dataset_id"],
            "roles": {"features": [], "target": None, "entity": None, "timestamp": None, "split": "split"},
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    codes = {issue["code"] for issue in body["error"]["details"]["issues"]}
    assert "no_analysis_roles" in codes


def test_audit_config_is_validated_by_the_api(client, loaded_demo):
    response = client.post(
        "/api/audit",
        json={
            "dataset_id": loaded_demo["dataset"]["dataset_id"],
            "roles": loaded_demo["suggested_roles"],
            "config": {"max_examples": 0},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_comparison_marks_unsupported_strategies_and_offers_csv_downloads(client, loaded_demo):
    response = client.post(
        "/api/splits/compare",
        json={
            "dataset_id": loaded_demo["dataset"]["dataset_id"],
            "roles": loaded_demo["suggested_roles"],
            "config": loaded_demo["recommended_audit_config"],
            "strategies": [
                {"kind": "group", "label": "Group holdout", "test_fraction": 0.25, "seed": 12345},
                {"kind": "random", "label": "Random holdout", "test_fraction": 0.25, "seed": 12345},
                {"kind": "chronological", "label": "Chronological", "test_fraction": 0.25, "seed": 1},
            ],
            "include_existing_split": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    rows = {row["strategy_id"]: row for row in body["result"]["rows"]}

    assert rows["existing"]["supported"] is True
    assert rows["existing"]["entity_overlap_test_share"] == 1.0
    assert rows["group-1"]["entity_shared_groups"] == 0
    assert rows["chronological-3"]["supported"] is False
    assert "timestamp" in rows["chronological-3"]["unsupported_reason"]
    assert "spreadsheet formula injection" in body["sanitization_note"]
    assert "unaffected" in body["sanitization_note"]
    assert "no universally best split" in body["selection_note"].lower()

    group_handle = next(item for item in body["assignments"] if item["strategy_id"] == "group-1")
    assert group_handle["kind"] == "group"

    download = client.get(group_handle["download_path"])
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    assert "attachment" in download.headers["content-disposition"]
    assert "prevent spreadsheet formula injection" in download.headers["x-splitscope-export-note"]
    lines = download.text.splitlines()
    assert lines[1].startswith("row_id,split,")
    data_rows = [line for line in lines[2:] if line.strip()]
    assert len(data_rows) == 240  # every row of the dataset is assigned exactly once
    assert sum(1 for line in data_rows if ",train," in line) + sum(
        1 for line in data_rows if ",test," in line
    ) == 240
    assert group_handle["train_rows"] + group_handle["test_rows"] == 240


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


def test_json_and_html_reports_are_downloadable(client, loaded_demo):
    audit = client.post(
        "/api/audit",
        json={
            "dataset_id": loaded_demo["dataset"]["dataset_id"],
            "roles": loaded_demo["suggested_roles"],
            "config": loaded_demo["recommended_audit_config"],
        },
    ).json()

    json_report = client.post("/api/reports/json", json={"run_id": audit["run_id"]})
    assert json_report.status_code == 200
    assert json_report.headers["content-type"].startswith("application/json")
    payload = json.loads(json_report.text)
    assert payload["report_kind"] == "audit"
    assert payload["input"]["synthetic"] is True
    assert payload["findings"][0]["rule_id"] == "SS-ENT-001"
    assert ".json" in json_report.headers["content-disposition"]

    html_report = client.post("/api/reports/html", json={"run_id": audit["run_id"]})
    assert html_report.status_code == 200
    assert html_report.headers["content-type"].startswith("text/html")
    assert "SplitScope audit" in html_report.text
    assert ".html" in html_report.headers["content-disposition"]

    comparison = client.post(
        "/api/splits/compare",
        json={
            "dataset_id": loaded_demo["dataset"]["dataset_id"],
            "roles": loaded_demo["suggested_roles"],
            "config": loaded_demo["recommended_audit_config"],
            "strategies": [{"kind": "group", "label": "Group", "test_fraction": 0.25, "seed": 1}],
        },
    ).json()
    comparison_html = client.post("/api/reports/html", json={"run_id": comparison["run_id"]})
    assert comparison_html.status_code == 200
    assert "SplitScope split comparison" in comparison_html.text


def test_runs_endpoint_lists_stored_runs(client, loaded_demo):
    client.post(
        "/api/audit",
        json={
            "dataset_id": loaded_demo["dataset"]["dataset_id"],
            "roles": loaded_demo["suggested_roles"],
            "config": loaded_demo["recommended_audit_config"],
        },
    )
    body = client.get("/api/runs").json()
    assert len(body["runs"]) == 1
    assert body["runs"][0]["kind"] == "audit"
    assert body["store"]["runs"] == 1


# --------------------------------------------------------------------------- #
# Errors and limits
# --------------------------------------------------------------------------- #


def test_unknown_dataset_returns_a_410_with_an_explanation(client):
    response = client.post(
        "/api/audit",
        json={"dataset_id": "ds-does-not-exist", "roles": {"features": ["a"]}},
    )
    assert response.status_code == 410
    body = response.json()
    assert body["error"]["code"] == "expired_or_evicted"
    assert "restarted" in body["error"]["message"] or "expired" in body["error"]["message"]
    assert body["error"]["details"]["fix"]


def test_unknown_run_returns_a_410(client):
    response = client.post("/api/reports/json", json={"run_id": "run-nope"})
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "expired_or_evicted"


def test_malformed_json_body_returns_the_structured_envelope(client):
    response = client.post(
        "/api/audit",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["problems"]


def test_unsupported_file_type_is_rejected_before_reading(client):
    response = _upload(client, b"anything", filename="book.xlsx")
    assert response.status_code == 415
    body = response.json()
    assert body["error"]["code"] == "unsupported_input"
    assert any("Excel" in item for item in body["error"]["details"]["not_supported"])


def test_duplicate_headers_are_rejected_with_the_names(client):
    response = _upload(client, b"a,b,a\n1,2,3\n")
    assert response.status_code == 422
    assert response.json()["error"]["details"]["duplicate_columns"] == ["a"]


@pytest.fixture()
def row_limited_client(monkeypatch):
    """A client whose configured row limit is 10, to exercise the rejection path."""
    from app.api.deps import reset_context
    from app.core.config import reset_settings_cache
    from app.main import create_app

    monkeypatch.setenv("SPLITSCOPE_MAX_ROWS", "10")
    reset_settings_cache()
    reset_context()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        # Restore the environment before rebuilding the caches. monkeypatch's own
        # teardown runs *after* this fixture, so resetting the caches here alone
        # would rebuild them from the still-set SPLITSCOPE_MAX_ROWS and leave every
        # later test in the session with a 10-row limit.
        monkeypatch.undo()
        reset_settings_cache()
        reset_context()


def test_oversized_row_count_is_rejected_not_truncated(row_limited_client):
    response = _upload(row_limited_client, _split_rows(40))
    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "limit_exceeded"
    assert body["error"]["details"] == {"rows_found": 40, "rows_allowed": 10}


def test_the_documented_row_limit_is_reported_by_health(row_limited_client):
    assert row_limited_client.get("/api/health").json()["limits"]["max_rows"] == 10


def test_row_limit_settings_do_not_leak_into_later_tests(client):
    """Regression: ``row_limited_client`` used to rebuild the settings cache while
    ``SPLITSCOPE_MAX_ROWS=10`` was still exported, so every test after it in the
    session ran with a 10-row limit (visible only to tests that load a larger demo
    over HTTP, such as the live journey script)."""
    from app.core.config import get_settings

    assert get_settings().upload.max_rows == 10_000
    assert client.get("/api/health").json()["limits"]["max_rows"] == 10_000


def test_unknown_route_returns_the_structured_envelope(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_cors_is_restricted_to_documented_origins(client):
    allowed = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    denied = client.options(
        "/api/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert denied.headers.get("access-control-allow-origin") is None


def test_openapi_document_is_served(client):
    body = client.get("/api/openapi.json").json()
    assert body["info"]["title"].startswith("SplitScope")
    assert "/api/audit" in body["paths"]
    assert "/api/splits/compare" in body["paths"]
