"""SS-TGT-001: a selected feature whose observed values exactly match the target.

Scope, stated precisely
-----------------------
This rule tests one specific hypothesis: over the rows where both the feature and
the target are non-missing, does the feature value equal the target value under
the audit's canonicalisation? It is an *equality* test, not a proxy-detection
model. Encoded targets (one-hot, ordinal-encoded, smoothed, log-scaled,
thresholded), derived targets and features that merely correlate strongly with
the target are all outside its scope and will not be reported.
"""

from __future__ import annotations

import numpy as np

from app.audit.canonical import parse_decimal
from app.audit.rules.base import RuleContext, RuleOutput, bound_examples, cap_values
from app.audit.tokens import column_missing_mask, column_tokens
from app.audit.types import Count, EvidenceExample, Finding, RuleMetric

RULE_ID = "SS-TGT-001"
TITLE = "Feature whose values exactly match the target"

LIMITATIONS = [
    "Only exact equality (after canonicalisation, with numeric equivalence for numeric-looking "
    "values) is tested. A target encoded, scaled, rounded, thresholded or one-hot expanded into "
    "a feature is not detected.",
    "A strong statistical association short of exact copying is not detected; correlation- or "
    "regression-based proxy detection is explicitly out of scope for this version.",
    "Equality is computed on the rows where both columns are non-missing. If a feature is present "
    "only on rows where the target has one value, coverage can reach 1.0 on a small comparable "
    "subset; the comparable row count and the target's majority-class rate are therefore reported "
    "alongside every match.",
    "Detecting a match does not establish intent or harm. A deterministic label such as a "
    "downstream status column is sometimes legitimately available.",
]

#: A feature with no variation cannot copy a varying target.
CONSTANT_FEATURE_DISTINCT = 1


def run(ctx: RuleContext) -> RuleOutput:
    target_column = ctx.resolved.target_column
    if target_column is None:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "No target column was selected, so features cannot be compared against a target.",
            target_column="(none)",
        )
    if not ctx.resolved.feature_columns:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "No feature columns were selected to compare against the target.",
            feature_columns="0",
        )

    frame = ctx.dataset.frame
    total_rows = len(frame)
    target_tokens = column_tokens(frame, target_column, ctx.canonicalizer)
    target_missing = column_missing_mask(frame, target_column, ctx.canonicalizer)

    distinct_targets = {t for t, m in zip(target_tokens, target_missing.tolist(), strict=True) if not m}
    if len(distinct_targets) <= 1:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "insufficient_data",
            f"The target column {target_column!r} has {len(distinct_targets)} distinct non-missing "
            "value(s). A constant target cannot be copied by a selected feature in a way this rule "
            "could distinguish from a degenerate column, so the check does not run.",
            target_column=target_column,
            distinct_target_values=str(len(distinct_targets)),
        )

    comparable_mask_all = ~target_missing
    comparable_rows_total = int(comparable_mask_all.sum())

    metrics = [
        RuleMetric(key="target_column", label="Target column", value=target_column),
        RuleMetric(
            key="rows_with_non_missing_target",
            label="Rows with a non-missing target",
            value=comparable_rows_total,
            unit="rows",
        ),
        RuleMetric(
            key="distinct_target_values",
            label="Distinct non-missing target values",
            value=len(distinct_targets),
        ),
        RuleMetric(
            key="min_coverage_threshold",
            label="Minimum coverage to report",
            value=ctx.config.target_copy_min_coverage,
        ),
    ]

    findings: list[Finding] = []
    skipped_constant: list[str] = []
    skipped_small: list[str] = []

    for column in ctx.resolved.feature_columns:
        feature_tokens = column_tokens(frame, column, ctx.canonicalizer)
        feature_missing = column_missing_mask(frame, column, ctx.canonicalizer)

        non_missing_values = {t for t, m in zip(feature_tokens, feature_missing.tolist(), strict=True) if not m}
        if len(non_missing_values) <= CONSTANT_FEATURE_DISTINCT:
            skipped_constant.append(column)
            continue

        comparable = ~(feature_missing | target_missing)
        comparable_rows = int(comparable.sum())
        if comparable_rows < ctx.config.target_copy_min_comparable_rows:
            skipped_small.append(column)
            continue

        matches = 0
        match_positions: list[int] = []
        mismatch_positions: list[int] = []
        for position in np.nonzero(comparable)[0].tolist():
            left = feature_tokens[position]
            right = target_tokens[position]
            equal = left == right
            if not equal:
                left_num = parse_decimal(left)
                right_num = parse_decimal(right)
                equal = left_num is not None and right_num is not None and left_num == right_num
            if equal:
                matches += 1
                match_positions.append(position)
            else:
                mismatch_positions.append(position)

        coverage = matches / comparable_rows
        if coverage < ctx.config.target_copy_min_coverage:
            continue

        baseline = _majority_baseline(target_tokens, comparable, ctx)
        severity, rationale = _severity(ctx, coverage, baseline)

        match_details = {
            "feature_column": column,
            "target_column": target_column,
            "comparable_rows": str(comparable_rows),
            "matching_rows": str(matches),
            "coverage": f"{coverage:.4f}",
            "majority_class_rate_of_target": "not computed (target treated as continuous)"
            if baseline is None
            else f"{baseline:.4f}",
        }
        examples = [
            EvidenceExample(
                label=f"Rows where {column!r} equals the target ({matches} of {comparable_rows} comparable rows)",
                row_ids=cap_values([ctx.row_id(p) for p in match_positions], ctx),
                details={
                    **match_details,
                    "feature_values": ", ".join(
                        str(frame[column].iloc[p])[:40] for p in match_positions[:3]
                    ),
                    "target_values": ", ".join(
                        str(frame[target_column].iloc[p])[:40] for p in match_positions[:3]
                    ),
                },
            )
        ]
        if mismatch_positions:
            examples.append(
                EvidenceExample(
                    label=f"Counterexamples: comparable rows where {column!r} differs from the target",
                    row_ids=cap_values([ctx.row_id(p) for p in mismatch_positions], ctx),
                    details={
                        "differences": str(len(mismatch_positions)),
                        "note": "Counterexamples bound the claim: the feature is not a perfect copy "
                        "of the target on these rows.",
                        "feature_values": ", ".join(
                            str(frame[column].iloc[p])[:40] for p in mismatch_positions[:3]
                        ),
                        "target_values": ", ".join(
                            str(frame[target_column].iloc[p])[:40] for p in mismatch_positions[:3]
                        ),
                    },
                )
            )
        kept, total, truncated = bound_examples(examples, ctx)

        findings.append(
            Finding(
                rule_id=RULE_ID,
                title=f"{TITLE}: {column!r} matches {coverage:.1%} of non-missing targets",
                severity=severity,  # type: ignore[arg-type]
                severity_rationale=rationale,
                description=(
                    f"Over the {comparable_rows} rows where both {column!r} and the target "
                    f"{target_column!r} are non-missing, the feature value equals the target value "
                    f"on {matches} rows ({coverage:.2%}). A feature that reproduces the label "
                    "carries the label into the model's inputs. If this column is available at "
                    "prediction time it will typically produce near-perfect test metrics that do "
                    "not survive deployment; if it is only available retrospectively, it is "
                    "leakage by construction. This is reported as a *potential target proxy*: the "
                    "match is measured, the interpretation is the reader's."
                ),
                evidence_summary=(
                    f"{column!r} equals the target {target_column!r} on {matches} of "
                    f"{comparable_rows} comparable rows ({coverage:.2%} coverage), with "
                    f"{comparable_rows - matches} counterexample(s)."
                ),
                counts=[
                    Count(
                        label="Rows where both the feature and the target are non-missing",
                        affected=comparable_rows,
                        denominator=total_rows,
                        unit="values",
                        note="Only these rows can support an equality test.",
                    ),
                    Count(
                        label="Comparable values where the feature equals the target",
                        affected=matches,
                        denominator=comparable_rows,
                        unit="values",
                        note="This ratio is the coverage referred to throughout the finding.",
                    ),
                    Count(
                        label="Comparable values where the feature differs from the target",
                        affected=comparable_rows - matches,
                        denominator=comparable_rows,
                        unit="values",
                    ),
                    Count(
                        label="Rows excluded because the feature value is missing",
                        affected=int(feature_missing.sum()),
                        denominator=total_rows,
                        unit="rows",
                    ),
                    Count(
                        label="Rows excluded because the target value is missing",
                        affected=int(target_missing.sum()),
                        denominator=total_rows,
                        unit="rows",
                    ),
                ],
                examples=kept,
                example_total=total,
                examples_truncated=truncated,
                recommended_action=(
                    f"Establish whether {column!r} would be genuinely available at prediction time. "
                    "If it is a restatement of the label, drop it from the feature list and re-run "
                    "the audit; if it is legitimately available, record why, because the reported "
                    "test metrics will otherwise be read as if the model had discovered the "
                    "relationship."
                ),
                limitations=LIMITATIONS,
                assumptions=[
                    "The target column as recorded is the prediction target for the intended task.",
                    "Equality is evaluated after whitespace stripping"
                    + (" and numeric-string normalisation" if ctx.canonicalizer.normalize_numeric_strings else "")
                    + ", with numeric equivalence applied to numeric-looking values.",
                    "Missing values match nothing, including other missing values.",
                ],
            )
        )

    if skipped_constant:
        metrics.append(
            RuleMetric(
                key="constant_features_skipped",
                label="Constant features skipped (cannot copy a varying target)",
                value=", ".join(skipped_constant[:10]),
            )
        )
    if skipped_small:
        metrics.append(
            RuleMetric(
                key="features_below_min_comparable_rows",
                label="Features skipped for too few comparable rows",
                value=", ".join(skipped_small[:10]),
            )
        )

    return RuleOutput(status="evaluated", findings=findings, metrics=metrics)


def _majority_baseline(
    target_tokens: list[str], comparable: np.ndarray, ctx: RuleContext
) -> float | None:
    """Share of the most frequent target value among the comparable rows.

    Returns None when the target has more distinct values than the configured
    categorical cut-off, in which case treating each value as a class would be
    meaningless and no baseline is computed.
    """
    values = [target_tokens[p] for p in np.nonzero(comparable)[0].tolist()]
    if not values:
        return None
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    if len(counts) > ctx.settings.diagnostics.categorical_max_unique:
        return None
    return max(counts.values()) / len(values)


def _severity(ctx: RuleContext, coverage: float, baseline: float | None) -> tuple[str, str]:
    if coverage >= ctx.config.target_copy_high_coverage:
        return (
            "high",
            f"Coverage is {coverage:.2%}, at or above the configured "
            f"{ctx.config.target_copy_high_coverage:.0%} threshold: the feature reproduces the "
            "target value almost exactly, which is the strongest form of this defect.",
        )
    if baseline is not None and coverage < baseline + ctx.config.target_copy_baseline_margin:
        return (
            "low",
            f"Coverage is {coverage:.2%}, above the reporting threshold of "
            f"{ctx.config.target_copy_min_coverage:.0%}, but it does not exceed the target's "
            f"majority-class rate of {baseline:.2%} by the configured "
            f"{ctx.config.target_copy_baseline_margin:.0%} margin. Predicting the majority class "
            "alone would already reach this coverage, so the match is weak evidence on its own.",
        )
    return (
        "medium",
        f"Coverage is {coverage:.2%}, above the reporting threshold of "
        f"{ctx.config.target_copy_min_coverage:.0%}"
        + (f" and above the target's majority-class rate of {baseline:.2%}" if baseline is not None else "")
        + ", but below the "
        f"{ctx.config.target_copy_high_coverage:.0%} level where the feature would reproduce the "
        "target almost exactly.",
    )


__all__ = ["RULE_ID", "TITLE", "run"]
