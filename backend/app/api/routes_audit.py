"""Audit execution and split comparison routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import get_context
from app.api.schemas import (
    AssignmentHandle,
    AuditRequest,
    AuditResponse,
    CompareRequest,
    CompareResponse,
)
from app.audit.service import (
    audit_existing_split,
    audit_generated_split,
    resolve_or_raise,
)
from app.core.errors import ValidationFailure
from app.core.logging_config import get_logger
from app.reports.csv_export import EXPORT_SANITIZATION_NOTE
from app.splits.comparison import SELECTION_NOTE, compare_splits

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["audit"])

EXPORT_PATH = "/api/exports/split/{assignment_id}.csv"


@router.post("/audit", response_model=AuditResponse)
def run_audit_route(request: AuditRequest) -> AuditResponse:
    """Audit the split in the file, or a split generated now from the rows."""
    context = get_context()
    dataset = context.store.get_dataset(request.dataset_id)

    assignment_handle: AssignmentHandle | None = None
    if request.generate is not None:
        result, assignment = audit_generated_split(
            dataset,
            roles=request.roles,
            config=request.config,
            split=request.generate,
            settings=context.settings,
        )
        context.store.put_assignment(assignment)
        summary = assignment.summary
        assignment_handle = AssignmentHandle(
            strategy_id=summary.strategy_id,
            assignment_id=assignment.assignment_id,
            label=summary.label,
            kind=summary.kind,
            train_rows=summary.train_rows,
            test_rows=summary.test_rows,
            download_path=EXPORT_PATH.format(assignment_id=assignment.assignment_id),
        )
    else:
        result = audit_existing_split(
            dataset, roles=request.roles, config=request.config, settings=context.settings
        )
    run_id = context.store.put_run(
        kind="audit",
        dataset_id=dataset.dataset_id,
        payload=result.model_dump(mode="json"),
        label=result.split.label,
    )
    logger.info(
        "Audit %s finished on %s: %d finding(s) in %.1f ms",
        run_id,
        dataset.dataset_id,
        result.evaluation.findings_total,
        result.duration_ms,
    )
    return AuditResponse(
        run_id=run_id,
        result=result,
        assignment=assignment_handle,
        export_hint=(
            "Download this run as JSON or a self-contained HTML report from the report export view. "
            "The run is held in memory only."
        ),
    )


@router.post("/splits/compare", response_model=CompareResponse)
def compare_splits_route(request: CompareRequest) -> CompareResponse:
    """Build every candidate split, re-run the checks, and tabulate the consequences."""
    context = get_context()
    dataset = context.store.get_dataset(request.dataset_id)
    resolved, validation = resolve_or_raise(dataset, request.roles)

    if not request.include_existing_split and not request.strategies:
        raise ValidationFailure(
            "Select at least one strategy to compare, or include the existing split.",
            details={"issues": [issue.model_dump() for issue in validation.issues]},
        )

    result, assignments, meta = compare_splits(
        dataset=dataset,
        roles=request.roles,
        resolved=resolved,
        strategies=request.strategies,
        config=request.config,
        settings=context.settings,
        audit_existing=request.include_existing_split,
    )

    handles: list[AssignmentHandle] = []
    for row in result.rows:
        if not row.supported:
            continue
        summary = next(
            (
                assignment.summary
                for assignment in assignments.values()
                if assignment.summary.strategy_id == row.strategy_id
            ),
            None,
        )
        if summary is None or summary.assignment_id is None:
            continue
        context.store.put_assignment(assignments[summary.assignment_id])
        handles.append(
            AssignmentHandle(
                strategy_id=row.strategy_id,
                assignment_id=summary.assignment_id,
                label=summary.label,
                kind=summary.kind,
                train_rows=summary.train_rows,
                test_rows=summary.test_rows,
                download_path=f"/api/exports/split/{summary.assignment_id}.csv",
            )
        )

    run_id = context.store.put_run(
        kind="comparison",
        dataset_id=dataset.dataset_id,
        payload=result.model_dump(mode="json"),
        label=f"{len(result.rows)} strategies",
    )
    logger.info(
        "Comparison %s finished on %s: %d supported, %d unsupported",
        run_id,
        dataset.dataset_id,
        len(handles),
        len(meta["unsupported"]),
    )
    return CompareResponse(
        run_id=run_id,
        result=result,
        assignments=handles,
        sanitization_note=EXPORT_SANITIZATION_NOTE,
        selection_note=SELECTION_NOTE,
    )


__all__ = ["router"]
