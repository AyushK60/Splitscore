"""SS-VRU-001: validation reuse within this session.

Label: this is a *process check*. Reusing the same test split for many
evaluate-and-adjust cycles is a leakage mechanism that lives in the workflow,
not in the data. The only evidence SplitScope actually has for it is its own
session run history, so this check reads — and only reads — the run records
the application accumulated in memory this session.

Honest states:

* **no history supplied** (the caller could not or did not provide run
  records, e.g. the synthetic evaluation harness): NOT EVALUATED. Absence of
  history is never reported as "no reuse".
* **fewer runs than the documented threshold**: evaluated, no finding; the
  count is in the metrics so the reader sees the basis.
* **at or above the threshold**: an info finding naming the run count, the
  split identity and the runs' findings, with the explicit limitation that
  inspecting a split repeatedly is common practice and only becomes a risk
  when decisions are made from it.
"""

from __future__ import annotations

from app.audit.rules.base import RuleContext, RuleOutput
from app.audit.types import Count, EvidenceExample, Finding, RunHistoryEntry, RuleMetric

RULE_ID = "SS-VRU-001"
TITLE = "Repeated evaluation of the same split in this session"

REUSE_THRESHOLD = 3  # prior runs of the same split before reuse is flagged
MAX_LISTED_RUNS = 5

LIMITATIONS = [
    "The evidence is this session's in-memory run history only. It resets when "
    "the server restarts, and it cannot see evaluations performed outside "
    "SplitScope — a notebook that tuned against the same test split leaves no "
    "record here.",
    "Auditing the same split repeatedly is normal, prudent practice while "
    "investigating a dataset. The finding marks the risk of making *selection "
    "decisions* from many test-set looks; it is info-severity by design.",
    "Split identity is matched on dataset id, split kind and the split column "
    "and label values. Two audits of one dataset with different generated "
    "splits are different splits and do not accumulate.",
]


def _same_split(entry: RunHistoryEntry, ctx: RuleContext) -> bool:
    if entry.dataset_id != ctx.dataset.dataset_id or ctx.split_summary is None:
        return False
    summary = ctx.split_summary
    if entry.split_kind != summary.kind:
        return False
    if summary.kind == "existing":
        return (
            entry.split_column == summary.split_column
            and entry.train_value == summary.train_value
            and entry.test_value == summary.test_value
        )
    # Generated splits: same strategy and identical achieved sizes from the
    # same seed are treated as the same split for reuse accounting.
    return (
        entry.train_rows == summary.train_rows
        and entry.test_rows == summary.test_rows
        and entry.split_kind == summary.kind
    )


def run(ctx: RuleContext) -> RuleOutput:
    history = ctx.run_history
    if history is None:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            (
                "No session run history was supplied to this audit, so validation reuse "
                "cannot be assessed. This is not evidence that no reuse happened: evaluations "
                "outside SplitScope leave no record here."
            ),
            run_history_size="not supplied",
        )

    prior = [entry for entry in history if _same_split(entry, ctx)]
    metrics: list[RuleMetric] = [
        RuleMetric(key="session_runs_total", label="Runs in this session", value=len(history)),
        RuleMetric(
            key="prior_runs_same_split",
            label="Prior runs of this exact split",
            value=len(prior),
        ),
        RuleMetric(key="reuse_threshold", label="Reuse threshold", value=REUSE_THRESHOLD),
    ]

    if len(prior) < REUSE_THRESHOLD:
        return RuleOutput(status="evaluated", findings=[], metrics=metrics)

    listed = prior[:MAX_LISTED_RUNS]
    findings = [
        Finding(
            rule_id=RULE_ID,
            title=TITLE,
            severity="info",
            severity_rationale=(
                f"This exact split has been audited {len(prior)} time(s) before in this "
                "session. Repeated evaluation of one test split is the workflow mechanism "
                "behind validation overfitting, but SplitScope cannot observe which decisions "
                "were made from these runs, so the result is an informational flag."
            ),
            description=(
                f"The session contains {len(prior)} prior audit run(s) of this same split "
                "(same dataset, same split definition). If model or configuration choices are "
                "being made based on these repeated evaluations, the test split is gradually "
                "becoming a training input — the classic validation-reuse risk. The split "
                "itself may be perfectly clean; the risk is in the process around it."
            ),
            evidence_summary=(
                f"{len(prior)} prior run(s) of this split in session history "
                f"(threshold {REUSE_THRESHOLD}); {len(history)} run(s) total this session."
            ),
            counts=[
                Count(
                    label="Prior session runs of this exact split",
                    affected=len(prior),
                    denominator=max(len(history), len(prior)),
                    unit="rows",
                    note="'rows' here counts runs, the check's unit of evidence; the "
                    "denominator is all runs in this session.",
                )
            ],
            examples=[
                EvidenceExample(
                    label=(
                        f"Prior runs of this split ({len(prior)} total, first "
                        f"{min(len(listed), MAX_LISTED_RUNS)} shown)"
                    ),
                    details={
                        f"run {entry.run_id}": (
                            f"{entry.kind}; {entry.findings_total} finding(s)"
                        )
                        for entry in listed
                    },
                )
            ],
            example_total=len(prior),
            examples_truncated=len(prior) > MAX_LISTED_RUNS,
            recommended_action=(
                "If choices are being made from these repeated evaluations, confirm the "
                "final configuration on a fresh holdout (or a cross-validation plan) that "
                "has not been inspected before."
            ),
            limitations=LIMITATIONS,
            assumptions=[
                "Session history is complete for this dataset; runs expiring from the "
                "in-memory store reduce the count.",
            ],
        )
    ]
    return RuleOutput(status="evaluated", findings=findings, metrics=metrics)


__all__ = ["LIMITATIONS", "REUSE_THRESHOLD", "RULE_ID", "TITLE", "run"]
