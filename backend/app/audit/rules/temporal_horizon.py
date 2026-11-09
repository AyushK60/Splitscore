"""SS-CHR-002: declared prediction-horizon (lookahead gap) check.

Label: this is a *horizon check*. Where the user has declared a prediction
horizon - how long after the training cutoff the evaluation is meant to
predict - it verifies that the split's time gap actually covers the horizon.
Without a declared horizon the check reports NOT EVALUATED: the horizon is
metadata about intent that a CSV cannot supply.

Definition (documented, deterministic):

* ``gap`` = earliest valid test timestamp − latest valid train timestamp.
* ``affected test rows`` = test rows whose timestamp is earlier than
  ``latest train timestamp + horizon`` - predictions that would be made within
  the declared horizon of training data, so the training set contains events
  from inside their horizon window.

The check shares the chronology boundary convention of SS-CHR-001: only
strictly ordered evidence counts, and unparsable timestamps are counted and
excluded rather than placed.
"""

from __future__ import annotations

import pandas as pd

from app.audit.io import to_datetime_series
from app.audit.rules.base import RuleContext, RuleOutput
from app.audit.types import Count, EvidenceExample, Finding, RuleMetric

RULE_ID = "SS-CHR-002"
TITLE = "Test predictions fall inside the declared prediction horizon"

HIGH_SHARE = 0.10  # share of test rows inside the horizon for a high finding

LIMITATIONS = [
    "The horizon is a declaration. If the declared number of days does not "
    "match the real decision cadence, the check's conclusion inherits that "
    "error.",
    "This check constrains only the split's timestamps. Feature windows, label "
    "delays and event-time misalignment are separate mechanisms it cannot see.",
    "Only rows whose timestamps parse are evaluated; unparsable rows are "
    "counted and excluded, never placed.",
    "The horizon is interpreted in calendar days from the latest training "
    "timestamp; sub-day horizons are supported as fractions of a day.",
]


def run(ctx: RuleContext) -> RuleOutput:
    timestamp_column = ctx.resolved.timestamp_column
    horizon_days = ctx.config.temporal_horizon_days
    if timestamp_column is None:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "No timestamp column was selected, so a horizon check has nothing to evaluate.",
            timestamp_column="(none)",
        )
    if horizon_days is None:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "No prediction horizon was declared. A raw CSV cannot supply the intended "
            "prediction horizon, so the lookahead-gap check is NOT EVALUATED rather than "
            "passed. Declare a horizon (and optionally a note on the event-time "
            "interpretation) in the audit configuration to run it.",
            timestamp_column=timestamp_column,
            horizon="(not declared)",
        )
    if horizon_days <= 0:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "unsupported",
            f"The declared horizon ({horizon_days} days) is not positive, so no gap check is "
            "defined.",
            horizon=str(horizon_days),
        )

    parsed = to_datetime_series(ctx.dataset.frame[timestamp_column])
    not_na = parsed.notna()
    train_positions = [p for p in ctx.train_positions() if bool(not_na.iloc[p])]
    test_positions = [p for p in ctx.test_positions() if bool(not_na.iloc[p])]
    invalid_train = len(ctx.train_positions()) - len(train_positions)
    invalid_test = len(ctx.test_positions()) - len(test_positions)

    metrics: list[RuleMetric] = [
        RuleMetric(key="timestamp_column", label="Timestamp column", value=timestamp_column),
        RuleMetric(key="declared_horizon_days", label="Declared horizon (days)", value=horizon_days),
    ]
    if ctx.config.temporal_horizon_note:
        metrics.append(
            RuleMetric(key="horizon_note", label="Horizon note", value=ctx.config.temporal_horizon_note)
        )
    if not train_positions or not test_positions:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "insufficient_data",
            "The check needs at least one parsable timestamp in each split.",
            timestamp_column=timestamp_column,
            unparsable_train=str(invalid_train),
            unparsable_test=str(invalid_test),
        )

    latest_train = max(parsed.iloc[p] for p in train_positions)
    earliest_test = min(parsed.iloc[p] for p in test_positions)
    horizon_delta = pd.Timedelta(days=horizon_days)
    horizon_end = latest_train + horizon_delta
    gap = earliest_test - latest_train

    affected = [p for p in test_positions if parsed.iloc[p] < horizon_end]
    metrics.extend(
        [
            RuleMetric(key="latest_train_timestamp", label="Latest train timestamp", value=latest_train.isoformat()),
            RuleMetric(key="earliest_test_timestamp", label="Earliest test timestamp", value=earliest_test.isoformat()),
            RuleMetric(key="gap_days", label="Train/test gap (days)", value=round(gap.total_seconds() / 86400, 4)),
            RuleMetric(
                key="test_rows_within_horizon",
                label="Test rows inside the horizon window",
                value=len(affected),
                unit="rows",
            ),
        ]
    )

    if not affected:
        return RuleOutput(status="evaluated", findings=[], metrics=metrics)

    share = len(affected) / len(test_positions)
    severity = "high" if share >= HIGH_SHARE else "medium"
    rationale = (
        f"{len(affected)} of {len(test_positions)} ordered test row(s) ({share:.1%}) carry "
        f"timestamps earlier than {horizon_end.isoformat()} - the declared "
        f"{horizon_days}-day horizon after the last training observation. Those predictions "
        "are made about a period whose events are already present in the training data."
    ) if share < 1 else (
        f"Every ordered test row ({len(affected)} of {len(test_positions)}) carries a "
        f"timestamp earlier than {horizon_end.isoformat()}, the declared {horizon_days}-day "
        "horizon after the last training observation. The evaluation happens entirely inside "
        "the horizon window, so training data covers the events being predicted."
    )

    finding = Finding(
        rule_id=RULE_ID,
        title=TITLE,
        severity=severity,
        severity_rationale=rationale,
        description=(
            f"The declared prediction horizon is {horizon_days} day(s) after the training "
            f"cutoff, but the split's time gap between the last training observation "
            f"({latest_train.isoformat()}) and the earliest test observation "
            f"({earliest_test.isoformat()}) is {_human_delta(gap)}. Test rows timestamped "
            "before the horizon end are predictions whose period is already represented in "
            "the training data - the lookahead the horizon is meant to prevent."
        ),
        evidence_summary=(
            f"{len(affected)} of {len(test_positions)} ordered test row(s) fall inside the "
            f"declared horizon; gap between the splits is {_human_delta(gap)} against a "
            f"declared horizon of {horizon_days} day(s)."
        ),
        counts=[
            Count(
                label="Test rows inside the declared horizon window",
                affected=len(affected),
                denominator=len(test_positions),
                unit="rows",
                note="Denominator covers only test rows whose timestamp parsed.",
            ),
            Count(
                label="Test rows whose timestamp could not be parsed (excluded)",
                affected=invalid_test,
                denominator=len(ctx.test_positions()),
                unit="rows",
            ),
        ],
        examples=[
            EvidenceExample(
                label=(
                    f"Test rows inside the horizon window ({len(affected)} total, first "
                    f"{min(len(affected), ctx.config.max_example_rows_per_example)} shown)"
                ),
                row_ids=[
                    ctx.row_id(p)
                    for p in affected[: ctx.config.max_example_rows_per_example]
                ],
                details={
                    "horizon_end": horizon_end.isoformat(),
                    "declared_horizon_days": str(horizon_days),
                    **({"horizon_note": ctx.config.temporal_horizon_note} if ctx.config.temporal_horizon_note else {}),
                },
            )
        ],
        example_total=1,
        examples_truncated=False,
        recommended_action=(
            "Re-split with a gap of at least the declared horizon (a purged chronological "
            "holdout), or revisit the declared horizon if it no longer matches the intended "
            "deployment."
        ),
        limitations=LIMITATIONS,
        assumptions=[
            f"The horizon is measured in calendar days from the latest training timestamp "
            f"({horizon_days} day(s) declared by the user).",
            "Event times are the timestamps in the selected column; label delay after the "
            "event is not modelled.",
        ],
    )
    return RuleOutput(status="evaluated", findings=[finding], metrics=metrics)


def _human_delta(delta: pd.Timedelta) -> str:
    seconds = delta.total_seconds()
    if seconds >= 86400 * 2:
        return f"{seconds / 86400:.1f} days"
    if seconds >= 3600 * 2:
        return f"{seconds / 3600:.1f} hours"
    if seconds >= 120:
        return f"{seconds / 60:.1f} minutes"
    if seconds < 0:
        return f"negative ({seconds:.0f} seconds)"
    return f"{seconds:.0f} seconds"


__all__ = ["LIMITATIONS", "RULE_ID", "TITLE", "run"]
