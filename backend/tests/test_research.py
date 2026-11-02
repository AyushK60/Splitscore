"""S3 research foundation: Study Card, roles, profiling and provenance.

Expected values are written by hand or computed with an independent library
(``hashlib``, ``statistics``) so a test cannot pass merely because production
code and the assertion share an implementation.
"""

from __future__ import annotations

import hashlib
import json
import statistics

import pytest
from fastapi.testclient import TestClient

from app.audit.roles import validate_roles
from app.audit.types import ColumnRoles
from app.research.profiling import build_profile
from app.research.provenance import schema_fingerprint
from app.research.schema import StudyCardDraft, build_role_map, completion
from app.research.studies import roles_from_column_roles

from .conftest import make_dataset, rows_to_csv

SENTINEL = "SENTINEL-9137"


@pytest.fixture()
def client():
    from app.api.deps import reset_context
    from app.main import create_app

    reset_context()
    with TestClient(create_app()) as test_client:
        yield test_client


def _upload(client, payload: bytes, filename: str = "study.csv"):
    return client.post("/api/datasets", files={"file": (filename, payload, "text/csv")})


def _numeric_rows(count: int = 24) -> bytes:
    rows = [
        {
            "customer_id": f"C-{index % 4}",
            "amount": str(index + 1),
            "label": "1" if index % 2 else "0",
            "split": "train" if index % 3 else "test",
            "note": SENTINEL if index == 0 else "",
        }
        for index in range(count)
    ]
    return rows_to_csv(rows)


# --------------------------------------------------------------------------- #
# Study Card
# --------------------------------------------------------------------------- #


def test_study_is_created_once_and_is_dataset_scoped(client):
    loaded = _upload(client, _numeric_rows()).json()
    dataset_id = loaded["dataset"]["dataset_id"]

    first = client.get(f"/api/datasets/{dataset_id}/study").json()
    second = client.get(f"/api/datasets/{dataset_id}/study").json()

    assert first["study_id"] == second["study_id"]
    assert first["revision"] == 0
    assert first["card"]["title"] is None
    assert first["completion"]["declared"] == 0
    assert first["completion"]["required"] == 5
    assert "memory" in first["storage_note"]


def test_study_save_requires_no_invented_values_and_counts_completion(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]

    response = client.put(
        f"/api/datasets/{dataset_id}/study",
        json={
            "card": {
                "title": "Repeat purchase study",
                "objective": "Estimate whether the loyalty programme changed repeat purchase.",
                "design": "observational",
                "unit_of_analysis": "customer",
                "target_task": "causal",
            }
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["revision"] == 1
    assert body["completion"] == {
        "required": 5,
        "declared": 5,
        "ratio": 1.0,
        "missing": [],
        "note": body["completion"]["note"],
    }
    # Consent was never asserted, so it must still be unknown.
    assert body["card"]["consent_status"] is None
    assert body["provenance"]["declared"].count("title") == 1
    assert "consent_status" in body["provenance"]["missing"]


def test_missing_required_metadata_is_reported_not_filled(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]

    body = client.put(
        f"/api/datasets/{dataset_id}/study",
        json={"card": {"title": "Only a title"}},
    ).json()

    assert body["completion"]["declared"] == 1
    assert set(body["completion"]["missing"]) == {
        "objective",
        "target_task",
        "design",
        "unit_of_analysis",
    }
    assert body["card"]["design"] is None
    codes = {issue["code"] for issue in body["issues"]}
    assert "missing_objective" in codes


def test_study_edit_increments_revision_and_keeps_values(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    client.put(f"/api/datasets/{dataset_id}/study", json={"card": {"title": "First"}})
    second = client.put(
        f"/api/datasets/{dataset_id}/study",
        json={"card": {"title": "Second", "design": "longitudinal"}},
    ).json()

    assert second["revision"] == 2
    assert second["card"]["title"] == "Second"
    assert second["card"]["design"] == "longitudinal"
    assert second["completion"]["declared"] == 2


def test_invalid_enum_is_rejected(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    response = client.put(
        f"/api/datasets/{dataset_id}/study",
        json={"card": {"design": "astrology"}},
    )
    assert response.status_code == 422


def test_study_export_contains_metadata_and_no_cell_values(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    client.put(
        f"/api/datasets/{dataset_id}/study",
        json={"card": {"title": "Exported study", "objective": "Check export"}},
    )
    response = client.get(f"/api/datasets/{dataset_id}/study/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]

    body = response.json()
    serialised = json.dumps(body)
    assert body["card"]["title"] == "Exported study"
    assert body["dataset"]["row_count"] == 24
    assert "rows" not in body["dataset"]
    assert SENTINEL not in serialised
    assert "C-1" not in serialised


def test_completion_is_not_a_quality_score():
    empty = StudyCardDraft()
    filled = StudyCardDraft(
        title="t", objective="o", design="observational", unit_of_analysis="u", target_task="causal"
    )
    assert completion(empty)["ratio"] == 0.0
    assert completion(filled)["ratio"] == 1.0
    assert "not a measure" in completion(filled)["note"]


# --------------------------------------------------------------------------- #
# Variable roles
# --------------------------------------------------------------------------- #


def _columns() -> list[str]:
    return ["customer_id", "amount", "label", "split", "note"]


def test_valid_role_map_derives_v1_roles_in_column_order():
    result = build_role_map(
        _columns(),
        {
            "customer_id": ["entity"],
            "amount": ["predictor"],
            "label": ["target"],
            "split": ["split"],
            "note": ["excluded"],
        },
        split_train_value="train",
        split_test_value="test",
    )

    assert result["ok"] is True
    derived = result["derived_roles"]
    assert derived["features"] == ["amount"]
    assert derived["target"] == "label"
    assert derived["entity"] == "customer_id"
    assert derived["metadata_excluded"] == ["note"]
    assert derived["split_train_value"] == "train"


def test_future_only_predictor_is_blocked():
    result = build_role_map(
        _columns(), {"amount": ["predictor", "future_only"]}, split_train_value=None, split_test_value=None
    )
    assert result["ok"] is False
    assert any(issue["code"] == "role_conflict" for issue in result["issues"])
    assert "only known after the outcome" in json.dumps(result["issues"])


def test_two_targets_are_rejected():
    result = build_role_map(
        _columns(),
        {"label": ["target"], "amount": ["target"]},
        split_train_value=None,
        split_test_value=None,
    )
    assert result["ok"] is False
    assert any(issue["code"] == "multiple_target" for issue in result["issues"])


def test_unknown_column_is_rejected():
    result = build_role_map(
        _columns(), {"ghost": ["predictor"]}, split_train_value=None, split_test_value=None
    )
    assert result["ok"] is False
    assert result["assignments"] == {}
    assert any(issue["code"] == "unknown_column" for issue in result["issues"])


def test_sensitive_predictor_is_allowed_with_a_warning():
    result = build_role_map(
        _columns(), {"note": ["sensitive", "predictor"]}, split_train_value=None, split_test_value=None
    )
    assert result["ok"] is True
    assert any(issue["severity"] == "warning" for issue in result["issues"])


def test_multiple_compatible_roles_are_allowed():
    result = build_role_map(
        _columns(), {"amount": ["predictor", "confounder"]}, split_train_value=None, split_test_value=None
    )
    assert result["ok"] is True
    assert result["derived_roles"]["features"] == ["amount"]


def test_role_endpoint_persists_and_returns_derived_roles(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    response = client.put(
        f"/api/datasets/{dataset_id}/roles",
        json={
            "assignments": {
                "customer_id": ["entity"],
                "amount": ["predictor"],
                "label": ["target"],
                "split": ["split"],
            },
            "split_train_value": "train",
            "split_test_value": "test",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["derived_roles"]["features"] == ["amount"]

    stored = client.get(f"/api/datasets/{dataset_id}/study").json()
    assert stored["roles"]["assignments"]["amount"] == ["predictor"]


def test_role_endpoint_refuses_conflict_and_keeps_previous_map(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    client.put(
        f"/api/datasets/{dataset_id}/roles",
        json={"assignments": {"amount": ["predictor"]}},
    )
    conflict = client.put(
        f"/api/datasets/{dataset_id}/roles",
        json={"assignments": {"amount": ["predictor", "future_only"]}},
    ).json()
    assert conflict["ok"] is False

    stored = client.get(f"/api/datasets/{dataset_id}/study").json()
    assert stored["roles"]["assignments"] == {"amount": ["predictor"]}


def test_derived_roles_are_accepted_by_the_v1_validator(dataset_factory):
    dataset = dataset_factory(
        [
            {"customer_id": f"C-{i % 3}", "amount": str(i), "label": str(i % 2), "split": "train" if i % 3 else "test"}
            for i in range(30)
        ]
    )
    result = build_role_map(
        dataset.columns,
        {
            "customer_id": ["entity"],
            "amount": ["predictor"],
            "label": ["target"],
            "split": ["split"],
        },
        split_train_value="train",
        split_test_value="test",
    )
    validation = validate_roles(dataset, ColumnRoles(**result["derived_roles"]))
    assert validation.ok is True


def test_seeded_roles_mirror_v1_meanings():
    roles = ColumnRoles(
        features=["amount"],
        target="label",
        entity="customer_id",
        timestamp=None,
        split="split",
        split_train_value="train",
        split_test_value="test",
        metadata_excluded=["note"],
    )
    seeded = roles_from_column_roles(roles)
    assert seeded["amount"] == ["predictor"]
    assert seeded["label"] == ["target"]
    assert seeded["customer_id"] == ["entity"]
    assert seeded["note"] == ["excluded"]


def test_demo_seeded_study_carries_the_declared_split_labels(client):
    """A demo study must be savable as-is: its manifest declares the split labels."""
    dataset_id = client.post("/api/demos/repeated_entity/load").json()["dataset"]["dataset_id"]
    seeded = client.get(f"/api/datasets/{dataset_id}/study").json()
    assert seeded["split_values"] == {"train": "train", "test": "test"}

    # The exact action the study workspace performs on first save: the role map
    # arrives without split labels because the form was already filled in.
    response = client.put(
        f"/api/datasets/{dataset_id}/roles",
        json={"assignments": seeded["roles"]["assignments"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True, response.json()["issues"]


# --------------------------------------------------------------------------- #
# Profiling
# --------------------------------------------------------------------------- #


def test_profile_counts_types_and_missingness_exactly(dataset_factory):
    rows = [
        {"amount": str(value), "kind": "a" if value % 2 else "b", "when": f"2024-01-{value:02d}", "ident": f"x{value}", "blank": ""}
        for value in range(1, 10)
    ]
    rows.append({"amount": "", "kind": "a", "when": "not a date", "ident": "x10", "blank": ""})
    dataset = dataset_factory(rows, min_rows=1)
    profile = build_profile(dataset)
    columns = {column["column"]: column for column in profile["columns"]}

    assert profile["dataset"]["row_count"] == 10
    assert profile["dataset"]["column_count"] == 5
    assert columns["amount"]["detected_type"] == "integer"
    assert columns["amount"]["missing_count"] == 1
    assert columns["amount"]["missing_ratio"] == 0.1
    assert columns["kind"]["detected_type"] == "categorical"
    # Nine of ten values parse, which is exactly the datetime threshold.
    assert columns["when"]["detected_type"] == "datetime"
    assert columns["when"]["datetime"]["unparsed"] == 1
    assert columns["ident"]["detected_type"] == "identifier"
    assert columns["blank"]["detected_type"] == "empty"


def test_profile_examples_are_distinct_values_in_file_order(dataset_factory):
    """A low-cardinality column shows its variety, not three copies of one label."""
    rows = [{"flag": "no" if index < 5 else "yes", "ident": f"x{index}"} for index in range(8)]
    dataset = dataset_factory(rows)
    columns = {column["column"]: column for column in build_profile(dataset)["columns"]}

    assert columns["flag"]["examples"] == ["no", "yes"]
    assert columns["flag"]["distinct_count"] == 2
    # High-cardinality columns are unchanged: first rows in file order.
    assert columns["ident"]["examples"] == ["x0", "x1", "x2"]


def test_numeric_summary_matches_an_independent_oracle(dataset_factory):
    values = [1, 2, 3, 4, 100]
    dataset = dataset_factory([{"v": str(value)} for value in values])
    column = build_profile(dataset)["columns"][0]["numeric"]

    assert column["count"] == 5
    assert column["mean"] == pytest.approx(sum(values) / 5)
    assert column["median"] == pytest.approx(3.0)
    assert column["std"] == pytest.approx(statistics.stdev(values))
    assert column["min"] == 1.0
    assert column["max"] == 100.0
    # Sorted values: q1 = 2.0, q3 = 4.0, so 100 is the only IQR candidate.
    assert column["q1"] == pytest.approx(2.0)
    assert column["q3"] == pytest.approx(4.0)
    assert column["outlier_candidates"] == 1


def test_duplicate_rows_are_counted_with_row_ids(dataset_factory):
    dataset = dataset_factory(
        [
            {"a": "1", "b": "x"},
            {"a": "1", "b": "x"},
            {"a": "2", "b": "y"},
        ]
    )
    profile = build_profile(dataset)
    assert profile["dataset"]["duplicate_rows"] == 1
    assert profile["dataset"]["duplicate_row_groups"] == 1
    assert profile["dataset"]["duplicate_example_row_ids"] == ["row-000002"]


def test_profile_never_silently_coerces_text(dataset_factory):
    rows = [{"v": str(value % 10)} for value in range(20)] + [{"v": "unknown"}]
    dataset = dataset_factory(rows, min_rows=1)
    column = build_profile(dataset)["columns"][0]
    # 20 of 21 cells parse, below the numeric threshold, so the column is text
    # and the mixed values are surfaced instead of a mean being invented.
    assert column["detected_type"] == "categorical"
    assert "mixed_types" in column["flags"]
    assert column["numeric"] is None


def test_profile_on_single_row_dataset_is_finite(dataset_factory):
    dataset = dataset_factory([{"only": "7"}])
    profile = build_profile(dataset)
    column = profile["columns"][0]
    assert column["numeric"]["count"] == 1
    assert column["numeric"]["std"] == 0.0


def test_profile_endpoint_returns_computed_columns(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    body = client.get(f"/api/datasets/{dataset_id}/profile").json()
    columns = {column["column"]: column for column in body["columns"]}

    assert body["dataset"]["row_count"] == 24
    assert columns["amount"]["detected_type"] == "integer"
    assert columns["split"]["detected_type"] == "categorical"
    assert columns["note"]["missing_count"] == 23
    assert isinstance(body["conventions"], list) and body["conventions"]


def test_split_column_values_are_not_mistaken_for_numbers(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    body = client.get(f"/api/datasets/{dataset_id}/dictionary").json()
    split = next(column for column in body["columns"] if column["column"] == "split")
    assert split["detected_type"] == "categorical"
    assert split["numeric"] is None


# --------------------------------------------------------------------------- #
# Provenance and reproducibility
# --------------------------------------------------------------------------- #


def test_dataset_sha256_is_the_hash_of_the_uploaded_bytes(client):
    payload = _numeric_rows()
    dataset_id = _upload(client, payload).json()["dataset"]["dataset_id"]
    manifest = client.get(f"/api/datasets/{dataset_id}/manifest").json()

    assert manifest["dataset"]["sha256"] == hashlib.sha256(payload).hexdigest()


def test_manifest_contains_no_cell_values_and_no_rows(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    manifest = client.get(f"/api/datasets/{dataset_id}/manifest").json()
    serialised = json.dumps(manifest)

    assert SENTINEL not in serialised
    assert "C-1" not in serialised
    assert manifest["integrity"]["raw_data_embedded"] is False
    assert manifest["integrity"]["cell_values_embedded"] is False


def test_schema_fingerprint_is_deterministic_and_role_sensitive(dataset_factory):
    dataset = dataset_factory([{"a": "1", "b": "2", "y": "0"} for _ in range(3)])
    roles_a = ColumnRoles(features=["a"], target="y", entity=None, timestamp=None, split=None)
    roles_b = ColumnRoles(features=["a", "b"], target="y", entity=None, timestamp=None, split=None)

    first = schema_fingerprint(dataset, roles_a)
    assert first == schema_fingerprint(dataset, roles_a)
    assert first != schema_fingerprint(dataset, roles_b)
    assert len(first) == 64


def test_manifest_validation_detects_a_different_dataset(client):
    first = _upload(client, _numeric_rows(), "a.csv").json()["dataset"]["dataset_id"]
    manifest = client.get(f"/api/datasets/{first}/manifest").json()

    second = _upload(client, _numeric_rows(count=25), "b.csv").json()["dataset"]["dataset_id"]
    result = client.post(
        f"/api/datasets/{second}/manifest/validate", json={"manifest": manifest}
    ).json()

    assert result["status"] == "dataset_mismatch"
    assert result["ok"] is False
    assert result["applied"] is False


def test_manifest_validation_matches_and_applies_metadata(client):
    payload = _numeric_rows()
    dataset_id = _upload(client, payload).json()["dataset"]["dataset_id"]
    client.put(
        f"/api/datasets/{dataset_id}/study",
        json={"card": {"title": "Reproducible study", "objective": "obj"}},
    )
    manifest = client.get(f"/api/datasets/{dataset_id}/manifest").json()

    checked = client.post(
        f"/api/datasets/{dataset_id}/manifest/validate", json={"manifest": manifest}
    ).json()
    assert checked["status"] == "match"
    assert checked["ok"] is True
    assert {check["name"] for check in checked["checks"]} == {"dataset_sha256", "schema_and_roles"}


def test_manifest_validation_rejects_an_unknown_schema_version(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    result = client.post(
        f"/api/datasets/{dataset_id}/manifest/validate",
        json={"manifest": {"manifest_schema_version": "0.4", "dataset": {}, "roles": {}}},
    ).json()
    assert result["status"] == "unsupported_version"


def test_manifest_row_id_scheme_is_stated(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    manifest = client.get(f"/api/datasets/{dataset_id}/manifest").json()
    assert manifest["dataset"]["row_id_scheme"].startswith("row-")


def test_schema_fingerprint_round_trips_through_manifest(client):
    dataset_id = _upload(client, _numeric_rows()).json()["dataset"]["dataset_id"]
    manifest = client.get(f"/api/datasets/{dataset_id}/manifest").json()

    roles = ColumnRoles(**manifest["roles"]["derived_column_roles"])
    from app.api.deps import get_context

    dataset = get_context().store.get_dataset(dataset_id)
    assert schema_fingerprint(dataset, roles) == manifest["dataset"]["schema_fingerprint"]
