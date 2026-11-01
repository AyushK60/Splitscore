"""SS-ENT-001: entity / group overlap between the two splits.

This rule answers a narrower question than "is the split wrong": *do the same
entities appear on both sides?* Whether that matters depends on the evaluation
the user intends, which is why the finding states the condition rather than
declaring a verdict.
"""

from __future__ import annotations

from app.audit.rules.base import RuleContext, RuleOutput, bound_examples, cap_values
from app.audit.tokens import column_missing_mask, column_tokens
from app.audit.types import Count, EvidenceExample, Finding, RuleMetric

RULE_ID = "SS-ENT-001"
TITLE = "Entity overlap between train and test splits"

LIMITATIONS = [
    "Overlap is measured on the entity column exactly as recorded. Two identifiers for the "
    "same real entity (for example 'A-1' and 'a-1', or a renamed account) are not matched.",
    "Rows with an empty entity value cannot be attributed to any entity. They are counted "
    "separately and are never merged into a single synthetic entity, so a split on missing "
    "entity identifiers cannot be validated by this rule.",
    "Overlap is not automatically an error. It is an error only relative to an evaluation that "
    "requires generalisation to entities not seen during training.",
    "This rule does not examine whether the entity column actually identifies the unit of "
    "deployment; that judgement is the user's.",
]


def run(ctx: RuleContext) -> RuleOutput:
    entity_column = ctx.resolved.entity_column
    if entity_column is None:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "No entity/group column was selected, so the split cannot be checked for shared groups.",
            entity_column="(none)",
        )

    frame = ctx.dataset.frame
    tokens = column_tokens(frame, entity_column, ctx.canonicalizer)
    missing = column_missing_mask(frame, entity_column, ctx.canonicalizer)

    train_positions = ctx.train_positions()
    test_positions = ctx.test_positions()

    train_missing_rows = sum(1 for p in train_positions if missing[p])
    test_missing_rows = sum(1 for p in test_positions if missing[p])

    train_groups: dict[str, list[int]] = {}
    for p in train_positions:
        if not missing[p]:
            train_groups.setdefault(tokens[p], []).append(p)
    test_groups: dict[str, list[int]] = {}
    for p in test_positions:
        if not missing[p]:
            test_groups.setdefault(tokens[p], []).append(p)

    shared = sorted(
        (token for token in train_groups if token in test_groups),
        key=lambda token: (-(len(train_groups[token]) + len(test_groups[token])), token),
    )

    affected_train_rows = sum(len(train_groups[t]) for t in shared)
    affected_test_rows = sum(len(test_groups[t]) for t in shared)

    metrics = [
        # Emitted unconditionally, including when zero, so the split comparison
        # table can read one stable metric key per check.
        RuleMetric(
            key="entity_overlap_test_rows",
            label="Test rows belonging to an entity also present in train",
            value=affected_test_rows,
            unit="rows",
        ),
        RuleMetric(
            key="entity_overlap_test_share",
            label="Share of the test split belonging to a shared entity",
            value=round(affected_test_rows / max(len(test_positions), 1), 6),
        ),
        RuleMetric(key="entity_column", label="Entity column", value=entity_column),
        RuleMetric(
            key="train_distinct_groups", label="Distinct entities in train", value=len(train_groups)
        ),
        RuleMetric(
            key="test_distinct_groups", label="Distinct entities in test", value=len(test_groups)
        ),
        RuleMetric(key="shared_groups", label="Entities in both splits", value=len(shared)),
        RuleMetric(
            key="unlabelled_entity_rows_train",
            label="Train rows with no entity identifier",
            value=train_missing_rows,
            unit="rows",
        ),
        RuleMetric(
            key="unlabelled_entity_rows_test",
            label="Test rows with no entity identifier",
            value=test_missing_rows,
            unit="rows",
        ),
    ]

    if not shared:
        return RuleOutput(status="evaluated", findings=[], metrics=metrics)

    test_share = affected_test_rows / max(len(test_positions), 1)
    if test_share >= ctx.config.entity_overlap_high_test_share:
        severity = "high"
        rationale = (
            f"{len(shared)} entity value(s) appear in both splits, covering {affected_test_rows} "
            f"test rows ({test_share:.1%} of the test split), which is at or above the configured "
            f"{ctx.config.entity_overlap_high_test_share:.0%} threshold. When the intended "
            "evaluation is performance on entities not seen during training, this share is large "
            "enough that the test split no longer measures it."
        )
    else:
        severity = "medium"
        rationale = (
            f"{len(shared)} entity value(s) appear in both splits, covering {affected_test_rows} "
            f"test rows ({test_share:.1%} of the test split), below the configured "
            f"{ctx.config.entity_overlap_high_test_share:.0%} threshold for a high-severity "
            "finding. The overlap is definite but affects a smaller share of the test set."
        )

    examples: list[EvidenceExample] = []
    for token in shared:
        in_train = train_groups[token]
        in_test = test_groups[token]
        examples.append(
            EvidenceExample(
                label=f"Entity {token!r} appears in both splits",
                row_ids=cap_values([ctx.row_id(p) for p in in_train], ctx)
                + cap_values([ctx.row_id(p) for p in in_test], ctx),
                details={
                    entity_column: token,
                    "train_rows_for_entity": str(len(in_train)),
                    "test_rows_for_entity": str(len(in_test)),
                    "train_first_row_ids": ", ".join(ctx.row_id(p) for p in in_train[:3]),
                    "test_first_row_ids": ", ".join(ctx.row_id(p) for p in in_test[:3]),
                },
            )
        )
    kept, total, truncated = bound_examples(examples, ctx)

    finding = Finding(
        rule_id=RULE_ID,
        title=TITLE,
        severity=severity,  # type: ignore[arg-type]
        severity_rationale=rationale,
        description=(
            f"The entity column {entity_column!r} takes a value in the training split that also "
            "occurs in the test split. If the deployment setting requires generalisation to "
            "entities that were never seen during training (a new customer, patient, device or "
            "document), then test rows belonging to a training entity are not out-of-entity "
            "samples: any entity-level signal memorised during training is still available at "
            "test time. When the entity column merely groups repeated measurements of rows that "
            "are themselves the unit of prediction, overlap is expected and is not a defect."
        ),
        evidence_summary=(
            f"{len(shared)} entity value(s) are shared between the splits, covering "
            f"{affected_test_rows} test row(s) ({test_share:.1%} of the test split) and "
            f"{affected_train_rows} train row(s)."
        ),
        counts=[
            Count(
                label="Entity values present in both splits",
                affected=len(shared),
                denominator=len(test_groups),
                unit="groups",
                note="Denominator is the number of distinct non-missing entity values in the test split.",
            ),
            Count(
                label="Test rows belonging to an entity also present in train",
                affected=affected_test_rows,
                denominator=len(test_positions),
                unit="rows",
            ),
            Count(
                label="Train rows belonging to an entity also present in test",
                affected=affected_train_rows,
                denominator=len(train_positions),
                unit="rows",
            ),
            Count(
                label="Test rows with an empty entity identifier (counted separately)",
                affected=test_missing_rows,
                denominator=len(test_positions),
                unit="rows",
                note="Empty identifiers are not treated as one shared entity, so these rows are "
                "excluded from the overlap measurement rather than inflating it.",
            ),
            Count(
                label="Train rows with an empty entity identifier (counted separately)",
                affected=train_missing_rows,
                denominator=len(train_positions),
                unit="rows",
            ),
        ],
        examples=kept,
        example_total=total,
        examples_truncated=truncated,
        recommended_action=(
            "If the evaluation must generalise to unseen entities, replace this split with a "
            "group holdout on the same entity column (available in the split comparison) and "
            "re-run this audit. Do not treat the overlap as a dataset defect without checking "
            "which entity the deployment setting actually predicts for."
        ),
        limitations=LIMITATIONS,
        assumptions=[
            "The selected entity column is the unit for which generalisation matters.",
            "Entity values are comparable across rows as literal strings, after the configured "
            "whitespace stripping.",
            "An empty entity value carries no entity information.",
        ],
    )

    return RuleOutput(status="evaluated", findings=[finding], metrics=metrics)


__all__ = ["RULE_ID", "TITLE", "run"]
