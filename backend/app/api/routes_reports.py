"""Report exports, split-assignment CSV exports and run introspection."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import get_context
from app.api.schemas import DossierRequest, ReportRequest, RunListResponse
from app.core.errors import NotFoundError, ValidationFailure
from app.reports.csv_export import EXPORT_SANITIZATION_NOTE, build_assignment_csv
from app.reports.dossier import build_dossier
from app.reports.dossier_html import render_dossier_html
from app.reports.html_report import render_audit_html, render_comparison_html
from app.reports.json_report import build_audit_report, build_comparison_report, report_filename
from app.research.profiling import build_profile
from app.research.studies import roles_from_column_roles, study_payload
from app.synthetic.manifest import recommended_roles as demo_recommended_roles

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


@router.post("/datasets/{dataset_id}/reports/dossier")
def export_dossier(
    dataset_id: str,
    request: DossierRequest,
    format: str = "json",
) -> Response:
    """Compose (and optionally download) the S7 dossier from named stored runs.

    The body is identical for both formats; ``format=json`` returns the API
    object, while ``format=html`` wraps that same object in a self-contained
    printable document. Supplying an ID of the wrong kind is a validation
    failure, not a silently skipped section.
    """
    if format not in {"json", "html"}:
        raise ValidationFailure(
            "Dossier format must be 'json' or 'html'.",
            details={"format": format},
        )
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    record = context.studies.get(dataset_id)
    if record is None and dataset.demo is not None:
        demo_roles = demo_recommended_roles(dataset.demo.demo_id)
        record = context.studies.get_or_create(
            dataset_id,
            seed_roles=roles_from_column_roles(demo_roles),
            seed_split_labels=(demo_roles.split_train_value, demo_roles.split_test_value),
        )
    elif record is None:
        record = context.studies.get_or_create(dataset_id)
    study = study_payload(record, dataset)
    profile = build_profile(
        dataset,
        assignments=record.role_assignments,
        declarations=record.column_declarations,
    )

    def stored_run(run_id: str | None, kind: str, *, label: str) -> dict | None:
        if not run_id:
            return None
        stored = context.store.get_run(run_id)
        if stored.dataset_id != dataset_id:
            raise NotFoundError(
                f"That {label} belongs to a different dataset.",
                details={"run_id": run_id, "dataset_id": stored.dataset_id},
            )
        if stored.kind != kind:
            raise ValidationFailure(
                f"That run is not a {label} run.",
                details={"run_id": run_id, "kind": stored.kind},
            )
        return stored

    audit_run = stored_run(request.audit_run_id, "audit", label="leakage audit")
    comparison_run = stored_run(
        request.comparison_run_id, "comparison", label="split comparison"
    )
    model_runs = []
    seen_models: set[str] = set()
    for run_id in request.model_run_ids:
        if run_id in seen_models:
            continue
        seen_models.add(run_id)
        stored = stored_run(run_id, "model", label="model")
        if stored is not None:
            model_runs.append(
                {"run_id": stored.run_id, "label": stored.label, "payload": stored.payload}
            )

    # S10-B: stored estimation runs (S9A/S9C) with cross-dataset and staleness
    # refusal. A run computed against different dataset bytes is refused
    # outright — the dossier never silently substitutes numbers from another
    # cohort, and never presents a stale result as current.
    estimation_runs: list[dict[str, Any]] = []
    seen_estimation: set[str] = set()
    graph_record: dict[str, Any] | None = None
    for run_id in request.estimation_run_ids:
        if run_id in seen_estimation:
            continue
        seen_estimation.add(run_id)
        stored = stored_run(run_id, "estimation", label="estimation")
        if stored is None:
            continue
        repro = stored.payload.get("reproducibility") or {}
        recorded = repro.get("dataset_fingerprint_sha256")
        if recorded and recorded != dataset.fingerprint_sha256:
            raise ValidationFailure(
                "The estimation run named for this dossier was computed against a dataset whose "
                "content has since changed. It cannot be included as current; re-run the analysis "
                "and select the new run.",
                details={"run_id": run_id, "recorded_fingerprint": recorded,
                         "current_fingerprint": dataset.fingerprint_sha256},
            )
        graph_id = repro.get("graph_id")
        if graph_id:
            try:
                record = context.causal_graphs.get(dataset_id, graph_id)
            except NotFoundError:
                record = None
            if record is not None and graph_record is None:
                graph_record = {
                    "graph_id": record.graph_id,
                    "revision": record.revision,
                    "spec_fingerprint_sha256": record.fingerprint,
                    "spec": record.spec.model_dump(mode="json") if hasattr(record.spec, "model_dump") else record.spec,
                }
        estimation_runs.append({**stored.payload, "run_id": stored.run_id})

    try:
        report = build_dossier(
            dataset=dataset,
            study=study,
            profile=profile,
            audit=(
                {**audit_run.payload, "run_id": audit_run.run_id} if audit_run else None
            ),
            comparison=(
                {**comparison_run.payload, "run_id": comparison_run.run_id}
                if comparison_run
                else None
            ),
            models=model_runs,
            requested_sections=request.sections,
            estimation_runs=estimation_runs,
            graph_record=graph_record,
            presentation=request.presentation,
        )
    except ValueError as exc:
        raise ValidationFailure(str(exc)) from exc

    if format == "html":
        body = render_dossier_html(report)
        name = report_filename("dossier", dataset.name)
        return Response(
            content=body,
            media_type="text/html; charset=utf-8",
            headers=_download_headers(f"{name}.html"),
        )

    payload = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    name = report_filename("dossier", dataset.name)
    return Response(
        content=payload,
        media_type="application/json; charset=utf-8",
        headers=_download_headers(f"{name}.json"),
    )


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
