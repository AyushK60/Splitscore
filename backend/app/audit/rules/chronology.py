"""SS-CHR-001: chronological split violation.

Label: this is a *chronology check*. It verifies one necessary condition for a
future-prediction split — that no training record is newer than the earliest test
record — and it says nothing about other temporal leakage mechanisms such as
rolling aggregates, lag features computed across the boundary, or label delay.
"""

from __future__ import annotations

import pandas as pd

from app.audit.io import to_datetime_series
from app.audit.rules.base import RuleContext, RuleOutput
from app.audit.types import Count, EvidenceExample, Finding, RuleMetric

RULE_ID = "SS-CHR-001"
TITLE = "Training records extend beyond the earliest test timestamp"

BOUNDARY_CONVENTION = (
    "A violation is recorded when at least one training timestamp is strictly later than the "
    "earliest valid test timestamp. Training rows whose timestamp is exactly equal to the "
    "earliest test timestamp are reported separately as boundary ties and are not counted as a "
    "violation, because at equal timestamps there is no temporal ordering to violate. If "
    "sub-second ordering matters for the intended evaluation, treat boundary ties as a defect as "
    "well and break them with a secondary key."
)

LIMITATIONS = [
    "This is a chronology check on the split's timestamps only. It does not detect temporal "
    "leakage introduced by feature engineering: rolling windows, expanding aggregates, lag "
    "features computed before splitting, or labels whose value depends on events after the "
    "timestamp all survive a perfectly ordered split.",
    "Only rows whose timestamps parse are ordered. Unparsable rows are counted and excluded; "
    "their position in time is not guessed.",
    "Naive timestamps are read as UTC and mixed offsets are normalised to UTC. If the file's "
    "timestamps carry a different implicit zone, the ordering is still consistent within the "
    "file, but the displayed UTC values will not match local time.",
    "The check assumes future-prediction intent. For an evaluation that does not predict forward "
    "in time, an unordered split is not a defect, and this rule reports itself as not evaluated.",
]


def run(ctx: RuleContext) -> RuleOutput:
    timestamp_column = ctx.resolved.timestamp_column
    if timestamp_column is None:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "No timestamp column was selected, so the split's chronological order cannot be checked.",
            timestamp_column="(none)",
        )
    if ctx.config.chronology_intent == "not_applicable":
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "The intended evaluation was declared as not future-prediction, so chronological order "
            "is not a requirement for this audit.",
            chronology_intent=ctx.config.chronology_intent,
        )

    parsed = to_datetime_series(ctx.dataset.frame[timestamp_column])
    not_na = parsed.notna()

    train_positions = ctx.train_positions()
    test_positions = ctx.test_positions()
    train_valid = [p for p in train_positions if bool(not_na.iloc[p])]
    test_valid = [p for p in test_positions if bool(not_na.iloc[p])]
    invalid_train = len(train_positions) - len(train_valid)
    invalid_test = len(test_positions) - len(test_valid)

    metrics = [
        RuleMetric(key="timestamp_column", label="Timestamp column", value=timestamp_column),
        RuleMetric(
            key="unparsable_train_timestamps",
            label="Unparsable train timestamps",
            value=invalid_train,
            unit="rows",
        ),
        RuleMetric(
            key="unparsable_test_timestamps",
            label="Unparsable test timestamps",
            value=invalid_test,
            unit="rows",
        ),
    ]

    if not train_valid or not test_valid:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "insufficient_data",
            f"The check needs at least one parsable timestamp in each split; found "
            f"{len(train_valid)} in train and {len(test_valid)} in test.",
            timestamp_column=timestamp_column,
            unparsable_train=str(invalid_train),
            unparsable_test=str(invalid_test),
        )

    train_max = max(parsed.iloc[p] for p in train_valid)
    test_min = min(parsed.iloc[p] for p in test_valid)
    global_min = min(parsed.iloc[p] for p in train_valid + test_valid)
    global_max = max(parsed.iloc[p] for p in train_valid + test_valid)

    affected = [p for p in train_valid if parsed.iloc[p] > test_min]
    ties = [p for p in train_valid if parsed.iloc[p] == test_min]
    span = train_max - test_min
    overall_span = global_max - global_min

    metrics.extend(
        [
            RuleMetric(key="train_max_timestamp", label="Latest train timestamp", value=_iso(train_max)),
            RuleMetric(key="test_min_timestamp", label="Earliest test timestamp", value=_iso(test_min)),
            RuleMetric(key="boundary_tie_rows", label="Train rows tied at the boundary", value=len(ties), unit="rows"),
            RuleMetric(
                key="train_rows_after_earliest_test",
                label="Train rows newer than the earliest test timestamp",
                value=len(affected),
                unit="rows",
            ),
        ]
    )

    violation = bool(affected)
    metrics.append(
        RuleMetric(
            key="chronology_status",
            label="Chronology status",
            value="violation" if violation else "ordered",
        )
    )

    if not violation:
        return RuleOutput(status="evaluated", findings=[], metrics=metrics)

    affected_share = len(affected) / len(train_valid)
    if affected_share >= ctx.config.chronology_high_train_share:
        severity = "high"
        rationale = (
            f"{len(affected)} of {len(train_valid)} ordered train rows ({affected_share:.1%}) are "
            f"newer than the earliest test timestamp, at or above the configured "
            f"{ctx.config.chronology_high_train_share:.0%} threshold. A future-prediction "
            "evaluation is being estimated on training data drawn from a later period than part of "
            "the test set, so the reported performance would not be out-of-time."
        )
    else:
        severity = "medium"
        rationale = (
            f"{len(affected)} of {len(train_valid)} ordered train rows ({affected_share:.1%}) are "
            f"newer than the earliest test timestamp, below the configured "
            f"{ctx.config.chronology_high_train_share:.0%} threshold for a high-severity finding. "
            "The ordering violation is definite but involves a small share of the training rows."
        )

    details = {
        "earliest_test_timestamp": _iso(test_min),
        "latest_train_timestamp": _iso(train_max),
        "earliest_timestamp_overall": _iso(global_min),
        "latest_timestamp_overall": _iso(global_max),
        "train_rows_after_earliest_test": str(len(affected)),
        "train_rows_tied_at_boundary": str(len(ties)),
        "overlap_span": _human_delta(span),
        "observed_time_range": _human_delta(overall_span),
    }

    example_rows = affected[: ctx.config.max_example_rows_per_example]
    examples = [
        EvidenceExample(
            label=f"Training rows newer than the earliest test timestamp ({len(affected)} total)",
            row_ids=[ctx.row_id(p) for p in example_rows],
            details={
                "first_newer_train_rows": ", ".join(ctx.row_id(p) for p in example_rows),
                **details,
            },
        ),
        EvidenceExample(
            label=f"Earliest test rows defining the boundary ({len(test_valid)} ordered test rows)",
            row_ids=[ctx.row_id(p) for p in test_valid[: ctx.config.max_example_rows_per_example]],
            details=details,
        ),
    ]
    if ties:
        examples.append(
            EvidenceExample(
                label=f"Training rows tied at the boundary timestamp ({len(ties)} total)",
                row_ids=[ctx.row_id(p) for p in ties[: ctx.config.max_example_rows_per_example]],
                details={
                    "boundary_timestamp": _iso(test_min),
                    "note": "Equal timestamps are not counted as a violation under the documented "
                    "boundary convention.",
                },
            )
        )

    finding = Finding(
        rule_id=RULE_ID,
        title=TITLE,
        severity=severity,  # type: ignore[arg-type]
        severity_rationale=rationale,
        description=(
            f"The training split contains records timestamped after the earliest record in the "
            f"test split. The latest train timestamp is {_iso(train_max)} while the earliest test "
            f"timestamp is {_iso(test_min)}, an overlap of {_human_delta(span)}. For an evaluation "
            "intended to estimate future performance, the split must place all earlier records in "
            "training and all later records in test; otherwise the training set has access to "
            "information from the test period."
        ),
        evidence_summary=(
            f"{len(affected)} of {len(train_valid)} ordered train row(s) are newer than the "
            f"earliest test timestamp {_iso(test_min)}. Latest train timestamp: {_iso(train_max)}. "
            f"{len(ties)} train row(s) are tied exactly at the boundary timestamp and are not "
            "counted as violations."
        ),
        counts=[
            Count(
                label="Train rows newer than the earliest test timestamp",
                affected=len(affected),
                denominator=len(train_valid),
                unit="rows",
                note="Denominator covers only train rows whose timestamp parsed.",
            ),
            Count(
                label="Train rows tied exactly at the earliest test timestamp (not a violation)",
                affected=len(ties),
                denominator=len(train_valid),
                unit="rows",
                note=BOUNDARY_CONVENTION,
            ),
            Count(
                label="Train rows whose timestamp could not be parsed (excluded from ordering)",
                affected=invalid_train,
                denominator=len(train_positions),
                unit="rows",
            ),
            Count(
                label="Test rows whose timestamp could not be parsed (excluded from ordering)",
                affected=invalid_test,
                denominator=len(test_positions),
                unit="rows",
            ),
        ],
        examples=examples,
        example_total=len(examples),
        examples_truncated=False,
        recommended_action=(
            "Replace the split with a chronological holdout (available in the split comparison) on "
            "the same timestamp column, which places every record earlier than the cut in training "
            "and the rest in test while keeping equal timestamps together. Confirm afterwards that "
            "no feature is computed from a window spanning the cut."
        ),
        limitations=LIMITATIONS,
        assumptions=[
            BOUNDARY_CONVENTION,
            "The timestamp column records when the record became usable as a training example, not "
            "when it was loaded.",
            "Ordered rows carry valid timestamps; unparsable rows are excluded rather than placed.",
            f"Row identifiers are positional, so the row IDs in the evidence refer to the uploaded "
            f"file, not to the chronological order. The {len(affected)} affected train row(s) are "
            f"timestamped after {_iso(test_min)}.",
        ],
    )

    return RuleOutput(status="evaluated", findings=[finding], metrics=metrics)


def _iso(value: pd.Timestamp) -> str:
    return value.isoformat()


def _human_delta(delta: pd.Timedelta) -> str:
    seconds = delta.total_seconds()
    if seconds >= 86400 * 2:
        return f"{seconds / 86400:.1f} days"
    if seconds >= 3600 * 2:
        return f"{seconds / 3600:.1f} hours"
    if seconds >= 120:
        return f"{seconds / 60:.1f} minutes"
    return f"{seconds:.0f} seconds"


__all__ = ["BOUNDARY_CONVENTION", "RULE_ID", "TITLE", "run"]
