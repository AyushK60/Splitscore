"""Shared fixtures.

Fixtures here build datasets from explicitly written rows and load them through the
real CSV ingestion path, so a test exercises the same code a user does. Expected
outcomes are written by hand in each test; nothing is derived by calling the
implementation under test.
"""

from __future__ import annotations

import csv
import io
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.audit.dataset import Dataset
from app.audit.io import read_csv_bytes
from app.audit.service import audit_existing_split
from app.audit.types import AuditConfig, AuditResult, ColumnRoles, Finding, RuleOutcome
from app.core.config import Settings, get_settings

REPO_ROOT = BACKEND_ROOT.parent


def rows_to_csv(rows: Sequence[dict[str, Any]], columns: Sequence[str] | None = None) -> bytes:
    """Serialise rows to CSV bytes with all values as text."""
    fieldnames = list(columns) if columns else list(rows[0].keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: ("" if row.get(key) is None else row.get(key, "")) for key in fieldnames})
    return buffer.getvalue().encode("utf-8")


def make_dataset(
    rows: Sequence[dict[str, Any]],
    *,
    name: str = "fixture.csv",
    source: str = "upload",
    is_synthetic: bool = False,
    min_rows: int = 1,
    min_columns: int = 1,
    max_rows: int = 100_000,
    max_columns: int = 1_000,
    max_bytes: int = 50 * 1024 * 1024,
    columns: Sequence[str] | None = None,
) -> Dataset:
    """Build a Dataset by writing rows and reading them back through the loader."""
    payload = rows_to_csv(rows, columns)
    loaded = read_csv_bytes(
        payload,
        max_bytes=max_bytes,
        max_rows=max_rows,
        max_columns=max_columns,
        min_rows=min_rows,
        min_columns=min_columns,
        filename=name,
    )
    return Dataset(
        dataset_id="ds-test",
        name=name,
        source=source,
        is_synthetic=is_synthetic,
        fingerprint_sha256=loaded.fingerprint_sha256,
        frame=loaded.frame,
        row_ids=loaded.row_ids,
        columns=loaded.columns,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        encoding=loaded.encoding,
        size_bytes=len(payload),
        warnings=list(loaded.warnings),
        demo=None,
    )


def make_roles(
    *,
    features: Iterable[str],
    target: str | None = None,
    entity: str | None = None,
    timestamp: str | None = None,
    split: str | None = None,
    train_value: str | None = "train",
    test_value: str | None = "test",
    metadata_excluded: Iterable[str] = (),
) -> ColumnRoles:
    return ColumnRoles(
        features=list(features),
        target=target,
        entity=entity,
        timestamp=timestamp,
        split=split,
        split_train_value=train_value if split else None,
        split_test_value=test_value if split else None,
        metadata_excluded=list(metadata_excluded),
    )


@pytest.fixture()
def settings():
    return get_settings()


@pytest.fixture()
def default_config() -> AuditConfig:
    return AuditConfig()


@pytest.fixture()
def dataset_factory():
    return make_dataset


@pytest.fixture()
def roles_factory():
    return make_roles


def run_audit_for(
    dataset: Dataset,
    roles: ColumnRoles,
    config: AuditConfig | None = None,
    settings: Settings | None = None,
) -> AuditResult:
    return audit_existing_split(
        dataset,
        roles=roles,
        config=config or AuditConfig(),
        settings=settings or get_settings(),
    )


def findings_for(result: AuditResult, rule_id: str) -> list[Finding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def outcome_for(result: AuditResult, rule_id: str) -> RuleOutcome:
    for outcome in result.rule_outcomes:
        if outcome.rule_id == rule_id:
            return outcome
    raise AssertionError(f"{rule_id} was not run")


def metric_for(result: AuditResult, rule_id: str, key: str):
    for metric in outcome_for(result, rule_id).metrics:
        if metric.key == key:
            return metric.value
    return None


def count_for(finding: Finding, label_fragment: str):
    for count in finding.counts:
        if label_fragment.lower() in count.label.lower():
            return count
    raise AssertionError(
        f"no count matching {label_fragment!r} in {[count.label for count in finding.counts]}"
    )


@pytest.fixture()
def datasets_dir() -> Path:
    return REPO_ROOT / "datasets"
