"""SS-DUP-001: exact feature duplicates across the train/test boundary.

What it does
------------
Canonicalises the selected feature columns for every row, groups rows by the
*verified* canonical feature tuple, and reports groups that contain at least one
train row and at least one test row.

What it deliberately does not do
--------------------------------
It does not look at unselected columns, so two rows that differ in an unselected
column are not reported. It does not detect near duplicates (see SS-NEAR-001),
and it does not look at preprocessing or fitted transformations, which happen
outside any train/test file split.
"""

from __future__ import annotations

from app.audit.rules.base import (
    RuleContext,
    RuleOutput,
    bound_examples,
    cap_values,
    feature_value_details,
    format_value,
    grouped_by_signature,
)
from app.audit.tokens import feature_signatures
from app.audit.types import Count, EvidenceExample, Finding, RuleMetric

RULE_ID = "SS-DUP-001"
TITLE = "Exact feature duplicates across the train/test split"

#: Documented severity thresholds. A single duplicated pair in a huge test split
#: is real but low-impact; duplicates touching a visible share of the test set
#: are not.
HIGH_AFFECTED_TEST_ROWS = 10
HIGH_AFFECTED_TEST_SHARE = 0.05
MEDIUM_AFFECTED_TEST_ROWS = 2

LIMITATIONS = [
    "Only the selected feature columns are compared. Rows that differ in an "
    "unselected column are not exact duplicates by this definition.",
    "Comparison uses the configured canonicalisation (whitespace stripping and "
    "optional numeric-string normalisation). Case folding, Unicode normalisation "
    "and punctuation stripping are never applied, so those variants are reported "
    "as distinct values.",
    "A missing value only matches another missing value. The literal strings 'NA', "
    "'NaN', 'null' and 'None' are treated as ordinary values unless the user adds "
    "them to the missing-value tokens.",
    "Near-duplicate rows that differ slightly are outside this rule; that is the "
    "separate, opt-in SS-NEAR-001 check.",
    "This rule says nothing about preprocessing leakage, group leakage or temporal "
    "leakage. A clean result here is not evidence that the split is sound.",
]


def _severity(affected_test_rows: int, test_rows: int) -> tuple[str, str]:
    share = affected_test_rows / test_rows if test_rows else 0.0
    if affected_test_rows >= HIGH_AFFECTED_TEST_ROWS or share >= HIGH_AFFECTED_TEST_SHARE:
        return (
            "high",
            f"{affected_test_rows} test rows ({share:.1%} of the test split) share an exact "
            f"feature signature with the training data. Exact duplicates at or above "
            f"{HIGH_AFFECTED_TEST_ROWS} rows, or {HIGH_AFFECTED_TEST_SHARE:.0%} of the test "
            "split, break the independence assumption of any i.i.d. evaluation on a "
            "visible share of the test set.",
        )
    if affected_test_rows >= MEDIUM_AFFECTED_TEST_ROWS:
        return (
            "medium",
            f"{affected_test_rows} test rows ({share:.1%} of the test split) share an exact "
            "feature signature with the training data. The violation is definite but small "
            "at this test-set size.",
        )
    return (
        "low",
        f"{affected_test_rows} test row ({share:.1%} of the test split) shares an exact "
        "feature signature with the training data. The violation is definite but affects a "
        "single row.",
    )


def run(ctx: RuleContext) -> RuleOutput:
    features = ctx.resolved.feature_columns
    if not features:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "No feature columns were selected, so there is no feature signature to compare.",
            feature_columns="0",
        )

    frame = ctx.dataset.frame
    train_mask = ctx.masks.train
    test_mask = ctx.masks.test

    signatures = feature_signatures(frame, features, ctx.canonicalizer)
    groups, hash_mismatches = grouped_by_signature(signatures)

    train_positions = [i for i, keep in enumerate(train_mask.tolist()) if keep]
    test_positions = [i for i, keep in enumerate(test_mask.tolist()) if keep]
    train_set = set(train_positions)
    test_set = set(test_positions)

    spanning: list[tuple[tuple[str, ...], list[int], list[int]]] = []
    train_signatures: set[tuple[str, ...]] = set()
    test_signatures: set[tuple[str, ...]] = set()
    train_dup_rows = 0
    test_dup_rows = 0

    for signature, members in groups.items():
        in_train = [p for p in members if p in train_set]
        in_test = [p for p in members if p in test_set]
        if in_train:
            train_signatures.add(signature)
        if in_test:
            test_signatures.add(signature)
        if len(in_train) > 1:
            train_dup_rows += len(in_train)
        if len(in_test) > 1:
            test_dup_rows += len(in_test)
        if in_train and in_test:
            spanning.append((signature, in_train, in_test))

    spanning.sort(key=lambda item: (-(len(item[1]) + len(item[2])), -len(item[2]), item[0]))

    affected_train_rows = sum(len(in_train) for _, in_train, _ in spanning)
    affected_test_rows = sum(len(in_test) for _, _, in_test in spanning)
    shared_signatures = len(spanning)

    test_rows_total = len(test_positions)
    affected_test_share = affected_test_rows / test_rows_total if test_rows_total else 0.0

    metrics = [
        # Emitted unconditionally, including when the value is 0, so the split
        # comparison table can read one stable metric key per check.
        RuleMetric(
            key="exact_duplicate_test_rows",
            label="Test rows sharing a feature signature with train",
            value=affected_test_rows,
            unit="rows",
        ),
        RuleMetric(
            key="exact_duplicate_train_rows",
            label="Train rows sharing a feature signature with test",
            value=affected_train_rows,
            unit="rows",
        ),
        RuleMetric(
            key="exact_duplicate_test_share",
            label="Share of the test split implicated",
            value=round(affected_test_share, 6),
        ),
        RuleMetric(
            key="exact_duplicate_shared_signatures",
            label="Feature signatures present in both splits",
            value=shared_signatures,
            unit="signatures",
        ),
        RuleMetric(key="feature_columns_compared", label="Feature columns compared", value=len(features)),
        RuleMetric(
            key="distinct_feature_signatures",
            label="Distinct feature signatures",
            value=len(groups),
        ),
        RuleMetric(
            key="hash_bucket_collisions_rejected",
            label="Hash buckets split after full-tuple verification",
            value=hash_mismatches,
            unit="buckets",
        ),
        RuleMetric(
            key="within_train_duplicate_rows",
            label="Train rows duplicated within train only",
            value=train_dup_rows,
            unit="rows",
        ),
        RuleMetric(
            key="within_test_duplicate_rows",
            label="Test rows duplicated within test only",
            value=test_dup_rows,
            unit="rows",
        ),
    ]

    if not spanning:
        return RuleOutput(status="evaluated", findings=[], metrics=metrics)

    examples: list[EvidenceExample] = []
    for signature, in_train, in_test in spanning:
        first = in_train[0]
        details = {
            "signature": " | ".join(format_value(value) for value in signature),
            "train_rows_in_group": str(len(in_train)),
            "test_rows_in_group": str(len(in_test)),
            "total_rows_in_group": str(len(in_train) + len(in_test)),
        }
        details.update(feature_value_details(frame, features, first, limit=6))
        examples.append(
            EvidenceExample(
                label=f"Exact duplicate group with {len(in_train)} train and {len(in_test)} test row(s)",
                row_ids=cap_values([ctx.row_id(p) for p in in_train], ctx)
                + cap_values([ctx.row_id(p) for p in in_test], ctx),
                details=details,
            )
        )
    kept, total, truncated = bound_examples(examples, ctx)
    severity, rationale = _severity(affected_test_rows, len(test_positions))

    finding = Finding(
        rule_id=RULE_ID,
        title=TITLE,
        severity=severity,  # type: ignore[arg-type]
        severity_rationale=rationale,
        description=(
            "A feature signature (the tuple of canonicalised values of the selected feature "
            "columns) occurs in both the training and the test split. For a test split that is "
            "meant to estimate performance on unseen rows, the model has already seen these "
            "rows during fitting, so their test contribution is not an unseen-row measurement. "
            "The duplication is a property of the file split; it exists regardless of which "
            "model is trained on it."
        ),
        evidence_summary=(
            f"{shared_signatures} feature signature(s) occur in both splits, covering "
            f"{affected_test_rows} test row(s) ({affected_test_rows / max(len(test_positions), 1):.1%} "
            f"of the test split) and {affected_train_rows} train row(s)."
        ),
        counts=[
            Count(
                label="Feature signatures present in both splits",
                affected=shared_signatures,
                denominator=len(test_signatures),
                unit="signatures",
                note="Denominator is the number of distinct feature signatures observed in the test split.",
            ),
            Count(
                label="Test rows sharing a feature signature with a train row",
                affected=affected_test_rows,
                denominator=len(test_positions),
                unit="rows",
            ),
            Count(
                label="Train rows sharing a feature signature with a test row",
                affected=affected_train_rows,
                denominator=len(train_positions),
                unit="rows",
            ),
            Count(
                label="Test rows that are exact duplicates of another test row (within test only)",
                affected=test_dup_rows,
                denominator=len(test_positions),
                unit="rows",
                note="Within-split duplication is not cross-split leakage. It is reported because "
                "it changes how the test metrics should be read, and because it usually shares a "
                "cause with the cross-split duplicates.",
            ),
            Count(
                label="Train rows that are exact duplicates of another train row (within train only)",
                affected=train_dup_rows,
                denominator=len(train_positions),
                unit="rows",
                note="See the note on within-test duplication.",
            ),
        ],
        examples=kept,
        example_total=total,
        examples_truncated=truncated,
        recommended_action=(
            "Group all copies of a duplicated signature together and place them entirely on one "
            "side of the boundary, or remove the duplicates before splitting. If duplicates arise "
            "from repeated events per entity, a group split by entity (see the split comparison) "
            "removes the overlap directly."
        ),
        limitations=LIMITATIONS,
        assumptions=[
            "The selected feature columns are a complete description of the row for the purpose "
            "of duplicate detection.",
            "Two rows that share every selected feature value are interchangeable for modelling.",
            "Row IDs are positional identifiers ('row-000123' is the 123rd data row of the file), "
            "so they are stable for a fixed file but change if the rows are reordered.",
        ],
    )

    return RuleOutput(status="evaluated", findings=[finding], metrics=metrics)


__all__ = ["RULE_ID", "TITLE", "run"]
