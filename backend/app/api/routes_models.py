"""HTTP routes for the S6 Model Lab (F09 statistics; F10 added later).

A fit is scoped to a dataset already in the store, reuses no inferred roles, and
records its run in the same bounded store as audits. The response carries the
specification, analysed population, coefficients, fit statistics, diagnostics
and warnings; the export route returns that exact payload, so a downloaded
result cannot disagree with the screen.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_context
from app.core.errors import LimitExceededError, NotFoundError
from app.models.contracts import MAX_PREDICTORS, StatisticsConfig
from app.models.prediction import PredictionConfig, fit_prediction
from app.research.studies import roles_from_column_roles
from app.synthetic.manifest import recommended_roles as demo_recommended_roles
from app.models.statistics import fit_statistics

router = APIRouter(prefix="/api", tags=["models"])

MAX_STORED_MODEL_RUNS = 16


class StatisticsRequest(BaseModel):
    """An explicit statistical specification. Nothing is inferred at fit time."""

    model_config = ConfigDict(extra="forbid")

    task: Literal["ols", "logistic"]
    outcome: str = Field(min_length=1, max_length=200)
    predictors: list[str] = Field(min_length=1, max_length=MAX_PREDICTORS)
    missing_policy: Literal["complete_case", "fail"] = "complete_case"
    intercept: bool = True
    positive_level: str | None = Field(default=None, max_length=200)
    categorical_references: dict[str, str] = Field(default_factory=dict)
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)


class PredictionRequest(BaseModel):
    """A predictive specification. The split is resolved from the study or a strategy."""

    model_config = ConfigDict(extra="forbid")

    task: Literal["classification", "regression"]
    outcome: str = Field(min_length=1, max_length=200)
    predictors: list[str] = Field(min_length=1, max_length=MAX_PREDICTORS)
    positive_level: str | None = Field(default=None, max_length=200)
    split_source: Literal["existing", "generated"] = "existing"
    split_strategy: Literal["random", "stratified", "group", "chronological"] = "stratified"
    test_fraction: float = Field(default=0.25, gt=0.0, lt=1.0)
    seed: int = Field(default=12345, ge=0)
    validation_fraction: float = Field(default=0.2, gt=0.0, lt=1.0)
    models: list[str] = Field(default_factory=list, max_length=6)
    subgroup_column: str | None = Field(default=None, max_length=200)
    subgroup_bins: list[float] = Field(default_factory=list, max_length=20)


@router.post("/datasets/{dataset_id}/models/statistics")
def post_statistics(dataset_id: str, request: StatisticsRequest) -> dict[str, Any]:
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    config = StatisticsConfig(
        task=request.task,
        outcome=request.outcome,
        predictors=tuple(request.predictors),
        missing_policy=request.missing_policy,
        intercept=request.intercept,
        positive_level=request.positive_level,
        categorical_references=request.categorical_references,
        alpha=request.alpha,
    )
    result = fit_statistics(dataset, config)
    result["created_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    run_id = context.store.put_run(
        kind="model",
        dataset_id=dataset_id,
        payload=result,
        label=result["specification"]["formula"],
    )
    # The stored payload is the same object, so an exported run always carries
    # the id the UI shows.
    result["run_id"] = run_id
    return result


@router.post("/datasets/{dataset_id}/models/prediction")
def post_prediction(dataset_id: str, request: PredictionRequest) -> dict[str, Any]:
    """Fit candidates on fit/validation and evaluate the selected model once on test."""
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    record = context.studies.get(dataset_id)
    if record is None and dataset.demo is not None:
        # A bundled demo declares its roles and split labels in its manifest.
        # Seed them exactly as the Study route would, so opening Model Lab
        # directly cannot lose the documented split.
        demo_roles = demo_recommended_roles(dataset.demo.demo_id)
        record = context.studies.get_or_create(
            dataset_id,
            seed_roles=roles_from_column_roles(demo_roles),
            seed_split_labels=(demo_roles.split_train_value, demo_roles.split_test_value),
        )
    roles = record.role_assignments if record is not None else {}
    split_labels = (
        (record.split_train_value, record.split_test_value)
        if record is not None
        else (None, None)
    )
    config = PredictionConfig(
        task=request.task,
        outcome=request.outcome,
        predictors=tuple(request.predictors),
        positive_level=request.positive_level,
        split_source=request.split_source,
        split_strategy=request.split_strategy,
        test_fraction=request.test_fraction,
        seed=request.seed,
        validation_fraction=request.validation_fraction,
        models=tuple(request.models),
        subgroup_column=request.subgroup_column,
        subgroup_bins=tuple(request.subgroup_bins),
    )
    result = fit_prediction(dataset, config, roles=roles, split_labels=split_labels)
    result["created_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    run_id = context.store.put_run(
        kind="model",
        dataset_id=dataset_id,
        payload=result,
        label=(
            f"predictive {request.task}: {request.outcome} ~ "
            + " + ".join(request.predictors)
        ),
    )
    result["run_id"] = run_id
    return result


@router.get("/datasets/{dataset_id}/models/runs")
def list_model_runs(dataset_id: str) -> dict[str, Any]:
    context = get_context()
    context.store.get_dataset(dataset_id)
    runs = [
        run
        for run in context.store.list_runs()
        if run["kind"] == "model" and run["dataset_id"] == dataset_id
    ]
    return {
        "dataset_id": dataset_id,
        "runs": runs[:MAX_STORED_MODEL_RUNS],
        "note": (
            "Model runs live in the same in-memory, bounded store as audits. They disappear when the "
            "process restarts or the entry expires; export a run to keep its numbers."
        ),
    }


@router.get("/models/runs/{run_id}")
def get_model_run(run_id: str) -> dict[str, Any]:
    context = get_context()
    run = context.store.get_run(run_id)
    if run.kind != "model":
        raise NotFoundError(
            "That run is not a model run.",
            details={"run_id": run_id, "kind": run.kind},
        )
    return run.payload


@router.get("/models/runs/{run_id}/export")
def export_model_run(run_id: str) -> JSONResponse:
    context = get_context()
    run = context.store.get_run(run_id)
    if run.kind != "model":
        raise NotFoundError(
            "That run is not a model run.",
            details={"run_id": run_id, "kind": run.kind},
        )
    return JSONResponse(
        content=run.payload,
        headers={
            "Content-Disposition": f'attachment; filename="splitscope-model-{run_id}.json"',
            "X-SplitScope-Export-Note": (
                "Model specification, population, coefficients and diagnostics. No dataset rows are "
                "included."
            ),
        },
    )


__all__ = ["router"]
