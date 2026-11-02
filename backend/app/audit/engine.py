"""The audit engine.

The engine is deliberately boring: build a context, run each registered rule in a
fixed order, isolate failures, and assemble the result. All the judgement lives in
the individual rules.

Two properties matter for trustworthiness:

* **Determinism.** For identical input bytes, roles and configuration, the finding
  list, example ordering, counts and metrics are identical. Only the timestamp and
  the runtime measurements vary.
* **Failure isolation.** A rule that raises is recorded as a rule of status
  ``error`` with its exception type. The other rules still run, and the audit as a
  whole does not silently become "clean".
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from app.audit.canonical import ValueCanonicalizer
from app.audit.dataset import Dataset, SplitMasks
from app.audit.diagnostics import build_diagnostics
from app.audit.rules import RULES
from app.audit.rules.base import RuleContext, RuleOutput, severity_ordered
from app.audit.scorecard import build_risk_scorecard
from app.audit.types import (
    AuditConfig,
    AuditResult,
    ColumnRoles,
    EvaluationSummary,
    Finding,
    NotEvaluatedCheck,
    ResolvedRoles,
    RuleOutcome,
    RunHistoryEntry,
    SplitSummary,
)
from app.core.config import Settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

GLOBAL_LIMITATIONS: list[str] = [
    "SplitScope audits a train/test split for the specific, enumerable risks listed in this "
    "report. It does not detect all forms of data leakage, and it cannot establish that a split or "
    "a dataset is safe.",
    "A result with no findings means only that the enabled checks found no supported issue in the "
    "inputs they examined. Checks that did not run are listed separately under 'Not evaluated' and "
    "must not be read as passing.",
    "Findings are evidence records, not scores. This tool deliberately does not compute a combined "
    "trust score, because averaging unrelated defects hides which specific assumption was violated.",
    "Row identifiers are positional ('row-000001' is the first data row of the uploaded file). They "
    "are stable for a fixed file but change if the rows are reordered. They are not content hashes, "
    "which would give duplicated rows identical identifiers and make evidence impossible to "
    "distinguish.",
    "The SHA-256 fingerprint is a reproducibility identifier for the uploaded bytes. It is not "
    "anonymisation: the data remains fully present in the original file.",
    "Only comma-separated text files are supported in this version. Spreadsheet formats, parquet and "
    "database inputs are out of scope.",
    "No predictive model is trained. This version makes no claim about, and reports no measurement "
    "of, model performance.",
]

GLOBAL_ASSUMPTIONS: list[str] = [
    "The uploaded file is the complete data for the intended task, and the train/test labels in it "
    "are the ones actually used.",
    "The selected feature columns are the ones the model will consume, before any preprocessing "
    "fitted on training data.",
    "The target column identifies the quantity the intended evaluation predicts.",
    "Row order in the file carries no meaning beyond the positional row identifiers.",
]


def build_canonicalizer(config: AuditConfig) -> ValueCanonicalizer:
    return ValueCanonicalizer(
        strip_whitespace=config.strip_whitespace,
        normalize_numeric_strings=config.normalize_numeric_strings,
        missing_tokens=config.missing_tokens,
    )


def _order_findings(findings: list[Finding]) -> list[Finding]:
    rule_order = {rule.RULE_ID: index for index, rule in enumerate(RULES)}
    return sorted(
        findings,
        key=lambda finding: (
            severity_ordered(finding.severity),
            rule_order.get(finding.rule_id, 999),
            finding.title,
        ),
    )


def _headline(
    findings: list[Finding], evaluated: list[str], not_evaluated: list[NotEvaluatedCheck]
) -> str:
    if findings:
        by_severity = dict.fromkeys(("high", "medium", "low", "info"), 0)
        for finding in findings:
            by_severity[finding.severity] += 1
        parts = [f"{count} {severity}" for severity, count in by_severity.items() if count]
        return (
            f"{len(findings)} finding(s) across {len(evaluated)} evaluated check(s): "
            + ", ".join(parts)
            + (
                f". {len(not_evaluated)} check(s) did not run and are listed separately."
                if not_evaluated
                else "."
            )
        )
    if not evaluated:
        return (
            "No check could be evaluated with the supplied configuration. This is not a clean "
            "result; nothing was measured."
        )
    if not_evaluated:
        return (
            f"No findings from the {len(evaluated)} check(s) that ran. "
            f"{len(not_evaluated)} check(s) did not run and are listed separately; a check that did "
            "not run is not a check that passed."
        )
    return (
        f"No findings: the {len(evaluated)} enabled check(s) found no supported issue in this split. "
        "This does not establish that the dataset or the split is free of leakage."
    )


def run_audit(
    *,
    dataset: Dataset,
    roles: ColumnRoles,
    resolved: ResolvedRoles,
    config: AuditConfig,
    masks: SplitMasks,
    split_summary: SplitSummary,
    settings: Settings,
    run_history: list[RunHistoryEntry] | None = None,
) -> AuditResult:
    """Run every enabled rule against one split and assemble the result."""
    started = time.perf_counter()
    canonicalizer = build_canonicalizer(config)

    context = RuleContext(
        dataset=dataset,
        masks=masks,
        resolved=resolved,
        config=config,
        settings=settings,
        canonicalizer=canonicalizer,
        split_summary=split_summary,
        run_history=run_history,
    )

    outcomes: list[RuleOutcome] = []
    findings: list[Finding] = []
    not_evaluated: list[NotEvaluatedCheck] = []
    evaluated: list[str] = []

    for rule in RULES:
        rule_started = time.perf_counter()
        try:
            output: RuleOutput = rule.run(context)
        except Exception as exc:
            logger.exception("Rule %s failed: %s", rule.RULE_ID, exc)
            output = RuleOutput(
                status="error",
                not_evaluated=NotEvaluatedCheck(
                    rule_id=rule.RULE_ID,
                    title=rule.TITLE,
                    status="error",
                    reason=(
                        f"The check raised {type(exc).__name__}. Other checks still ran; this check "
                        "produced no result and must not be read as passing."
                    ),
                    details={"exception_type": type(exc).__name__},
                ),
            )
        duration_ms = round((time.perf_counter() - rule_started) * 1000, 3)

        outcomes.append(
            RuleOutcome(
                rule_id=rule.RULE_ID,
                title=rule.TITLE,
                status=output.status,  # type: ignore[arg-type]
                duration_ms=duration_ms,
                findings=output.findings,
                metrics=output.metrics,
                not_evaluated=output.not_evaluated,
            )
        )
        if output.status == "evaluated":
            evaluated.append(rule.RULE_ID)
        elif output.not_evaluated is not None:
            not_evaluated.append(output.not_evaluated)
        findings.extend(output.findings)

    ordered = _order_findings(findings)
    by_severity = dict.fromkeys(("high", "medium", "low", "info"), 0)
    for finding in ordered:
        by_severity[finding.severity] += 1

    diagnostics = build_diagnostics(
        dataset.frame,
        resolved_columns=list(resolved.feature_columns),
        train_mask=masks.train,
        test_mask=masks.test,
        canonicalizer=canonicalizer,
        limits=settings.diagnostics,
        target_column=resolved.target_column,
    )

    limitations = list(GLOBAL_LIMITATIONS)
    notes: list[str] = []
    if split_summary.proportion_note:
        notes.append(split_summary.proportion_note)
    notes.extend(split_summary.notes)
    if getattr(dataset, "warnings", None):
        notes.extend(f"Input warning: {warning}" for warning in dataset.warnings)
    limitations.extend(notes)

    audit_limits: dict[str, object] = {
        **settings.limits_payload(),
        "effective_near_duplicate_row_bound": max(
            2,
            min(
                config.near_duplicates.max_combined_rows,
                settings.near_duplicate.max_combined_rows,
            ),
        ),
        "canonicalization": {
            "strip_whitespace": config.strip_whitespace,
            "normalize_numeric_strings": config.normalize_numeric_strings,
            "missing_tokens": list(config.missing_tokens),
            "missing_definition": (
                "A cell is missing only when it is absent, the empty string, or an exact member of "
                "the configured missing-value tokens. Literal strings such as 'NA' and 'NaN' are "
                "values, not missing values."
            ),
        },
        "severity_thresholds": {
            "entity_overlap_high_test_share": config.entity_overlap_high_test_share,
            "chronology_high_train_share": config.chronology_high_train_share,
            "target_copy_min_coverage": config.target_copy_min_coverage,
            "target_copy_high_coverage": config.target_copy_high_coverage,
            "target_copy_baseline_margin": config.target_copy_baseline_margin,
            "target_copy_min_comparable_rows": config.target_copy_min_comparable_rows,
            "near_duplicate_max_severity": "medium",
        },
    }

    result = AuditResult(
        generated_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        audit_config=config,
        roles=roles,
        resolved_roles=resolved,
        dataset=dataset.summary(),
        split=split_summary,
        evaluation=EvaluationSummary(
            evaluated_rule_ids=evaluated,
            not_evaluated=not_evaluated,
            findings_total=len(ordered),
            findings_by_severity=by_severity,
            headline=_headline(ordered, evaluated, not_evaluated),
        ),
        findings=ordered,
        rule_outcomes=outcomes,
        diagnostics=diagnostics,
        audit_limits=audit_limits,
        limitations=limitations,
        assumptions=GLOBAL_ASSUMPTIONS,
    )
    result.risk_scorecard = build_risk_scorecard(result)
    return result


__all__ = [
    "GLOBAL_ASSUMPTIONS",
    "GLOBAL_LIMITATIONS",
    "build_canonicalizer",
    "run_audit",
]
