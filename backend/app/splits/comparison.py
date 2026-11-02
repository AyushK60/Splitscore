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

import numpy as np

from app.audit.canonical import ValueCanonicalizer
from app.audit.dataset import Dataset, SplitMasks
from app.audit.engine import build_canonicalizer, run_audit
from app.audit.types import (
    AuditConfig,
    AuditResult,
    ColumnRoles,
    ComparisonResult,
    ComparisonRow,
    PlanComparison,
    PlanFoldFacts,
    ResolvedRoles,
    SplitAssignment,
    SplitConfig,
    SplitSummary,
)
from app.core.config import Settings
from app.core.errors import InfeasibleOperationError
from app.core.logging_config import get_logger
from app.splits.plans import MAX_FOLDS, MAX_REPEATS, EvaluationPlan, PlanConfig, build_plan
from app.splits.strategies import existing_split, generate_split, summarise

logger = get_logger(__name__)

#: Maximum audited folds across all plans in one comparison. Every fold runs
#: the full audit, so the bound keeps the endpoint bounded and predictable.
MAX_TOTAL_FOLDS = 20

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


def _fold_facts(
    *,
    fold,
    result: AuditResult,
) -> PlanFoldFacts:
    metrics = {outcome.rule_id: outcome.metrics for outcome in result.rule_outcomes}
    duplicate_metrics = metrics.get("SS-DUP-001", [])
    entity_metrics = metrics.get("SS-ENT-001", [])
    chronology_metrics = metrics.get("SS-CHR-001", [])
    statuses = {check.rule_id: check for check in result.evaluation.not_evaluated}
    chronology_status = _metric(chronology_metrics, "chronology_status")
    if chronology_status is None and "SS-CHR-001" in statuses:
        chronology_status = f"not evaluated: {statuses['SS-CHR-001'].status}"
    return PlanFoldFacts(
        fold_index=fold.fold_index,
        repeat=fold.repeat,
        train_rows=fold.train_rows,
        test_rows=fold.test_rows,
        exact_duplicate_test_rows=_metric(duplicate_metrics, "exact_duplicate_test_rows"),
        entity_shared_groups=_metric(entity_metrics, "shared_groups"),
        entity_overlap_test_share=_metric(entity_metrics, "entity_overlap_test_share"),
        chronology_status=str(chronology_status) if chronology_status is not None else None,
        findings_by_rule={
            outcome.rule_id: len(outcome.findings) for outcome in result.rule_outcomes if outcome.findings
        },
        findings_total=result.evaluation.findings_total,
        duration_ms=result.duration_ms,
    )


def _unsupported_plan(plan_config: PlanConfig, reason: str) -> PlanComparison:
    return PlanComparison(
        plan_id=plan_config.plan_id or plan_config.kind,
        kind=plan_config.kind,
        label=plan_config.label,
        n_folds=plan_config.n_folds,
        repeats=plan_config.repeats,
        gap=plan_config.gap,
        supported=False,
        unsupported_reason=reason,
    )


def _plan_comparison(
    *,
    dataset: Dataset,
    plan: EvaluationPlan,
    roles: ColumnRoles,
    resolved: ResolvedRoles,
    config: AuditConfig,
    settings: Settings,
    canonicalizer: ValueCanonicalizer,
) -> PlanComparison:
    """Audit every fold of one plan and aggregate the outcomes honestly."""
    fold_facts: list[PlanFoldFacts] = []
    for fold in plan.folds:
        fold_label = (
            f"{plan.label} fold {fold.fold_index}"
            if plan.repeats == 1
            else f"{plan.label} repeat {fold.repeat} fold {fold.fold_index}"
        )
        summary = SplitSummary(
            strategy_id=f"{plan.plan_id}:f{fold.repeat}.{fold.fold_index}",
            label=fold_label,
            kind="existing",
            train_rows=fold.train_rows,
            test_rows=fold.test_rows,
            seed=plan.seed,
            proportion_note=None,
            notes=[f"Fold {fold.fold_index} of the {plan.label} plan."],
        )
        # Rebuild the fold's masks from its exact row ids, so what is audited is
        # exactly what the plan stores and what an export would contain.
        id_set = set(fold.test_row_ids)
        test_mask = np.zeros(dataset.row_count, dtype=bool)
        train_ids = set(fold.train_row_ids)
        train_mask = np.zeros(dataset.row_count, dtype=bool)
        for position, row_id in enumerate(dataset.row_ids):
            if row_id in train_ids:
                train_mask[position] = True
            elif row_id in id_set:
                test_mask[position] = True
        masks = SplitMasks(train=train_mask, test=test_mask)
        result = run_audit(
            dataset=dataset,
            roles=roles,
            resolved=resolved,
            config=config,
            masks=masks,
            split_summary=summary,
            settings=settings,
        )
        fold_facts.append(_fold_facts(fold=fold, result=result))

    overlaps = [
        fold.entity_overlap_test_share
        for fold in fold_facts
        if fold.entity_overlap_test_share is not None
    ]
    violations = sum(
        1 for fold in fold_facts if fold.chronology_status == "violation"
    )
    findings_by_rule: dict[str, int] = {}
    for fold in fold_facts:
        for rule_id, count in fold.findings_by_rule.items():
            findings_by_rule[rule_id] = findings_by_rule.get(rule_id, 0) + count
    folds_with_findings = sum(1 for fold in fold_facts if fold.findings_total > 0)
    worst = max((fold.findings_total for fold in fold_facts), default=0)
    aggregate: dict[str, Any] = {
        "folds_audited": len(fold_facts),
        "folds_with_findings": folds_with_findings,
        "max_findings_in_one_fold": worst,
        "findings_by_rule_total": findings_by_rule,
        "folds_with_chronology_violation": violations,
        "mean_entity_overlap_test_share": (
            round(sum(overlaps) / len(overlaps), 6) if overlaps else None
        ),
        "max_entity_overlap_test_share": (round(max(overlaps), 6) if overlaps else None),
        "mean_test_fraction": (
            round(
                sum(fold.test_rows / (fold.test_rows + fold.train_rows) for fold in fold_facts)
                / len(fold_facts),
                6,
            )
            if fold_facts
            else None
        ),
    }
    return PlanComparison(
        plan_id=plan.plan_id,
        kind=plan.kind,
        label=plan.label,
        n_folds=plan.n_folds,
        repeats=plan.repeats,
        gap=plan.gap,
        seed=plan.seed,
        notes=plan.notes,
        folds=fold_facts,
        aggregate=aggregate,
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
    plans: list[PlanConfig] | None = None,
) -> tuple[ComparisonResult, dict[str, SplitAssignment], dict[str, Any]]:
    """Build every candidate split, audit it, and return the comparison.

    Returns the comparison result, the stored assignments keyed by assignment ID,
    and a small diagnostics dictionary for the API layer. Evaluation plans are
    audited fold by fold and returned as :class:`PlanComparison` entries.
    """
    started = time.perf_counter()
    canonicalizer = build_canonicalizer(config)

    rows: list[ComparisonRow] = []
    per_strategy_findings: dict[str, list[Any]] = {}
    assignments: dict[str, SplitAssignment] = {}
    outcome_meta: dict[str, Any] = {"unsupported": [], "evaluated": []}

    candidates: list[tuple[str, SplitConfig]] = []
    if audit_existing:
        candidates.append((EXISTING_STRATEGY_ID, SplitConfig(kind="existing", label="Existing split column")))
    for index, strategy in enumerate(strategies):
        strategy_id = strategy.strategy_id or f"{strategy.kind}-{index + 1}"
        candidates.append((strategy_id, strategy))

    seen: set[str] = set()
    for strategy_id, strategy in candidates:
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

    plan_results: list[PlanComparison] = []
    plan_configs = plans or []
    total_folds = sum(plan_config.n_folds * plan_config.repeats for plan_config in plan_configs)
    if total_folds > MAX_TOTAL_FOLDS:
        raise InfeasibleOperationError(
            f"The requested plans audit {total_folds} folds in total, above the bound of "
            f"{MAX_TOTAL_FOLDS}. Reduce the fold counts or compare fewer plans per run.",
            details={"total_folds": total_folds, "max_total_folds": MAX_TOTAL_FOLDS},
        )
    for index, plan_config in enumerate(plan_configs):
        plan_id = plan_config.plan_id or f"{plan_config.kind}-{index + 1}"
        try:
            plan = build_plan(
                dataset,
                resolved_entity=resolved.entity_column,
                resolved_target=resolved.target_column,
                resolved_timestamp=resolved.timestamp_column,
                config=plan_config.model_copy(update={"plan_id": plan_id}),
                canonicalizer=canonicalizer,
            )
        except InfeasibleOperationError as exc:
            logger.info("Plan %s is infeasible: %s", plan_id, exc.message)
            plan_results.append(_unsupported_plan(plan_config, exc.message))
            outcome_meta["unsupported"].append(
                {"strategy_id": plan_id, "reason": exc.message, "details": exc.details}
            )
            continue
        plan_results.append(
            _plan_comparison(
                dataset=dataset,
                plan=plan,
                roles=roles,
                resolved=resolved,
                config=config,
                settings=settings,
                canonicalizer=canonicalizer,
            )
        )
        outcome_meta["evaluated"].append(
            {
                "strategy_id": plan_id,
                "kind": "plan",
                "folds_audited": len(plan.folds),
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
            strategies=[strategy for _, strategy in candidates],
            rows=rows,
            per_strategy_findings=per_strategy_findings,
            selection_note=SELECTION_NOTE,
            limitations=list(COMPARISON_LIMITATIONS),
            plans=plan_results,
        ),
        assignments,
        outcome_meta,
    )


__all__ = [
    "COMPARISON_LIMITATIONS",
    "EXISTING_STRATEGY_ID",
    "MAX_TOTAL_FOLDS",
    "SELECTION_NOTE",
    "compare_splits",
]
