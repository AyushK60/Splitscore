"""SS-PPF-001: preprocessing fit boundary (declared).

Scientific constraint this rule exists for: a raw CSV cannot establish where a
scaler, imputer, encoder or feature selector was fitted. A pipeline fitted on
the full dataset leaks test information into training transforms, and no
amount of split hygiene elsewhere repairs it.

SplitScope does not execute or instrument preprocessing, so:

* with **no declaration**, the check is NOT EVALUATED — never passed. The
  reason names exactly what is missing and how to declare it;
* with a **declaration**, each step is judged on its declared ``fit_context``:
  ``full_dataset`` is a high finding; ``unknown`` / ``not_recorded`` are
  medium findings (the boundary cannot be verified); ``train_only`` is clean
  *as declared*.

Only a future version that actually executes the preprocessing can claim
verified pipeline isolation. Until then this rule's vocabulary is
"declared" and "not evaluated" — never "verified".
"""

from __future__ import annotations

from app.audit.rules.base import RuleContext, RuleOutput
from app.audit.types import Count, EvidenceExample, Finding, RuleMetric

RULE_ID = "SS-PPF-001"
TITLE = "Preprocessing fit boundary (declared)"

LIMITATIONS = [
    "This check evaluates a declaration. SplitScope does not run the "
    "preprocessing, so 'train_only' means the user recorded train-only "
    "fitting — not that SplitScope verified it.",
    "Declared step lists can be incomplete. An undeclared step is invisible to "
    "this check; completeness of the declaration is the user's responsibility.",
    "The check does not inspect transformer parameters (means, medians, "
    "encodings). Only the declared fit context is judged.",
]


def run(ctx: RuleContext) -> RuleOutput:
    declaration = ctx.config.preprocessing
    if declaration is None or not declaration.steps:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            (
                "No preprocessing declaration was provided. SplitScope does not instrument "
                "preprocessing execution, and a raw CSV cannot establish where a scaler, "
                "imputer or feature selector was fitted — so the pipeline fit boundary is NOT "
                "EVALUATED, not passed. Declare the preprocessing steps and their fit context "
                "in the audit configuration to record the boundary."
            ),
            declared_steps="0",
        )

    steps = declaration.steps
    metrics: list[RuleMetric] = [
        RuleMetric(key="declared_steps", label="Declared preprocessing steps", value=len(steps)),
        RuleMetric(
            key="train_only_steps",
            label="Steps declared fitted on training data only",
            value=sum(1 for step in steps if step.fit_context == "train_only"),
        ),
        RuleMetric(
            key="full_dataset_steps",
            label="Steps declared fitted on the full dataset",
            value=sum(1 for step in steps if step.fit_context == "full_dataset"),
        ),
        RuleMetric(
            key="unverified_steps",
            label="Steps with unrecorded or unknown fit context",
            value=sum(
                1 for step in steps if step.fit_context in ("unknown", "not_recorded")
            ),
        ),
    ]

    offending = [
        step for step in steps if step.fit_context in ("full_dataset", "unknown", "not_recorded")
    ]
    if not offending:
        return RuleOutput(status="evaluated", findings=[], metrics=metrics)

    full = [step.name for step in offending if step.fit_context == "full_dataset"]
    unverified = [step.name for step in offending if step.fit_context != "full_dataset"]

    severity = "high" if full else "medium"
    rationale = (
        f"{len(full)} declared preprocessing step(s) are recorded as fitted on the full "
        "dataset, so their parameters encode test-side information."
        if full
        else f"{len(unverified)} declared preprocessing step(s) have an unrecorded or unknown "
        "fit context, so pipeline isolation cannot be confirmed even as a declaration."
    )

    parts: list[str] = []
    if full:
        parts.append(
            f"steps {', '.join(full)} are declared as fitted on the full dataset "
            "(train + test). Their fitted parameters (means, quantiles, category maps, "
            "selected features) are computed partly from test rows, which is leakage "
            "regardless of how the split itself is drawn."
        )
    if unverified:
        parts.append(
            f"steps {', '.join(unverified)} have no recorded fit context, so the "
            "declaration cannot confirm isolation."
        )
    description = (
        "The declared preprocessing pipeline's fit boundary is not clean: " + " ".join(parts)
    )
    findings = [
        Finding(
            rule_id=RULE_ID,
            title=TITLE,
            severity=severity,
            severity_rationale=rationale,
            description=description,
            evidence_summary=(
                f"{len(offending)} of {len(steps)} declared step(s) are not cleanly fitted on "
                "training data only (per declaration)."
            ),
            counts=[
                Count(
                    label="Declared steps not fitted on training data only",
                    affected=len(offending),
                    denominator=len(steps),
                    unit="columns",
                    note="'columns' here counts declared pipeline steps, the check's unit "
                    "of evidence.",
                )
            ],
            examples=[
                EvidenceExample(
                    label="Declared preprocessing steps with a problematic fit boundary",
                    details={
                        "full_dataset_steps": ", ".join(full) if full else "(none)",
                        "unverified_steps": ", ".join(unverified) if unverified else "(none)",
                        **(
                            {"declaration_note": declaration.note}
                            if declaration.note
                            else {}
                        ),
                    },
                )
            ],
            example_total=1,
            examples_truncated=False,
            recommended_action=(
                "Refit every preprocessing step on training data only inside the modelling "
                "pipeline (fit at train time, apply unchanged at test time). Update the "
                "declaration and re-run the audit."
            ),
            limitations=LIMITATIONS,
            assumptions=[
                "The declaration is complete and accurate; SplitScope does not execute the "
                "pipeline to verify it.",
            ],
        )
    ]
    return RuleOutput(status="evaluated", findings=findings, metrics=metrics)


__all__ = ["LIMITATIONS", "RULE_ID", "TITLE", "run"]
