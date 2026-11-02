"""In-memory study records and the read models the API returns.

A study belongs to a dataset, not to a user: SplitScope is a local single-user
tool and the store already expires datasets after an hour. The record lives in
the same process for the same reason the dataset does, so a Study Card can never
outlive the data it describes and quietly become orphaned metadata.

Nothing here is persisted. That is stated in every payload rather than left for
a user to discover after a restart.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.audit.dataset import Dataset
from app.audit.roles import validate_roles
from app.audit.types import ColumnRoles
from app.core.version import APP_NAME, APP_VERSION
from app.research.schema import (
    FIELD_LABELS,
    SELECT_OPTIONS,
    STUDY_FIELDS,
    STUDY_SCHEMA_VERSION,
    StudyCardDraft,
    build_role_map,
    completion,
    declared_fields,
    study_issues,
)

MAX_STUDIES = 32

STORAGE_NOTE = (
    "Study Cards live in this server's memory alongside the dataset. They expire with it and "
    "are lost when the process restarts, so export the card if you need to keep it. SplitScope "
    "never writes uploaded raw data to disk."
)


@dataclass
class StudyRecord:
    study_id: str
    dataset_id: str
    revision: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    card: StudyCardDraft = field(default_factory=StudyCardDraft)
    role_assignments: dict[str, list[str]] = field(default_factory=dict)
    split_train_value: str | None = None
    split_test_value: str | None = None
    column_declarations: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def dataset_id_display(self) -> str:
        return self.dataset_id


class StudyRegistry:
    """Bounded registry keyed by dataset id, with one record per dataset."""

    def __init__(self, max_entries: int = MAX_STUDIES) -> None:
        self._records: dict[str, StudyRecord] = {}
        self._max = max_entries
        self._lock = threading.RLock()

    def get(self, dataset_id: str) -> StudyRecord | None:
        with self._lock:
            return self._records.get(dataset_id)

    def get_or_create(
        self,
        dataset_id: str,
        seed_roles: dict[str, list[str]] | None = None,
        seed_split_labels: tuple[str | None, str | None] | None = None,
    ) -> StudyRecord:
        with self._lock:
            existing = self._records.get(dataset_id)
            if existing is not None:
                return existing
            record = StudyRecord(
                study_id=f"study-{uuid.uuid4().hex[:10]}",
                dataset_id=dataset_id,
                role_assignments=dict(seed_roles or {}),
                split_train_value=seed_split_labels[0] if seed_split_labels else None,
                split_test_value=seed_split_labels[1] if seed_split_labels else None,
            )
            while len(self._records) >= self._max:
                oldest = min(self._records, key=lambda key: self._records[key].updated_at)
                del self._records[oldest]
            self._records[dataset_id] = record
            return record

    def save(self, record: StudyRecord) -> StudyRecord:
        with self._lock:
            record.revision += 1
            record.updated_at = datetime.now(UTC)
            self._records[record.dataset_id] = record
            return record

    def discard(self, dataset_id: str) -> bool:
        with self._lock:
            return self._records.pop(dataset_id, None) is not None

    def count(self) -> int:
        with self._lock:
            return len(self._records)


def roles_from_column_roles(roles: ColumnRoles) -> dict[str, list[str]]:
    """Seed a research role map from V1's column roles.

    Used once, when a study is created: the V1 roles are the user's existing
    answer, so starting from them avoids asking the same question twice. It is a
    copy, not a live link — the research map becomes the single source of truth.
    """
    assignments: dict[str, list[str]] = {}
    for name in roles.features:
        assignments.setdefault(name, []).append("predictor")
    if roles.target:
        assignments.setdefault(roles.target, []).append("target")
    if roles.entity:
        assignments.setdefault(roles.entity, []).append("entity")
    if roles.timestamp:
        assignments.setdefault(roles.timestamp, []).append("timestamp")
    if roles.split:
        assignments.setdefault(roles.split, []).append("split")
    for name in roles.metadata_excluded:
        assignments.setdefault(name, []).append("excluded")
    return assignments


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def field_state(record: StudyRecord) -> list[dict[str, Any]]:
    data = record.card.model_dump(mode="json")
    declared = declared_fields(record.card)
    rows: list[dict[str, Any]] = []
    for spec in STUDY_FIELDS:
        value = data.get(spec.name)
        rows.append(
            {
                **spec.model_dump(),
                "value": value,
                "declared": declared[spec.name],
                "provenance": "user_declared" if declared[spec.name] else "missing",
            }
        )
    return rows


def provenance_block(record: StudyRecord) -> dict[str, Any]:
    declared = [name for name, value in declared_fields(record.card).items() if value]
    missing = [name for name, value in declared_fields(record.card).items() if not value]
    return {
        "declared": declared,
        "missing": missing,
        "computed": [
            "dataset.row_count",
            "dataset.column_count",
            "dataset.fingerprint_sha256",
            "profile.columns",
            "schema_fingerprint",
        ],
        "inferred": [],
        "note": (
            "Study fields are yours. SplitScope computes dataset facts and never fills in a study "
            "field, a consent status or a design type on your behalf."
        ),
    }


def study_payload(record: StudyRecord, dataset: Dataset) -> dict[str, Any]:
    """Serialise a study for the API, including derived role state."""
    role_result = build_role_map(
        dataset.columns,
        record.role_assignments,
        split_train_value=record.split_train_value,
        split_test_value=record.split_test_value,
    )
    derived = role_result["derived_roles"]
    v1_issues: list[dict[str, Any]] = []
    if role_result["ok"]:
        validation = validate_roles(dataset, ColumnRoles(**derived))
        v1_issues = [
            {
                "code": f"audit_{issue.code}",
                "severity": "error" if issue.severity == "error" else "warning",
                "column": issue.column,
                "message": issue.message,
                "hint": issue.hint,
            }
            for issue in validation.issues
        ]

    return {
        "study_id": record.study_id,
        "dataset_id": record.dataset_id,
        "dataset_name": dataset.name,
        "schema_version": STUDY_SCHEMA_VERSION,
        "revision": record.revision,
        "created_at_utc": _iso(record.created_at),
        "updated_at_utc": _iso(record.updated_at),
        "card": record.card.model_dump(mode="json"),
        "completion": completion(record.card),
        "fields": field_state(record),
        "issues": study_issues(record.card),
        "provenance": provenance_block(record),
        "roles": {
            "assignments": record.role_assignments,
            "derived_roles": derived,
            "ok": role_result["ok"],
            "issues": list(role_result["issues"]) + v1_issues,
            "errors": role_result["errors"],
            "warnings": role_result["warnings"],
            "note": role_result["note"],
        },
        "split_values": {
            "train": record.split_train_value,
            "test": record.split_test_value,
        },
        "column_declarations": record.column_declarations,
        "select_options": SELECT_OPTIONS,
        "storage_note": STORAGE_NOTE,
        "app": {"name": APP_NAME, "version": APP_VERSION},
    }


def apply_role_map(
    record: StudyRecord,
    dataset: Dataset,
    assignments: dict[str, list[str]],
    *,
    split_train_value: str | None,
    split_test_value: str | None,
) -> dict[str, Any]:
    """Validate and store a role map. Errors are returned, never silently dropped."""
    result = build_role_map(
        dataset.columns,
        assignments,
        split_train_value=split_train_value,
        split_test_value=split_test_value,
    )
    if result["ok"]:
        audit_validation = validate_roles(dataset, ColumnRoles(**result["derived_roles"]))
        if not audit_validation.ok:
            result = {
                **result,
                "ok": False,
                "issues": list(result["issues"])
                + [
                    {
                        "code": f"audit_{issue.code}",
                        "severity": "error",
                        "column": issue.column,
                        "message": issue.message,
                        "hint": issue.hint,
                    }
                    for issue in audit_validation.issues
                    if issue.severity == "error"
                ],
            }
            result["errors"] = len(
                [issue for issue in result["issues"] if issue["severity"] == "error"]
            )
    if not result["ok"]:
        return result

    record.role_assignments = result["assignments"]
    record.split_train_value = split_train_value
    record.split_test_value = split_test_value
    return result


def declaration_map(declarations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Normalise per-column dictionary declarations."""
    cleaned: dict[str, dict[str, Any]] = {}
    for entry in declarations:
        column = str(entry.get("column", "")).strip()
        if not column:
            continue
        cleaned[column] = {
            "declared_type": (entry.get("declared_type") or None),
            "description": (entry.get("description") or None),
            "unit": (entry.get("unit") or None),
            "measurement_scale": (entry.get("measurement_scale") or None),
        }
    return cleaned


__all__ = [
    "MAX_STUDIES",
    "STORAGE_NOTE",
    "StudyRecord",
    "StudyRegistry",
    "apply_role_map",
    "declaration_map",
    "field_state",
    "provenance_block",
    "roles_from_column_roles",
    "study_payload",
]
