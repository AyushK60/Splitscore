"""Machine-readable JSON report.

Structure, and why each part exists:

* ``app`` and ``schema`` let a consumer detect an incompatible report before
  parsing the rest.
* ``input`` identifies the audited bytes. The SHA-256 is a *reproducibility
  identifier*: two people can confirm they audited identical bytes. It is not
  anonymisation and the payload says so.
* ``settings`` carries every parameter that could change a result, including the
  canonicalisation rules and the severity thresholds, so a finding is always
  reproducible from the report alone.
* ``findings`` and ``not_evaluated`` are separate keys. A consumer that merges
  them silently turns "did not run" into "passed".
* ``reproducibility`` documents exactly which fields vary between runs.

The full uploaded dataset is never embedded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.audit.types import AuditResult, ComparisonResult
from app.core.version import APP_NAME, APP_VERSION, AUDIT_SCHEMA_VERSION

REPRODUCIBILITY_NOTE = (
    "For identical input bytes, column roles and audit settings, findings, counts, metrics and "
    "example ordering are deterministic. The fields generated_at_utc, duration_ms and any run or "
    "dataset identifier vary between runs and are excluded from determinism claims."
)

DETERMINISTIC_FIELDS = [
    "input.sha256",
    "roles",
    "resolved_roles",
    "settings",
    "split",
    "findings",
    "rule_outcomes",
    "diagnostics",
    "evaluation",
]

NON_DETERMINISTIC_FIELDS = ["generated_at_utc", "duration_ms", "run_id", "dataset_id"]


def _app_block(generated_at_utc: str, duration_ms: float) -> dict[str, Any]:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "duration_ms": duration_ms,
    }


def _input_block(dataset: Any) -> dict[str, Any]:
    return {
        "name": dataset.name,
        "source": dataset.source,
        "synthetic": dataset.is_synthetic,
        "demo_id": dataset.demo_id,
        "sha256": dataset.fingerprint_sha256,
        "sha256_note": "Reproducibility identifier for the uploaded bytes, not anonymisation.",
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "columns": dataset.columns,
        "created_at_utc": dataset.created_at_utc,
        "warnings": dataset.warnings,
    }


def build_audit_report(result: AuditResult, *, run_id: str | None = None) -> dict[str, Any]:
    return {
        "report_kind": "audit",
        "app": _app_block(result.generated_at_utc, result.duration_ms),
        "schema": {"audit_schema_version": result.schema_version},
        "run_id": run_id,
        "input": _input_block(result.dataset),
        "roles": result.roles.model_dump(),
        "resolved_roles": result.resolved_roles.model_dump(),
        "settings": {
            "audit_config": result.audit_config.model_dump(),
            "limits": result.audit_limits,
        },
        "split": result.split.model_dump(),
        "evaluation": result.evaluation.model_dump(),
        "findings": [finding.model_dump() for finding in result.findings],
        "rule_outcomes": [outcome.model_dump() for outcome in result.rule_outcomes],
        "not_evaluated": [check.model_dump() for check in result.evaluation.not_evaluated],
        "diagnostics": result.diagnostics.model_dump(),
        "limitations": result.limitations,
        "assumptions": result.assumptions,
        "reproducibility": {
            "note": REPRODUCIBILITY_NOTE,
            "deterministic_fields": DETERMINISTIC_FIELDS,
            "run_dependent_fields": NON_DETERMINISTIC_FIELDS,
        },
        "data_note": (
            "This report contains bounded evidence samples only. The full uploaded dataset is not "
            "included."
        ),
    }


def build_comparison_report(result: ComparisonResult, *, run_id: str | None = None) -> dict[str, Any]:
    return {
        "report_kind": "comparison",
        "app": _app_block(result.generated_at_utc, result.duration_ms),
        "schema": {"audit_schema_version": result.schema_version},
        "run_id": run_id,
        "input": _input_block(result.dataset),
        "roles": result.roles.model_dump(),
        "resolved_roles": result.resolved_roles.model_dump(),
        "settings": {"audit_config": result.audit_config.model_dump()},
        "strategies": [strategy.model_dump() for strategy in result.strategies],
        "rows": [row.model_dump() for row in result.rows],
        "findings_by_strategy": {
            strategy_id: [finding.model_dump() for finding in findings]
            for strategy_id, findings in result.per_strategy_findings.items()
        },
        "selection_note": result.selection_note,
        "limitations": result.limitations,
        "reproducibility": {
            "note": REPRODUCIBILITY_NOTE,
            "deterministic_fields": DETERMINISTIC_FIELDS,
            "run_dependent_fields": NON_DETERMINISTIC_FIELDS,
        },
        "data_note": (
            "This report contains bounded evidence samples only. The full uploaded dataset is not "
            "included."
        ),
    }


def report_filename(kind: str, dataset_name: str, *, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    stem = "".join(
        character if character.isalnum() or character in "-_." else "-" for character in dataset_name
    ).strip("-") or "dataset"
    return f"splitscope-{kind}-{stem}-{stamp}"


__all__ = [
    "DETERMINISTIC_FIELDS",
    "NON_DETERMINISTIC_FIELDS",
    "REPRODUCIBILITY_NOTE",
    "build_audit_report",
    "build_comparison_report",
    "report_filename",
]
