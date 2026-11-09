"""Schema fingerprints and the reproducibility manifest.

A manifest is the difference between "we audited a file called data.csv" and
"we audited these bytes, with this schema, under these declared roles". It
therefore records identity, not permission: no raw rows, no cell values, no
secrets - only the fingerprint of the source bytes, a deterministic schema hash
and the declarations that shaped the analysis.

Re-import is deliberately conservative. A manifest whose dataset hash does not
match the loaded dataset is reported as a mismatch instead of being applied to
the wrong data.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.audit.dataset import Dataset
from app.audit.io import ROW_ID_PREFIX
from app.audit.types import ColumnRoles
from app.core.version import APP_NAME, APP_VERSION
from app.research.schema import MANIFEST_SCHEMA_VERSION, STUDY_SCHEMA_VERSION
from app.research.studies import StudyRecord, build_role_map


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def schema_fingerprint(dataset: Dataset, roles: ColumnRoles) -> str:
    """Deterministic hash of the schema *and* the role mapping it is audited under.

    Column order is part of the schema, because a role map applied to reordered
    columns describes a different analysis. Cell values are excluded on purpose:
    this identifies structure, not content.
    """
    from app.core.hashing import sha256_text

    payload = {
        "columns": list(dataset.columns),
        "roles": {
            "features": list(roles.features),
            "target": roles.target,
            "entity": roles.entity,
            "timestamp": roles.timestamp,
            "split": roles.split,
            "split_train_value": roles.split_train_value,
            "split_test_value": roles.split_test_value,
            "metadata_excluded": list(roles.metadata_excluded),
        },
    }
    return sha256_text(_canonical(payload))


def build_manifest(
    dataset: Dataset,
    record: StudyRecord,
    *,
    available_checks: list[str],
    run_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble a manifest from the loaded dataset and its study record."""
    role_result = build_role_map(
        dataset.columns,
        record.role_assignments,
        split_train_value=record.split_train_value,
        split_test_value=record.split_test_value,
    )
    derived = role_result["derived_roles"]
    roles = ColumnRoles(**derived)
    card = record.card.model_dump(mode="json")

    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "study_schema_version": STUDY_SCHEMA_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "application": {"name": APP_NAME, "version": APP_VERSION},
        "study": {
            "study_id": record.study_id,
            "revision": record.revision,
            "title": card.get("title"),
            "objective": card.get("objective"),
            "design": card.get("design"),
            "target_task": card.get("target_task"),
            "unit_of_analysis": card.get("unit_of_analysis"),
            "population": card.get("population"),
            "sampling": card.get("sampling"),
            "collection_period": card.get("collection_period"),
            "primary_outcome": card.get("primary_outcome"),
            "predictor_availability": card.get("predictor_availability"),
            "missing_data_convention": card.get("missing_data_convention"),
            "inclusion_rules": card.get("inclusion_rules"),
            "exclusion_rules": card.get("exclusion_rules"),
            "limitations": card.get("limitations"),
            "data_owner": card.get("data_owner"),
            "rights_note": card.get("rights_note"),
            "consent_status": card.get("consent_status"),
            "privacy_flags": card.get("privacy_flags", []),
        },
        "dataset": {
            "name": dataset.name,
            "source": dataset.source,
            "is_synthetic": dataset.is_synthetic,
            "sha256": dataset.fingerprint_sha256,
            "rows": dataset.row_count,
            "columns": dataset.column_count,
            "encoding": dataset.encoding,
            "row_id_scheme": f"{ROW_ID_PREFIX}NNNNNN (positional, 1-based, stable per file)",
            "schema_fingerprint": schema_fingerprint(dataset, roles),
        },
        "roles": {
            "assignments": record.role_assignments,
            "derived_column_roles": derived,
            "role_validation": {
                "ok": role_result["ok"],
                "errors": role_result["errors"],
                "warnings": role_result["warnings"],
            },
        },
        "analysis": {
            "split_strategy": (
                f"existing column {derived['split']!r}"
                if derived.get("split")
                else "not configured in this manifest"
            ),
            "seed": None,
            "preprocessing": "none (this manifest predates any fitted pipeline)",
            "checks_available": available_checks,
            "checks_run": [],
            "run_ids": run_ids or [],
            "note": (
                "No audit run is bound to this manifest yet. Run the audit and export its report "
                "to record which checks actually executed."
            ),
        },
        "exclusions": {
            "excluded_columns": derived.get("metadata_excluded", []),
            "excluded_row_count": None,
            "note": "Row-level exclusions are not applied by the audit; this field stays null.",
        },
        "warnings": [
            "The Study Card is user-declared. Consent, ethics approval and data rights are not "
            "verified by SplitScope.",
            "The schema fingerprint identifies structure and roles, not cell contents.",
        ],
        "integrity": {
            "raw_data_embedded": False,
            "cell_values_embedded": False,
        },
    }


def validate_manifest(dataset: Dataset, manifest: dict[str, Any]) -> dict[str, Any]:
    """Compare an imported manifest with the currently loaded dataset.

    Returns a status the UI can act on rather than a bare boolean: a mismatched
    dataset is not the same problem as a manifest from an unsupported version.
    """
    version = manifest.get("manifest_schema_version")
    if version != MANIFEST_SCHEMA_VERSION:
        return {
            "status": "unsupported_version",
            "ok": False,
            "expected_version": MANIFEST_SCHEMA_VERSION,
            "received_version": version,
            "message": (
                f"This manifest was written with schema {version!r}; this build reads "
                f"{MANIFEST_SCHEMA_VERSION!r}."
            ),
            "checks": [],
        }

    data = manifest.get("dataset") or {}
    manifest_hash = data.get("sha256")
    dataset_hash = dataset.fingerprint_sha256
    hash_matches = manifest_hash == dataset_hash

    roles_payload = (manifest.get("roles") or {}).get("derived_column_roles")
    if not isinstance(roles_payload, dict):
        return {
            "status": "malformed",
            "ok": False,
            "message": "The manifest has no derived column roles to compare.",
            "checks": [],
        }

    try:
        roles = ColumnRoles(**roles_payload)
    except Exception:
        return {
            "status": "malformed",
            "ok": False,
            "message": "The manifest's column roles are not a valid role object.",
            "checks": [],
        }

    fingerprint = schema_fingerprint(dataset, roles)
    schema_matches = fingerprint == data.get("schema_fingerprint")

    checks = [
        {
            "name": "dataset_sha256",
            "ok": hash_matches,
            "expected": manifest_hash,
            "actual": dataset_hash,
            "message": (
                "The loaded file is byte-identical to the manifest's dataset."
                if hash_matches
                else "The loaded file is different from the one this manifest describes."
            ),
        },
        {
            "name": "schema_and_roles",
            "ok": schema_matches,
            "expected": data.get("schema_fingerprint"),
            "actual": fingerprint,
            "message": (
                "Column order and role mapping match the manifest."
                if schema_matches
                else "Columns or role assignments differ from the manifest."
            ),
        },
    ]

    if hash_matches and schema_matches:
        status = "match"
        message = "The manifest matches the loaded dataset. Its study metadata can be applied."
    elif not hash_matches:
        status = "dataset_mismatch"
        message = (
            "This manifest belongs to different bytes. Re-upload the original file, or start a new "
            "study rather than applying metadata to the wrong data."
        )
    else:
        status = "schema_mismatch"
        message = (
            "The dataset matches but the schema or role mapping does not. Apply the roles "
            "explicitly if that difference is intended."
        )

    return {
        "status": status,
        "ok": status == "match",
        "message": message,
        "checks": checks,
        "study": manifest.get("study"),
        "dataset_in_manifest": data,
        "note": "Metadata import never reconstructs raw data; only the declarations are applied.",
    }


__all__ = ["build_manifest", "schema_fingerprint", "validate_manifest"]
