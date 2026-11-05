"""Causal effect estimation routes (S9A).

The estimation endpoints extend the S8A/S8C route rules unchanged: the dataset
must be live (typed 410 when expired/evicted), a graph id under a different
dataset is 404, and every failure returns the single structured error
envelope. Estimation runs are stored in the existing bounded run store with
``kind="estimation"``; a stored run is re-checked against the dataset and
graph fingerprints on retrieval and reported stale when either changed.

The routes never estimate anything themselves — all numerics live in
:mod:`app.causal.estimation.service`, whose identification gate runs before
every estimation. No user-supplied code, payload or function can reach the
estimators: the request selects among three named, server-defined estimators,
nothing else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_context
from app.api.routes_causal import _dataset
from app.api.routes_causal_identification import _envelope, _require_validated_spec
from app.causal.estimation.contracts import (
    ESTIMATION_SCHEMA_VERSION,
    EstimationLimits,
    EstimationRequest,
)
from app.causal.estimation.service import (
    ESTIMATION_VERSION,
    mark_staleness,
    run_estimation,
)
from app.core.errors import NotFoundError
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["causal-estimation"])


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EstimationValidateRequest(_Model):
    """A readiness probe: the full estimation request, nothing executed."""

    request: EstimationRequest


class EstimationRunRequest(_Model):
    """Run one named estimator under the fully specified analysis."""

    request: EstimationRequest
    estimator: Literal["regression_adjustment", "ipw", "aipw"]
    label: str = Field(default="", max_length=120)


class EstimationCompareRequest(_Model):
    """Run every supported estimator under one identical analysis."""

    request: EstimationRequest
    label: str = Field(default="", max_length=120)


def _record(dataset_id: str, graph_id: str):
    context = get_context()
    dataset = _dataset(dataset_id)
    record = context.causal_graphs.get(dataset.dataset_id, graph_id)
    return dataset, record


@router.post("/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/validate")
def estimation_validate(
    dataset_id: str, graph_id: str, body: EstimationValidateRequest
) -> dict[str, Any]:
    """Check estimation readiness without computing anything.

    Runs the full identification gate (fingerprint, structural validation,
    column anchors, S8C backdoor verdict) and reports the cohort that *would*
    be analysed, with no estimate attached.
    """
    from app.causal.estimation.preparation import prepare_cohort
    from app.causal.estimation.service import run_identification_gate

    dataset, record = _record(dataset_id, graph_id)
    _require_validated_spec(record.spec, dataset)
    request = body.request
    gate = run_identification_gate(dataset, record, request)
    treatment_column = next(
        node.column for node in record.spec.nodes if node.node_id == request.treatment_node
    )
    outcome_column = next(
        node.column for node in record.spec.nodes if node.node_id == request.outcome_node
    )
    adjustment_columns = [
        node.column
        for node in record.spec.nodes
        if node.node_id in set(request.adjustment_nodes)
    ]
    cohort_preview = prepare_cohort(
        dataset,
        request,
        treatment_column=treatment_column,
        outcome_column=outcome_column,
        covariate_columns=adjustment_columns,
    ).to_payload()
    logger.info(
        "estimation readiness on %s: gate passed, %d cohort row(s)",
        record.graph_id,
        cohort_preview["rows_final"],
    )
    return _envelope(
        record,
        {
            "estimation_version": ESTIMATION_VERSION,
            "estimation_schema_version": ESTIMATION_SCHEMA_VERSION,
            "readiness": "ready",
            "gate": gate,
            "cohort_preview": cohort_preview,
            "limits": EstimationLimits.as_dict(),
            "note": "Nothing was estimated and nothing was stored.",
        },
    )


@router.post("/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/run")
def estimation_run(dataset_id: str, graph_id: str, body: EstimationRunRequest) -> dict[str, Any]:
    """Run one estimator; store the result as a bounded estimation run."""
    context = get_context()
    dataset, record = _record(dataset_id, graph_id)
    _require_validated_spec(record.spec, dataset)
    payload = run_estimation(
        dataset,
        record,
        body.request,
        estimator_names=[body.estimator],
    )
    payload["created_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    run_id = context.store.put_run(
        kind="estimation",
        dataset_id=dataset.dataset_id,
        payload=payload,
        label=body.label
        or f"{body.estimator}: {body.request.treatment_node} → {body.request.outcome_node}",
    )
    payload["run_id"] = run_id
    logger.info(
        "estimation run %s on %s: %s",
        run_id,
        record.graph_id,
        body.estimator,
    )
    return payload


@router.post("/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/compare")
def estimation_compare(
    dataset_id: str, graph_id: str, body: EstimationCompareRequest
) -> dict[str, Any]:
    """Run all three estimators under one identical analysis and compare them."""
    context = get_context()
    dataset, record = _record(dataset_id, graph_id)
    _require_validated_spec(record.spec, dataset)
    payload = run_estimation(
        dataset,
        record,
        body.request,
        estimator_names=["regression_adjustment", "ipw", "aipw"],
        compare=True,
    )
    payload["created_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    run_id = context.store.put_run(
        kind="estimation",
        dataset_id=dataset.dataset_id,
        payload=payload,
        label=body.label
        or f"comparison: {body.request.treatment_node} → {body.request.outcome_node}",
    )
    payload["run_id"] = run_id
    logger.info("estimation comparison %s on %s", run_id, record.graph_id)
    return payload


@router.get("/datasets/{dataset_id}/estimation-runs")
def list_estimation_runs(dataset_id: str) -> dict[str, Any]:
    """Estimation runs for one live dataset, newest first."""
    context = get_context()
    dataset = _dataset(dataset_id)
    runs = [
        entry
        for entry in context.store.list_runs()
        if entry["kind"] == "estimation" and entry["dataset_id"] == dataset.dataset_id
    ]
    return {"dataset_id": dataset.dataset_id, "runs": runs}


@router.get("/datasets/{dataset_id}/estimation-runs/{run_id}")
def get_estimation_run(dataset_id: str, run_id: str) -> dict[str, Any]:
    """Retrieve one stored estimation run, re-checked for staleness."""
    context = get_context()
    dataset = _dataset(dataset_id)
    run = context.store.get_run(run_id)
    if run.dataset_id != dataset.dataset_id:
        raise NotFoundError(
            "That estimation run belongs to a different dataset.",
            details={"run_id": run_id, "dataset_id": dataset.dataset_id},
        )
    if run.kind != "estimation":
        raise NotFoundError(
            "That run is not an estimation run.",
            details={"run_id": run_id, "kind": run.kind},
        )
    graph_id = run.payload.get("reproducibility", {}).get("graph_id")
    try:
        record = context.causal_graphs.get(dataset.dataset_id, graph_id)
    except NotFoundError:
        annotated = dict(run.payload)
        annotated["stale"] = True
        annotated["staleness_reason"] = (
            "The graph this estimate was computed against no longer exists for this dataset."
        )
        return annotated
    return mark_staleness(run.payload, dataset, record)


__all__ = ["router"]
