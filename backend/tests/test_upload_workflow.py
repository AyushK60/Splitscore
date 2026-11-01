"""Tests for the uploaded-dataset workflow.

A CSV with no split column used to be a dead end: the audit demanded a split
column and no UI path could create one. These tests pin the pieces that close
that gap: auditing a generated split through ``POST /api/audit``, reading the
observed values of a column for the train/test mapping step, and the layered
byte limits that decide whether an upload is admitted at all.

Every dataset here is written by hand as small CSV text; no file from a user's
machine is read by the suite.
"""

from __future__ import annotations

import io

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


def _upload(client, payload: bytes, filename: str = "data.csv"):
    return client.post(
        "/api/datasets",
        files={"file": (filename, io.BytesIO(payload), "text/csv")},
    )


def _wine_like_rows(count: int = 120) -> list[dict[str, str]]:
    """A miniature of the accepted wine-quality file: id, chemistry, quality.

    Same shape as the real file — a unique ``Id`` column, several numeric
    feature columns, an integer ``quality`` target, and no split, timestamp or
    entity column — at a size that keeps the suite fast.
    """
    rows = []
    for index in range(count):
        quality = 3 + index % 6  # six distinct grades, like the real file
        rows.append(
            {
                "Id": str(index + 1),
                "fixed acidity": f"{6 + (index % 5) * 0.4:.1f}",
                "volatile acidity": f"{0.2 + (index % 7) * 0.05:.2f}",
                "citric acid": f"{0.1 + (index % 3) * 0.1:.2f}",
                "residual sugar": f"{1.5 + (index % 4) * 0.3:.1f}",
                "chlorides": f"{0.05 + (index % 6) * 0.01:.2f}",
                "free sulfur dioxide": str(10 + index % 25),
                "total sulfur dioxide": str(30 + index % 60),
                "density": f"{0.99 + (index % 5) * 0.001:.3f}",
                "pH": f"{3.0 + (index % 4) * 0.1:.1f}",
                "sulphates": f"{0.5 + (index % 4) * 0.1:.1f}",
                "alcohol": f"{9 + (index % 5) * 0.5:.1f}",
                "quality": str(quality),
            }
        )
    return rows


def _no_split_roles(dataset_body) -> dict:
    """Roles for a file without a split column: everything but the split."""
    suggested = dataset_body["suggested_roles"]
    return {
        **suggested,
        "split": None,
        "split_train_value": None,
        "split_test_value": None,
    }


# --------------------------------------------------------------------------- #
# Audit of a generated split
# --------------------------------------------------------------------------- #


def test_audit_generates_a_random_split_when_the_file_has_no_split_column(client):
    upload = _upload(client, rows_to_csv(_wine_like_rows()))
    assert upload.status_code == 201, upload.text
    body = upload.json()
    dataset_id = body["dataset"]["dataset_id"]
    assert body["suggested_roles"]["split"] is None  # nothing in the file marks train/test

    response = client.post(
        "/api/audit",
        json={
            "dataset_id": dataset_id,
            "roles": _no_split_roles(body),
            "generate": {"kind": "random", "label": "Random holdout", "test_fraction": 0.25, "seed": 7},
        },
    )
    assert response.status_code == 200, response.text
    audit = response.json()
    summary = audit["result"]["split"]
    assert summary["kind"] == "random"
    assert summary["seed"] == 7
    assert summary["train_rows"] + summary["test_rows"] == 120
    assert summary["split_column"] is None

    assignment = audit["assignment"]
    assert assignment is not None
    assert assignment["strategy_id"] == "random"
    assert assignment["train_rows"] == summary["train_rows"]

    download = client.get(assignment["download_path"])
    assert download.status_code == 200
    data_rows = [line for line in download.text.splitlines()[2:] if line.strip()]
    assert len(data_rows) == 120  # every row assigned exactly once


def test_audit_of_a_generated_split_is_reproducible_for_the_same_seed(client):
    upload = _upload(client, rows_to_csv(_wine_like_rows()))
    dataset_id = upload.json()["dataset"]["dataset_id"]
    roles = _no_split_roles(upload.json())

    first = client.post(
        "/api/audit",
        json={
            "dataset_id": dataset_id,
            "roles": roles,
            "generate": {"kind": "random", "label": "Random holdout", "test_fraction": 0.2, "seed": 42},
        },
    )
    second = client.post(
        "/api/audit",
        json={
            "dataset_id": dataset_id,
            "roles": roles,
            "generate": {"kind": "random", "label": "Random holdout", "test_fraction": 0.2, "seed": 42},
        },
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["assignment"]["assignment_id"] == second.json()["assignment"]["assignment_id"]
    assert (
        first.json()["result"]["split"]["test_rows"] == second.json()["result"]["split"]["test_rows"]
    )


def test_audit_generated_split_downloads_every_row_exactly_once(client):
    upload = _upload(client, rows_to_csv(_wine_like_rows()))
    dataset_id = upload.json()["dataset"]["dataset_id"]
    response = client.post(
        "/api/audit",
        json={
            "dataset_id": dataset_id,
            "roles": _no_split_roles(upload.json()),
            "generate": {"kind": "random", "label": "Random holdout", "test_fraction": 0.25, "seed": 1},
        },
    )
    assert response.status_code == 200, response.text
    assignment = response.json()["assignment"]
    csv_text = client.get(assignment["download_path"]).text
    data_rows = [line for line in csv_text.splitlines()[2:] if line.strip()]
    assert len(data_rows) == 120
    train = sum(1 for line in data_rows if ",train," in line)
    test = sum(1 for line in data_rows if ",test," in line)
    assert train + test == 120
    assert (train, test) == (assignment["train_rows"], assignment["test_rows"])


def test_existing_is_not_a_generatable_strategy(client):
    upload = _upload(client, rows_to_csv(_wine_like_rows()))
    dataset_id = upload.json()["dataset"]["dataset_id"]
    response = client.post(
        "/api/audit",
        json={
            "dataset_id": dataset_id,
            "roles": _no_split_roles(upload.json()),
            "generate": {"kind": "existing", "label": "The split in the file"},
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] in {"validation_error", "infeasible_operation"}
    assert "existing" in body["error"]["message"].lower()


def test_audit_without_generate_still_requires_a_split_column(client):
    """The old behaviour is unchanged: no generate, no split column -> typed 422."""
    upload = _upload(client, rows_to_csv(_wine_like_rows()))
    body = upload.json()
    response = client.post(
        "/api/audit",
        json={"dataset_id": body["dataset"]["dataset_id"], "roles": _no_split_roles(body)},
    )
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "split column" in message.lower()


def test_stratified_generated_split_records_the_target(client):
    upload = _upload(client, rows_to_csv(_wine_like_rows()))
    body = upload.json()
    response = client.post(
        "/api/audit",
        json={
            "dataset_id": body["dataset"]["dataset_id"],
            "roles": _no_split_roles(body),
            "generate": {"kind": "stratified", "label": "Stratified by quality", "test_fraction": 0.25, "seed": 3},
        },
    )
    assert response.status_code == 200, response.text
    summary = response.json()["result"]["split"]
    assert summary["kind"] == "stratified"


def test_group_and_chronological_generated_splits_explain_what_is_missing(client):
    upload = _upload(client, rows_to_csv(_wine_like_rows()))
    body = upload.json()
    roles = _no_split_roles(body)

    group = client.post(
        "/api/audit",
        json={
            "dataset_id": body["dataset"]["dataset_id"],
            "roles": roles,
            "generate": {"kind": "group", "label": "Group holdout", "test_fraction": 0.25, "seed": 1},
        },
    )
    assert group.status_code == 409  # infeasible_operation, not a validation failure
    assert "entity" in group.json()["error"]["message"].lower()

    chrono = client.post(
        "/api/audit",
        json={
            "dataset_id": body["dataset"]["dataset_id"],
            "roles": roles,
            "generate": {"kind": "chronological", "label": "Chronological", "test_fraction": 0.25, "seed": 1},
        },
    )
    assert chrono.status_code == 409
    assert "timestamp" in chrono.json()["error"]["message"].lower()


# --------------------------------------------------------------------------- #
# Role suggestions for an uploaded file
# --------------------------------------------------------------------------- #


def test_wine_like_upload_suggests_quality_target_and_excludes_the_id_column(client):
    upload = _upload(client, rows_to_csv(_wine_like_rows()), filename="wine.csv")
    assert upload.status_code == 201, upload.text
    body = upload.json()
    suggested = body["suggested_roles"]

    assert suggested["target"] == "quality"
    assert suggested["split"] is None
    assert suggested["entity"] is None  # Id is unique per row, so it is not a group
    assert "Id" in suggested["metadata_excluded"]
    features = set(suggested["features"])
    assert "Id" not in features
    assert "quality" not in features
    assert len(features) == 11  # the eleven chemistry columns

    validation = body["validation"]
    assert validation["ok"] is True
    codes = {issue["code"] for issue in validation["issues"]}
    assert "role_overlap" not in codes
    assert "column_multi_role" not in codes


def test_role_suggestions_survive_a_reload_of_the_same_upload(client):
    """GET /datasets/{id} re-derives suggestions from the stored frame."""
    upload = _upload(client, rows_to_csv(_wine_like_rows()))
    dataset_id = upload.json()["dataset"]["dataset_id"]
    detail = client.get(f"/api/datasets/{dataset_id}").json()
    assert detail["suggested_roles"]["target"] == "quality"


# --------------------------------------------------------------------------- #
# Observed values for the train/test mapping step
# --------------------------------------------------------------------------- #


def _split_marked_rows(count: int = 40) -> bytes:
    rows = [
        {
            "customer_id": f"C-{index % 6}",
            "amount": str(index * 3),
            "label": "1" if index % 2 else "0",
            "split": "train" if index % 3 else "test",
        }
        for index in range(count)
    ]
    return rows_to_csv(rows)


def test_column_values_reports_observed_values_with_counts(client):
    upload = _upload(client, _split_marked_rows())
    dataset_id = upload.json()["dataset"]["dataset_id"]

    response = client.get(f"/api/datasets/{dataset_id}/column-values", params={"column": "split"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["column"] == "split"
    assert body["total_rows"] == 40
    counts = {item["value"]: item["count"] for item in body["values"]}
    assert counts == {"train": 26, "test": 14}
    assert body["truncated"] is False
    assert body["note"]


def test_column_values_reports_missing_cells_as_empty(client):
    rows = [{"a": "1", "b": ""}, {"a": "2", "b": "x"}, {"a": "3", "b": ""}]
    rows += [{"a": str(index), "b": "x"} for index in range(4, 25)]  # meet the min-row floor
    upload = _upload(client, rows_to_csv(rows))
    dataset_id = upload.json()["dataset"]["dataset_id"]

    body = client.get(f"/api/datasets/{dataset_id}/column-values", params={"column": "b"}).json()
    counts = {item["value"]: item["count"] for item in body["values"]}
    assert counts == {"x": 22, "": 2}
    assert body["missing_count"] == 2


def test_column_values_unknown_column_is_a_404_with_the_column_list(client):
    upload = _upload(client, _split_marked_rows())
    dataset_id = upload.json()["dataset"]["dataset_id"]
    response = client.get(f"/api/datasets/{dataset_id}/column-values", params={"column": "nope"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "split" in body["error"]["details"]["columns"]


def test_column_values_truncates_long_lists_with_a_flag(client):
    rows = [{"a": str(index % 5), "b": str(index)} for index in range(60)]
    upload = _upload(client, rows_to_csv(rows))
    dataset_id = upload.json()["dataset"]["dataset_id"]

    body = client.get(
        f"/api/datasets/{dataset_id}/column-values", params={"column": "b", "limit": 10}
    ).json()
    assert len(body["values"]) == 10
    assert body["truncated"] is True
    assert body["distinct_count"] == 60


# --------------------------------------------------------------------------- #
# Layered limits
# --------------------------------------------------------------------------- #


def test_health_reports_the_configured_byte_limits(client):
    limits = client.get("/api/health").json()["limits"]
    assert limits["max_upload_bytes"] == 25 * 1024 * 1024
    assert limits["max_upload_mb"] == 25.0
    assert limits["max_parsed_bytes"] == 256 * 1024 * 1024
    # Shape limits are independent of the byte limits.
    assert limits["max_rows"] == 10_000
    assert limits["max_columns"] == 100


def test_upload_larger_than_the_byte_limit_is_rejected_not_truncated(monkeypatch):
    from app.api.deps import reset_context
    from app.core.config import reset_settings_cache
    from app.main import create_app

    monkeypatch.setenv("SPLITSCOPE_MAX_UPLOAD_BYTES", str(4 * 1024))  # 4 KiB
    reset_settings_cache()
    reset_context()
    try:
        with TestClient(create_app()) as small_client:
            payload = _split_marked_rows(400)  # comfortably over 4 KiB
            assert len(payload) > 4 * 1024
            response = _upload(small_client, payload)
            assert response.status_code == 413
            body = response.json()
            assert body["error"]["code"] == "limit_exceeded"
            assert body["error"]["details"]["bytes_allowed"] == 4 * 1024
            assert "larger than" in body["error"]["message"].lower()
    finally:
        monkeypatch.undo()
        reset_settings_cache()
        reset_context()


def test_parsed_memory_limit_rejects_an_expanding_file(monkeypatch):
    """A small CSV of long text can balloon in memory; that is a separate limit."""
    from app.api.deps import reset_context
    from app.core.config import reset_settings_cache
    from app.main import create_app

    monkeypatch.setenv("SPLITSCOPE_MAX_PARSED_BYTES", str(64 * 1024))  # 64 KiB parsed
    reset_settings_cache()
    reset_context()
    try:
        with TestClient(create_app()) as small_client:
            rows = [{"text": "x" * 500, "other": "y" * 500} for _ in range(100)]
            payload = rows_to_csv(rows)
            assert len(payload) < 160 * 1024  # passes the raw byte check
            response = _upload(small_client, payload)
            assert response.status_code == 413
            body = response.json()
            assert body["error"]["code"] == "limit_exceeded"
            details = body["error"]["details"]
            assert details["parsed_bytes"] > details["parsed_bytes_allowed"]
            assert "parsed" in body["error"]["message"].lower()
    finally:
        monkeypatch.undo()
        reset_settings_cache()
        reset_context()


def test_store_budget_rejects_a_dataset_larger_than_itself(monkeypatch):
    from app.api.deps import reset_context
    from app.core.config import reset_settings_cache
    from app.main import create_app

    monkeypatch.setenv("SPLITSCOPE_MAX_STORE_BYTES", str(32 * 1024))  # 32 KiB store
    reset_settings_cache()
    reset_context()
    try:
        with TestClient(create_app()) as small_client:
            rows = [{"text": "x" * 400, "other": "y"} for _ in range(150)]
            response = _upload(small_client, rows_to_csv(rows))
            assert response.status_code == 413
            body = response.json()
            assert body["error"]["code"] == "limit_exceeded"
            assert "store budget" in body["error"]["message"]
    finally:
        monkeypatch.undo()
        reset_settings_cache()
        reset_context()


def test_a_rejected_upload_leaves_no_dataset_behind(client):
    from app.api.deps import get_context

    rows = [{"a": "1", "b": "2"} for _ in range(30)]
    good = _upload(client, rows_to_csv(rows))
    assert good.status_code == 201
    before = set(get_context().store.stats().dataset_ids)

    bad = _upload(client, b"a,b\n1,2\n", filename="book.xlsx")  # rejected by type
    assert bad.status_code == 415
    after = set(get_context().store.stats().dataset_ids)
    assert after == before  # the rejected file stored nothing
