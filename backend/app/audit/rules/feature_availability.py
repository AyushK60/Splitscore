"""SS-AVL-001: declared feature-availability conflicts.

Label: this is a *ledger conformance check*. It evaluates the availability the
user declared for each predictor against the way the audit uses those columns.
It never infers availability: a column name, a type or a cardinality says
nothing about when a value becomes known in the real process that produces it.

What it reports:

* a feature declared ``after_prediction`` (future-only information used as a
  predictor) — a high-severity finding;
* a derived feature whose declared dependencies include an ``after_prediction``
  input — medium, because the future-only information reaches the model
  through the derived column;
* a feature declared ``unknown`` — info, so the gap is visible without
  pretending the column was cleared.

Undeclared features are counted and reported in the metrics; the ledger is an
instrument the analyst fills in, not a box the tool ticks for them.
"""

from __future__ import annotations

from app.audit.rules.base import RuleContext, RuleOutput
from app.audit.types import Count, EvidenceExample, Finding, RuleMetric

RULE_ID = "SS-AVL-001"
TITLE = "Feature availability ledger conflicts"

LIMITATIONS = [
    "This check evaluates declarations, not reality. A feature declared "
    "'at_prediction' is treated as available at the prediction point because the "
    "user said so; SplitScope cannot verify the claim from a CSV.",
    "Availability is declared per column. A column that is sometimes available "
    "and sometimes not (partial rollout, delayed feed) is represented by the "
    "pessimistic declaration the user chooses.",
    "'unknown' declarations are reported as an explicit gap. They are not "
    "treated as available and not treated as future-only.",
]


def run(ctx: RuleContext) -> RuleOutput:
    availability = ctx.config.feature_availability
    dependencies = ctx.config.derived_feature_dependencies
    features = list(ctx.resolved.feature_columns)

    declared = [column for column in features if column in availability]
    undeclared = [column for column in features if column not in availability]

    metrics: list[RuleMetric] = [
        RuleMetric(key="feature_count", label="Feature columns", value=len(features)),
        RuleMetric(key="declared_count", label="Features with a declared availability", value=len(declared)),
        RuleMetric(
            key="undeclared_count",
            label="Features without a declared availability",
            value=len(undeclared),
        ),
    ]
    for level in ("before_prediction", "at_prediction", "after_prediction", "unknown"):
        count = sum(1 for column in declared if availability[column] == level)
        metrics.append(
            RuleMetric(key=f"declared_{level}", label=f"Declared '{level}'", value=count)
        )

    if not declared and not dependencies:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "No feature-availability ledger was declared. SplitScope cannot infer when a "
            "predictor becomes known, so the future-information check is NOT EVALUATED rather "
            "than passed. Declare availability per feature in the audit configuration to run it.",
            declared_features="0",
            feature_columns=str(len(features)),
        )

    future_only = sorted(
        column for column in declared if availability[column] == "after_prediction"
    )
    unknown = sorted(column for column in declared if availability[column] == "unknown")

    # Derived features whose declared inputs include future-only columns.
    derived_exposed: dict[str, list[str]] = {}
    for feature, inputs in dependencies.items():
        if feature not in features:
            continue
        offending = [value for value in inputs if value in future_only]
        if offending:
            derived_exposed[feature] = offending

    findings: list[Finding] = []

    if future_only:
        findings.append(
            Finding(
                rule_id=RULE_ID,
                title=TITLE,
                severity="high",
                severity_rationale=(
                    f"{len(future_only)} predictor column(s) are declared to carry information "
                    "that only becomes available after the prediction or decision point. Using "
                    "them as predictors makes the offline evaluation unrepresentative of "
                    "deployment, regardless of how well the model scores."
                ),
                description=(
                    "The feature-availability ledger declares that these predictors are only "
                    "known after the prediction or decision point: "
                    + ", ".join(future_only)
                    + ". A model trained with access to future-only columns learns from "
                    "information the deployed decision cannot have, so any measured performance "
                    "overstates what the system would achieve."
                ),
                evidence_summary=(
                    f"{len(future_only)} of {len(features)} feature column(s) declared "
                    f"'after_prediction'; {len(undeclared)} feature(s) have no declaration."
                ),
                counts=[
                    Count(
                        label="Features declared available only after prediction",
                        affected=len(future_only),
                        denominator=len(features),
                        unit="columns",
                        note="Denominator is the full feature set of this audit.",
                    ),
                    Count(
                        label="Features without any availability declaration",
                        affected=len(undeclared),
                        denominator=len(features),
                        unit="columns",
                    ),
                ],
                examples=[
                    EvidenceExample(
                        label="Declared future-only predictors",
                        details={
                            "columns": ", ".join(future_only),
                            "declared_as": "after_prediction",
                        },
                    )
                ],
                example_total=1,
                examples_truncated=False,
                recommended_action=(
                    "Remove these columns from the feature set, or replace them with values "
                    "that are genuinely known at the decision point (for example values as of "
                    "the prediction timestamp). Re-run the audit afterwards."
                ),
                limitations=LIMITATIONS,
                assumptions=[
                    "The declaration reflects the real production process: 'after_prediction' "
                    "means the value is not knowable when the decision is made.",
                    "The declared columns are used as predictors in the model this audit is "
                    "for; SplitScope audits the declared feature set.",
                ],
            )
        )

    for feature, offending in sorted(derived_exposed.items()):
        findings.append(
            Finding(
                rule_id=RULE_ID,
                title=TITLE,
                severity="medium",
                severity_rationale=(
                    f"The derived feature '{feature}' declares dependencies "
                    f"({', '.join(offending)}) that the ledger marks future-only, so the "
                    "future-only information reaches the model through this column."
                ),
                description=(
                    f"'{feature}' is declared as a derived feature of "
                    f"{', '.join(offending)}, which the availability ledger marks as available "
                    "only after the prediction point. The derived column therefore carries "
                    "future-only information even if its own name and values look innocuous."
                ),
                evidence_summary=(
                    f"Derived feature '{feature}' depends on {len(offending)} future-only "
                    "column(s) per the declared dependency list."
                ),
                counts=[
                    Count(
                        label="Future-only inputs behind this derived feature",
                        affected=len(offending),
                        denominator=len(dependencies.get(feature, [])),
                        unit="columns",
                    )
                ],
                examples=[
                    EvidenceExample(
                        label=f"Derived feature exposed to future-only inputs: {feature}",
                        details={
                            "derived_feature": feature,
                            "future_only_inputs": ", ".join(offending),
                        },
                    )
                ],
                example_total=1,
                examples_truncated=False,
                recommended_action=(
                    "Recompute this derived feature from inputs that are available at the "
                    "prediction point, or drop it from the feature set."
                ),
                limitations=LIMITATIONS,
                assumptions=[
                    "The declared dependency list is complete; an undeclared dependency is not "
                    "checked because SplitScope does not derive feature lineage itself.",
                ],
            )
        )

    if unknown:
        findings.append(
            Finding(
                rule_id=RULE_ID,
                title=TITLE,
                severity="info",
                severity_rationale=(
                    f"{len(unknown)} predictor column(s) have an 'unknown' availability "
                    "declaration. This is an explicit gap in the ledger, not a finding of "
                    "leakage."
                ),
                description=(
                    "These predictors are declared with unknown prediction-time availability: "
                    + ", ".join(unknown)
                    + ". Until the availability is established, the audit cannot say whether "
                    "they are safe to use; the honest state is 'unresolved', not 'passed'."
                ),
                evidence_summary=(
                    f"{len(unknown)} feature column(s) declared 'unknown' out of "
                    f"{len(features)} features."
                ),
                counts=[
                    Count(
                        label="Features with unknown declared availability",
                        affected=len(unknown),
                        denominator=len(features),
                        unit="columns",
                    )
                ],
                examples=[
                    EvidenceExample(
                        label="Predictors with unknown availability",
                        details={"columns": ", ".join(unknown), "declared_as": "unknown"},
                    )
                ],
                example_total=1,
                examples_truncated=False,
                recommended_action=(
                    "Resolve the availability of these columns with the owner of the producing "
                    "process, then update the ledger and re-run the audit."
                ),
                limitations=LIMITATIONS,
                assumptions=[
                    "'unknown' is an honest declaration of missing knowledge, distinct from "
                    "'available' and from 'future-only'.",
                ],
            )
        )

    return RuleOutput(status="evaluated", findings=findings, metrics=metrics)


__all__ = ["LIMITATIONS", "RULE_ID", "TITLE", "run"]
