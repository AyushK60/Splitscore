"""High-level audit service.

A thin coordination layer so that the API, the evaluation script and the tests
all exercise exactly the same path: validate roles, build the split, run the
engine. Nothing here decides anything about leakage; it only composes the pieces
and turns validation errors into typed exceptions with the issues attached.
"""

from __future__ import annotations

from app.audit.canonical import ValueCanonicalizer
from app.audit.dataset import Dataset, SplitMasks
from app.audit.engine import build_canonicalizer, run_audit
from app.audit.roles import validate_roles
from app.audit.types import (
    AuditConfig,
    AuditResult,
    ColumnRoles,
    ResolvedRoles,
    RoleValidationResult,
    SplitAssignment,
    SplitConfig,
    SplitSummary,
)
from app.core.config import Settings
from app.core.errors import ValidationFailure
from app.splits.strategies import existing_split, generate_split, summarise


def resolve_or_raise(dataset: Dataset, roles: ColumnRoles) -> tuple[ResolvedRoles, RoleValidationResult]:
    """Validate roles and return the resolved set, raising on blocking errors."""
    validation = validate_roles(dataset, roles)
    if not validation.ok or validation.resolved is None:
        raise ValidationFailure(
            "The column roles are not usable for this dataset.",
            details={
                "issues": [issue.model_dump() for issue in validation.issues],
                "error_count": sum(1 for issue in validation.issues if issue.severity == "error"),
                "warning_count": sum(1 for issue in validation.issues if issue.severity == "warning"),
            },
        )
    return validation.resolved, validation


def build_existing_split(
    dataset: Dataset, resolved: ResolvedRoles
) -> tuple[SplitMasks, SplitSummary]:
    if resolved.split_column is None or resolved.train_value is None or resolved.test_value is None:
        raise ValidationFailure(
            "Auditing requires a split column with a train label and a test label. Select a split "
            "column, or generate a split instead.",
            details={
                "split_column": resolved.split_column,
                "train_value": resolved.train_value,
                "test_value": resolved.test_value,
                "hint": "If your file has no split column, choose 'create a split' in setup.",
            },
        )
    return existing_split(
        dataset,
        split_column=resolved.split_column,
        train_value=resolved.train_value,
        test_value=resolved.test_value,
    )


def build_generated_split(
    dataset: Dataset,
    *,
    resolved: ResolvedRoles,
    config: SplitConfig,
    canonicalizer: ValueCanonicalizer,
) -> tuple[SplitMasks, SplitSummary, SplitAssignment]:
    """Build one generated assignment and describe it for the report.

    The split is generated from the stored frame; the uploaded file itself is
    never modified, and the returned summary records the strategy, the seed and
    the achieved sizes so the run and its exports are reproducible.
    """
    if config.kind == "existing":
        raise ValidationFailure(
            "'existing' is not a generatable strategy: it reads the split column named in the "
            "roles. Leave 'generate' out to audit the split already in the file.",
            details={"strategy": config.kind},
        )

    generated = generate_split(
        dataset,
        resolved_entity=resolved.entity_column,
        resolved_target=resolved.target_column,
        resolved_timestamp=resolved.timestamp_column,
        config=config,
        canonicalizer=canonicalizer,
    )
    strategy_id = config.strategy_id or config.kind
    assignment_id = f"{dataset.dataset_id}:{strategy_id}"
    summary = summarise(
        strategy_id=strategy_id,
        label=config.label,
        kind=config.kind,
        generated=generated,
        assignment_id=assignment_id,
    )
    assignment = SplitAssignment(
        assignment_id=assignment_id,
        summary=summary,
        train_row_ids=generated.masks.row_ids(dataset, "train"),
        test_row_ids=generated.masks.row_ids(dataset, "test"),
    )
    return generated.masks, summary, assignment


def audit_existing_split(
    dataset: Dataset,
    *,
    roles: ColumnRoles,
    config: AuditConfig,
    settings: Settings,
) -> AuditResult:
    """Audit the split that is already present in the dataset."""
    resolved, _ = resolve_or_raise(dataset, roles)
    masks, summary = build_existing_split(dataset, resolved)
    return run_audit(
        dataset=dataset,
        roles=roles,
        resolved=resolved,
        config=config,
        masks=masks,
        split_summary=summary,
        settings=settings,
    )


def audit_generated_split(
    dataset: Dataset,
    *,
    roles: ColumnRoles,
    config: AuditConfig,
    split: SplitConfig,
    settings: Settings,
) -> tuple[AuditResult, SplitAssignment]:
    """Audit a split generated now from the dataset, returning its assignment."""
    resolved, _ = resolve_or_raise(dataset, roles)
    canonicalizer = build_canonicalizer(config)
    masks, summary, assignment = build_generated_split(
        dataset, resolved=resolved, config=split, canonicalizer=canonicalizer
    )
    result = run_audit(
        dataset=dataset,
        roles=roles,
        resolved=resolved,
        config=config,
        masks=masks,
        split_summary=summary,
        settings=settings,
    )
    return result, assignment


__all__ = [
    "audit_existing_split",
    "audit_generated_split",
    "build_existing_split",
    "build_generated_split",
    "resolve_or_raise",
]
