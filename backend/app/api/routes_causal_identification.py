"""Causal identification routes (S8C).

Read-only analytical queries over a *stored, validated* graph. No route in
this module mutates the graph or the dataset: identification runs on the
stored specification exactly as saved, and results are addressed by the
graph's scientific fingerprint so the client can detect staleness.

Every route follows the S8A rules: the dataset must be live (typed 410 when
expired/evicted), a valid graph id under a different dataset is a 404, and
unanswerable queries return the single structured error envelope with a
machine-readable code — never a prose-only failure.

S8C deliberately stops at graphical identification: there is no endpoint that
returns an estimated effect, a propensity score, a bootstrap interval, or any
other causal number.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_context
from app.api.routes_causal import _dataset
from app.causal.adjustment import (
    AdjustmentQueryError,
    evaluate_adjustment_set,
    search_adjustment_sets,
)
from app.causal.d_separation import DSeparationQueryError, d_separated
from app.causal.identification import (
    IDENTIFICATION_VERSION,
    build_dag,
    identify_backdoor,
    observed_node_ids,
)
from app.causal.schema import CAUSAL_GRAPH_SCHEMA_VERSION, MAX_NODES, CausalGraphSpec
from app.causal.validation import validate_spec
from app.core.errors import ValidationFailure
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["causal-identification"])


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DSeparationRequest(_Model):
    """One graphical-independence query."""

    x: str = Field(min_length=1, max_length=80)
    y: str = Field(min_length=1, max_length=80)
    conditioning: list[str] = Field(default_factory=list, max_length=MAX_NODES)


class ScopeBody(_Model):
    """Optional per-request analysis-scope override."""

    treatment: str | None = Field(default=None, max_length=80)
    outcome: str | None = Field(default=None, max_length=80)


class AdjustmentEvaluationRequest(ScopeBody):
    adjustment_set: list[str] = Field(default_factory=list, max_length=MAX_NODES)


class AdjustmentSearchRequest(ScopeBody):
    pass


class IdentificationRequest(ScopeBody):
    method: str = Field(default="backdoor", max_length=40)


def _query_error(code: str, message: str) -> ValidationFailure:
    """One structured, per-issue error list, matching the S8A envelope shape."""
    return ValidationFailure(
        message,
        details={
            "ok": False,
            "errors": [{"code": code, "severity": "error", "message": message, "hint": None}],
            "warnings": [],
            "fix": "Correct the query and resubmit. Nothing was changed or stored.",
        },
    )


def _live_record(dataset_id: str, graph_id: str):
    """Resolve the live dataset and its stored graph record (no mutation)."""
    context = get_context()
    dataset = _dataset(dataset_id)
    record = context.causal_graphs.get(dataset.dataset_id, graph_id)
    return dataset, record


def _require_validated_spec(spec: CausalGraphSpec, dataset):
    """Identification only ever runs on a spec whose references still resolve.

    The stored graph was validated when saved, but the dataset in memory may
    have been replaced; re-validate so identification never runs against a
    graph whose column anchors no longer exist.
    """
    result = validate_spec(spec, dataset_columns=list(dataset.columns))
    if not result.ok:
        raise ValidationFailure(
            "The stored causal graph no longer validates against the dataset in memory; "
            "identification was refused.",
            details={
                **result.to_payload(),
                "fix": "Re-validate the graph in the Causal Lab and resolve the listed errors.",
            },
        )
    return result


def _envelope(record, payload: dict[str, Any]) -> dict[str, Any]:
    """Common provenance block: results are addressed to an exact fingerprint."""
    return {
        "graph_id": record.graph_id,
        "dataset_id": record.dataset_id,
        "revision": record.revision,
        "spec_fingerprint_sha256": record.fingerprint,
        "schema_version": CAUSAL_GRAPH_SCHEMA_VERSION,
        **payload,
    }


def _scope_or_422(spec: CausalGraphSpec, treatment: str | None, outcome: str | None) -> tuple[str, str]:
    resolved_treatment = treatment or spec.analysis.treatment
    resolved_outcome = outcome or spec.analysis.outcome
    if resolved_treatment is None or resolved_outcome is None:
        raise _query_error(
            "analysis_incomplete",
            "No treatment/outcome pair is available: select one here or save an analysis "
            "scope on the graph.",
        )
    return resolved_treatment, resolved_outcome


@router.post("/datasets/{dataset_id}/causal-graphs/{graph_id}/d-separation")
def d_separation_query(dataset_id: str, graph_id: str, request: DSeparationRequest) -> dict[str, Any]:
    """Exact d-separation of two nodes given a conditioning set (read-only)."""
    dataset, record = _live_record(dataset_id, graph_id)
    _require_validated_spec(record.spec, dataset)
    dag = build_dag(record.spec)
    try:
        result = d_separated(dag, request.x, request.y, request.conditioning)
    except DSeparationQueryError as error:
        raise _query_error(error.code, error.message) from error
    logger.info(
        "d-separation on %s: %s ⊥ %s | %s → %s",
        record.graph_id,
        request.x,
        request.y,
        request.conditioning,
        result.d_separated,
    )
    return _envelope(record, result.to_payload())


@router.post("/datasets/{dataset_id}/causal-graphs/{graph_id}/adjustment-evaluation")
def adjustment_evaluation(
    dataset_id: str, graph_id: str, request: AdjustmentEvaluationRequest
) -> dict[str, Any]:
    """Evaluate one proposed adjustment set under the classical backdoor criterion."""
    dataset, record = _live_record(dataset_id, graph_id)
    _require_validated_spec(record.spec, dataset)
    treatment, outcome = _scope_or_422(record.spec, request.treatment, request.outcome)
    dag = build_dag(record.spec)
    observed = observed_node_ids(record.spec)
    try:
        result = evaluate_adjustment_set(dag, treatment, outcome, request.adjustment_set, observed)
    except AdjustmentQueryError as error:
        raise _query_error(error.code, error.message) from error
    return _envelope(record, result.to_payload())


@router.post("/datasets/{dataset_id}/causal-graphs/{graph_id}/adjustment-search")
def adjustment_search(
    dataset_id: str, graph_id: str, request: AdjustmentSearchRequest
) -> dict[str, Any]:
    """Search observed inclusion-minimal backdoor adjustment sets (bounded, honest)."""
    dataset, record = _live_record(dataset_id, graph_id)
    _require_validated_spec(record.spec, dataset)
    treatment, outcome = _scope_or_422(record.spec, request.treatment, request.outcome)
    dag = build_dag(record.spec)
    observed = observed_node_ids(record.spec)
    try:
        result = search_adjustment_sets(dag, treatment, outcome, observed)
    except AdjustmentQueryError as error:
        raise _query_error(error.code, error.message) from error
    logger.info(
        "adjustment search on %s (%s→%s): %s, %d set(s)",
        record.graph_id,
        treatment,
        outcome,
        result.status,
        len(result.minimal_sets),
    )
    return _envelope(record, result.to_payload())


@router.post("/datasets/{dataset_id}/causal-graphs/{graph_id}/identification")
def identification_status(
    dataset_id: str, graph_id: str, request: IdentificationRequest
) -> dict[str, Any]:
    """Structured graphical-identification status with rule-based explanations."""
    dataset, record = _live_record(dataset_id, graph_id)
    _require_validated_spec(record.spec, dataset)
    result = identify_backdoor(
        record.spec,
        treatment=request.treatment,
        outcome=request.outcome,
        method=request.method,
    )
    logger.info("identification on %s: %s", record.graph_id, result.status)
    return _envelope(
        record,
        {**result.to_payload(), "identification_version": IDENTIFICATION_VERSION},
    )


__all__ = ["router"]
