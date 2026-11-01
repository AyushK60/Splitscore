"""Report exports, split-assignment CSV exports and run introspection."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import get_context
from app.api.schemas import ReportRequest, RunListResponse
from app.core.errors import ValidationFailure
from app.reports.csv_export import EXPORT_SANITIZATION_NOTE, build_assignment_csv
from app.reports.html_report import render_audit_html, render_comparison_html
from app.reports.json_report import build_audit_report, build_comparison_report, report_filename

router = APIRouter(prefix="/api", tags=["reports"])

SAFE_ID = re.compile(r"^[A-Za-z0-9:_-]{1,120}$")


def _download_headers(filename: str) -> dict[str, str]:
    return {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


def _run_payload(run_id: str):
    context = get_context()
    stored = context.store.get_run(run_id)
    dataset = context.store.get_dataset(stored.dataset_id)
    return context, stored, dataset


@router.post("/reports/json")
def export_json(request: ReportRequest) -> Response:
    _, stored, _dataset = _run_payload(request.run_id)
    if stored.kind == "audit":
        payload = build_audit_report(_rehydrate_audit(stored.payload), run_id=stored.run_id)
        name = report_filename("audit", stored.payload["dataset"]["name"])
    else:
        payload = build_comparison_report(_rehydrate_comparison(stored.payload), run_id=stored.run_id)
        name = report_filename("comparison", stored.payload["dataset"]["name"])

    body = json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers=_download_headers(f"{name}.json"),
    )


@router.post("/reports/html")
def export_html(request: ReportRequest) -> Response:
    _, stored, _dataset = _run_payload(request.run_id)
    if stored.kind == "audit":
        result = _rehydrate_audit(stored.payload)
        body = render_audit_html(result, run_id=stored.run_id)
        name = report_filename("audit", stored.payload["dataset"]["name"])
    else:
        result = _rehydrate_comparison(stored.payload)
        body = render_comparison_html(result, run_id=stored.run_id)
        name = report_filename("comparison", stored.payload["dataset"]["name"])

    return Response(
        content=body,
        media_type="text/html; charset=utf-8",
        headers=_download_headers(f"{name}.html"),
    )


@router.get("/exports/split/{assignment_id}.csv")
def export_assignment(assignment_id: str) -> Response:
    if not SAFE_ID.match(assignment_id):
        raise ValidationFailure(
            "That assignment identifier is not in the expected form.",
            details={"assignment_id": assignment_id},
        )
    context = get_context()
    assignment = context.store.get_assignment(assignment_id)
    body = build_assignment_csv(assignment, include_header_note=True)
    name = f"splitscope-split-{assignment.summary.kind}-{assignment.summary.strategy_id}.csv".replace(
        ":", "-"
    )
    headers = _download_headers(name)
    headers["X-SplitScope-Export-Note"] = EXPORT_SANITIZATION_NOTE
    return Response(content=body, media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/runs", response_model=RunListResponse)
def list_runs() -> RunListResponse:
    context = get_context()
    stats = context.store.stats()
    return RunListResponse(
        runs=context.store.list_runs(),
        store={
            "datasets": stats.datasets,
            "runs": stats.runs,
            "assignments": stats.assignments,
            "total_bytes": stats.total_bytes,
            "limits": stats.limits,
            "evictions": stats.evictions,
            "expirations": stats.expirations,
        },
    )


def _rehydrate_audit(payload: dict):
    from app.audit.types import AuditResult

    return AuditResult.model_validate(payload)


def _rehydrate_comparison(payload: dict):
    from app.audit.types import ComparisonResult

    return ComparisonResult.model_validate(payload)


__all__ = ["router"]
