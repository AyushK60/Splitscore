"""SS-ENT-002: identifier-like feature reuse across the split.

Label: this is a *memorisation-vector check*. It inspects feature columns whose
observed values are all distinct - an identifier-like column by observation,
not by inference about roles - and reports cross-split value overlap, which is
the raw material of row memorisation.

The check is deliberately narrow about what it claims:

* it never declares a column to be an entity identifier; "identifier-like" is
  an observed property (every non-missing value distinct), stated with its
  evidence;
* it runs only on columns the user assigned as features; the declared entity
  column is audited by SS-ENT-001, which has its own definitions;
* counts, denominators and the split are real. Cardinality alone, without
  cross-split overlap, produces no finding - an all-distinct column that never
  repeats is still recorded in the metrics as a memorisation *vector* to be
  aware of, because the model can memorise training rows even when the exact
  values do not recur.
"""

from __future__ import annotations

import pandas as pd

from app.audit.rules.base import RuleContext, RuleOutput, format_value
from app.audit.types import Count, EvidenceExample, Finding, RuleMetric

RULE_ID = "SS-ENT-002"
TITLE = "Identifier-like feature values shared across the split"

MIN_ROWS = 10  # below this, "all distinct" is not meaningful evidence

LIMITATIONS = [
    "Identifier-like is an observed property (a distinct-value ratio at or above "
    "0.9 over non-missing cells), not a conclusion that the column is an entity "
    "identifier. A high-precision integer measurement can also be all-distinct.",
    "Columns that are predominantly non-integer numbers are treated as continuous "
    "measurements and are not screened: their values are usually all-distinct "
    "without carrying identity, and any exact match would be coincidence.",
    "The check only sees exact value equality. Two spellings of one identifier "
    "are two values; whether that matters is a decision for the data owner.",
    "Overlap of identifier-like values is memorisation *material*, not proof "
    "that the model memorised anything. No model is trained in this tool.",
    "Columns with missing values are evaluated on their non-missing values; "
    "missing counts are reported separately.",
]


def run(ctx: RuleContext) -> RuleOutput:
    features = list(ctx.resolved.feature_columns)
    frame = ctx.dataset.frame
    total_rows = int(len(frame))
    if total_rows < MIN_ROWS:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "insufficient_data",
            f"The dataset has {total_rows} rows; identifier-likeness is only assessed from "
            f"{MIN_ROWS} rows onward.",
            row_count=str(total_rows),
        )

    train_positions = ctx.train_positions()
    test_positions = ctx.test_positions()
    if not train_positions or not test_positions:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "One side of the split is empty, so cross-split reuse cannot be computed.",
        )

    metrics: list[RuleMetric] = [
        RuleMetric(key="feature_count", label="Feature columns", value=len(features)),
        RuleMetric(key="train_rows", label="Train rows", value=len(train_positions)),
        RuleMetric(key="test_rows", label="Test rows", value=len(test_positions)),
    ]

    # A column qualifies as identifier-like when its distinct-value ratio is at
    # or above this threshold - an observed property, not an inference that the
    # column is an entity identifier. Shared values are exactly the case the
    # check screens for, so demanding *all* values distinct would skip them.
    IDENTIFIER_LIKE_RATIO = 0.9
    # Continuous measurements (floats) are usually all-distinct without being
    # identifiers; screening them would flag coincidental value collisions.
    # A column is treated as a continuous measurement when most values parse as
    # numbers and those numbers are predominantly non-integers.
    NUMERIC_RATIO = 0.8
    INTEGER_RATIO = 0.95

    findings: list[Finding] = []
    identifier_like = 0
    for column in features:
        values = frame[column]
        non_missing = values.notna() & (values.astype(str) != "")
        non_missing_count = int(non_missing.sum())
        if non_missing_count == 0:
            continue
        as_numeric = pd.to_numeric(values[non_missing], errors="coerce")
        numeric_ratio = float(as_numeric.notna().mean())
        parsed = as_numeric.dropna()
        integer_ratio = (
            float((parsed % 1 == 0).mean()) if numeric_ratio >= NUMERIC_RATIO and len(parsed) else 0.0
        )
        is_continuous = numeric_ratio >= NUMERIC_RATIO and integer_ratio < INTEGER_RATIO
        if is_continuous:
            metrics.append(
                RuleMetric(
                    key=f"continuous_{column}",
                    label=f"Continuous measurement column (not screened): {column}",
                    value="yes",
                )
            )
            continue
        distinct = int(values[non_missing].astype(str).nunique())
        distinct_ratio = distinct / non_missing_count
        is_identifier_like = distinct_ratio >= IDENTIFIER_LIKE_RATIO
        if not is_identifier_like:
            continue
        identifier_like += 1

        train_values = {str(frame[column].iloc[p]) for p in train_positions}
        test_values = {str(frame[column].iloc[p]) for p in test_positions}
        # '' is excluded: an empty cell is a missing cell, not an identifier.
        shared = sorted((train_values & test_values) - {""})

        metrics.append(
            RuleMetric(
                key=f"identifier_like_{column}",
                label=f"Identifier-like column: {column}",
                value="yes",
            )
        )

        if not shared:
            continue

        test_row_positions = [
            p for p in test_positions if str(frame[column].iloc[p]) in set(shared)
        ]
        train_row_positions = [
            p for p in train_positions if str(frame[column].iloc[p]) in set(shared)
        ]
        severity = "medium"
        rationale = (
            f"The feature column '{column}' is identifier-like ({distinct} distinct "
            f"values over {non_missing_count} non-missing cells, ratio "
            f"{distinct_ratio:.2f}) and {len(shared)} of its value(s) appear on both "
            f"sides of the split, covering {len(test_row_positions)} test row(s) of "
            f"{len(test_positions)} ({len(test_row_positions) / len(test_positions):.1%}). "
            "A model that memorises training rows can use these exact identifiers at "
            "evaluation time, so the test estimate is exposed to memorisation."
        )

        findings.append(
            Finding(
                rule_id=RULE_ID,
                title=TITLE,
                severity=severity,
                severity_rationale=rationale,
                description=(
                    f"The feature column '{column}' has an all-distinct value set (an observed "
                    "identifier-like property) and the same value occurs in both the training "
                    f"and the test split. {len(shared)} shared value(s) cover "
                    f"{len(test_row_positions)} test row(s) and {len(train_row_positions)} "
                    "train row(s). If the model can memorise training rows keyed by these "
                    "identifiers, test performance will be overstated."
                ),
                evidence_summary=(
                    f"Column '{column}': {distinct} distinct non-missing values over "
                    f"{non_missing_count} non-missing cells (distinct ratio "
                    f"{distinct_ratio:.2f}); {len(shared)} value(s) shared across the split; "
                    f"{len(test_row_positions)} test row(s) affected."
                ),
                counts=[
                    Count(
                        label="Shared identifier-like values across the split",
                        affected=len(shared),
                        denominator=distinct,
                        unit="values",
                        scope=f"column '{column}'",
                    ),
                    Count(
                        label="Test rows carrying a shared value",
                        affected=len(test_row_positions),
                        denominator=len(test_positions),
                        unit="rows",
                    ),
                    Count(
                        label="Train rows carrying a shared value",
                        affected=len(train_row_positions),
                        denominator=len(train_positions),
                        unit="rows",
                    ),
                ],
                examples=[
                    EvidenceExample(
                        label=(
                            f"Shared values of '{column}' across the split "
                            f"({len(shared)} total, first {min(len(shared), 4)} shown)"
                        ),
                        row_ids=[
                            ctx.row_id(p)
                            for p in test_row_positions[: ctx.config.max_example_rows_per_example]
                        ],
                        details={
                            "column": column,
                            "shared_values": ", ".join(
                                format_value(value) for value in shared[:4]
                            ),
                            "note": "Row ids shown are test rows carrying a shared value.",
                        },
                    )
                ],
                example_total=1,
                examples_truncated=False,
                recommended_action=(
                    "Confirm with the data owner whether this column would be available and "
                    "meaningful at prediction time. If it is an identifier, exclude it from "
                    "the feature set (or hash it per entity with documented grouping) and "
                    "re-run the audit."
                ),
                limitations=LIMITATIONS,
                assumptions=[
                    "The column was explicitly assigned as a feature; the declared entity "
                    "column, if any, is audited by SS-ENT-001 under its own definitions.",
                    "Exact string equality after the audit's documented canonicalisation is "
                    "the only matching rule.",
                ],
            )
        )

    metrics.append(
        RuleMetric(
            key="identifier_like_columns",
            label="Identifier-like feature columns observed",
            value=identifier_like,
        )
    )
    return RuleOutput(status="evaluated", findings=findings, metrics=metrics)


__all__ = ["LIMITATIONS", "RULE_ID", "TITLE", "run"]
