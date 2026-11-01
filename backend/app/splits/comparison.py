"""Split comparison.

For each requested strategy the comparison builds the assignment, re-runs the
real audit rules against it, and reduces the result to one comparison row.

Two rules are followed throughout:

* A strategy that cannot be built for this dataset (no entity column, a class too
  small to stratify) is marked ``supported=False`` with the reason, and still
  appears in the table. Silently omitting it would hide the option.
* Nothing here selects a winner. The table shows consequences; the deployment
  assumption decides which split is appropriate.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from app.audit.canonical import ValueCanonicalizer
from app.audit.dataset import Dataset, SplitMasks
from app.audit.engine import build_canonicalizer, run_audit
from app.audit.types import (
    AuditConfig,
    AuditResult,
    ColumnRoles,
    ComparisonResult,
    ComparisonRow,
    ResolvedRoles,
    SplitAssignment,
    SplitConfig,
    SplitSummary,
)
from app.core.config import Settings
from app.core.errors import InfeasibleOperationError
from app.core.logging_config import get_logger
from app.splits.strategies import existing_split, generate_split, summarise

logger = get_logger(__name__)

SELECTION_NOTE = (
    "There is no universally best split. The appropriate strategy is the one whose test split "
    "resembles the data the deployed model will be asked about: a random holdout for exchangeable "
    "rows, a stratified holdout when class proportions must be preserved, a group holdout when the "
    "model must generalise to entities it has never seen, and a chronological holdout when it must "
    "predict forward in time. Read the columns above as consequences of that choice, not as a "
    "ranking."
)

COMPARISON_LIMITATIONS: list[str] = [
    "Changing the split changes which of the supported risks are present. It does not remove "
    "duplicate rows, target-proxy features or preprocessing leakage from the data itself.",
    "A split that reports fewer findings is not automatically the better choice for the task; it "
    "may simply be the split that hides the problem from these particular checks.",
    "Every generated strategy should be validated against the deployment assumption it is meant to "
    "represent before its test metrics are reported.",
    "This comparison re-runs the same enabled checks as the audit. Checks that did not run for the "
    "original split typically do not run for the candidates either, for the same reasons.",
]

EXISTING_STRATEGY_ID = "existing"


def _build_split(
    dataset: Dataset,
    *,
    resolved: ResolvedRoles,
    config: SplitConfig,
    canonicalizer: ValueCanonicalizer,
    strategy_id: str,
) -> tuple[SplitMasks, SplitSummary]:
    """Build one assignment, either from the existing column or by generation."""
    if config.kind == "existing":
        if resolved.split_column is None or resolved.train_value is None or resolved.test_value is None:
            raise InfeasibleOperationError(
                "There is no split column configured, so the existing split cannot be audited.",
                details={"strategy": EXISTING_STRATEGY_ID},
            )
        return existing_split(
            dataset,
            split_column=resolved.split_column,
            train_value=resolved.train_value,
            test_value=resolved.test_value,
            strategy_id=strategy_id,
            label=config.label,
        )

    generated = generate_split(
        dataset,
        resolved_entity=resolved.entity_column,
        resolved_target=resolved.target_column,
        resolved_timestamp=resolved.timestamp_column,
        config=config,
        canonicalizer=canonicalizer,
    )
    summary = summarise(
        strategy_id=strategy_id,
        label=config.label,
        kind=config.kind,
        generated=generated,
    )
    return generated.masks, summary


def _metric(outcome_metrics: list[Any], key: str) -> Any:
    for metric in outcome_metrics:
        if metric.key == key:
            return metric.value
    return None


def _target_summary(result: AuditResult) -> tuple[str | None, float | None]:
    target = result.diagnostics.target
    if target is None:
        return None, None
    if target.kind == "categorical":
        return (
            f"categorical, {len([c for c in target.categories if not c.is_other_bucket])} class(es), "
            f"largest proportion gap {target.max_abs_ratio_gap:.1%}"
            if target.max_abs_ratio_gap is not None
            else "categorical",
            target.max_abs_ratio_gap,
        )
    if target.kind == "continuous":
        train_median = target.train_stats.get("median")
        test_median = target.test_stats.get("median")
        if train_median is not None and test_median is not None:
            return f"continuous, median train {train_median:g} / test {test_median:g}", None
        return "continuous", None
    return target.note or "not available", None


def _row_from_result(
    *,
    summary: SplitSummary,
    result: AuditResult,
    notes: list[str],
) -> ComparisonRow:
    metrics = {outcome.rule_id: outcome.metrics for outcome in result.rule_outcomes}
    duplicate_metrics = metrics.get("SS-DUP-001", [])
    entity_metrics = metrics.get("SS-ENT-001", [])
    chronology_metrics = metrics.get("SS-CHR-001", [])

    statuses = {check.rule_id: check for check in result.evaluation.not_evaluated}
    chronology_status = _metric(chronology_metrics, "chronology_status")
    if chronology_status is None and "SS-CHR-001" in statuses:
        chronology_status = f"not evaluated: {statuses['SS-CHR-001'].status}"

    target_summary, target_gap = _target_summary(result)

    return ComparisonRow(
        strategy_id=summary.strategy_id,
        label=summary.label,
        kind=summary.kind,
        supported=True,
        requested_test_fraction=summary.requested_test_fraction,
        achieved_test_fraction=summary.achieved_test_fraction,
        train_rows=summary.train_rows,
        test_rows=summary.test_rows,
        proportion_note=summary.proportion_note,
        exact_duplicate_test_rows=_metric(duplicate_metrics, "exact_duplicate_test_rows"),
        exact_duplicate_test_share=_metric(duplicate_metrics, "exact_duplicate_test_share"),
        entity_shared_groups=_metric(entity_metrics, "shared_groups"),
        entity_overlap_test_share=_metric(entity_metrics, "entity_overlap_test_share"),
        chronology_status=str(chronology_status) if chronology_status is not None else None,
        target_summary=target_summary,
        target_max_abs_ratio_gap=target_gap,
        finding_counts={
            outcome.rule_id: len(outcome.findings)
            for outcome in result.rule_outcomes
            if outcome.findings
        },
        not_evaluated=result.evaluation.not_evaluated,
        notes=notes,
    )


def _unsupported_row(config: SplitConfig, strategy_id: str, reason: str) -> ComparisonRow:
    return ComparisonRow(
        strategy_id=strategy_id,
        label=config.label,
        kind=config.kind,
        supported=False,
        unsupported_reason=reason,
        requested_test_fraction=config.test_fraction if config.kind != "existing" else None,
        finding_counts={},
        not_evaluated=[],
        notes=[],
    )


def compare_splits(
    *,
    dataset: Dataset,
    roles: ColumnRoles,
    resolved: ResolvedRoles,
    strategies: list[SplitConfig],
    config: AuditConfig,
    settings: Settings,
    audit_existing: bool = True,
) -> tuple[ComparisonResult, dict[str, SplitAssignment], dict[str, Any]]:
    """Build every candidate split, audit it, and return the comparison.

    Returns the comparison result, the stored assignments keyed by assignment ID,
    and a small diagnostics dictionary for the API layer.
    """
    started = time.perf_counter()
    canonicalizer = build_canonicalizer(config)

    rows: list[ComparisonRow] = []
    per_strategy_findings: dict[str, list[Any]] = {}
    assignments: dict[str, SplitAssignment] = {}
    outcome_meta: dict[str, Any] = {"unsupported": [], "evaluated": []}

    plans: list[tuple[str, SplitConfig]] = []
    if audit_existing:
        plans.append((EXISTING_STRATEGY_ID, SplitConfig(kind="existing", label="Existing split column")))
    for index, strategy in enumerate(strategies):
        strategy_id = strategy.strategy_id or f"{strategy.kind}-{index + 1}"
        plans.append((strategy_id, strategy))

    seen: set[str] = set()
    for strategy_id, strategy in plans:
        if strategy_id in seen:
            continue
        seen.add(strategy_id)

        try:
            masks, summary = _build_split(
                dataset,
                resolved=resolved,
                config=strategy,
                canonicalizer=canonicalizer,
                strategy_id=strategy_id,
            )
        except InfeasibleOperationError as exc:
            logger.info("Split strategy %s is infeasible: %s", strategy_id, exc.message)
            rows.append(_unsupported_row(strategy, strategy_id, exc.message))
            outcome_meta["unsupported"].append(
                {"strategy_id": strategy_id, "reason": exc.message, "details": exc.details}
            )
            continue

        assignment_id = f"{dataset.dataset_id}:{strategy_id}"
        summary.assignment_id = assignment_id
        assignments[assignment_id] = SplitAssignment(
            assignment_id=assignment_id,
            summary=summary,
            train_row_ids=masks.row_ids(dataset, "train"),
            test_row_ids=masks.row_ids(dataset, "test"),
        )

        result = run_audit(
            dataset=dataset,
            roles=roles,
            resolved=resolved,
            config=config,
            masks=masks,
            split_summary=summary,
            settings=settings,
        )
        notes: list[str] = []
        if summary.proportion_note:
            notes.append(summary.proportion_note)
        notes.extend(summary.notes)

        rows.append(_row_from_result(summary=summary, result=result, notes=notes))
        per_strategy_findings[strategy_id] = result.findings
        outcome_meta["evaluated"].append(
            {
                "strategy_id": strategy_id,
                "findings_total": result.evaluation.findings_total,
                "duration_ms": result.duration_ms,
                "assignment_id": assignment_id,
            }
        )

    return (
        ComparisonResult(
            generated_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            dataset=dataset.summary(),
            roles=roles,
            resolved_roles=resolved,
            audit_config=config,
            strategies=[strategy for _, strategy in plans],
            rows=rows,
            per_strategy_findings=per_strategy_findings,
            selection_note=SELECTION_NOTE,
            limitations=list(COMPARISON_LIMITATIONS),
        ),
        assignments,
        outcome_meta,
    )


__all__ = [
    "COMPARISON_LIMITATIONS",
    "EXISTING_STRATEGY_ID",
    "SELECTION_NOTE",
    "compare_splits",
]
