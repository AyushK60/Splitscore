"""HTTP routes for the S4 Scientific Visual Explorer.

All routes are scoped to a dataset in the store and reuse the S3 study record
for role context. Point-level payloads are sampled (and say so); every
aggregate is computed on the full population.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_context
from app.core.errors import LimitExceededError, ValidationFailure
from app.explore.aggregates import correlation_matrix, distribution_payload, missingness_payload
from app.explore.sampling import DEFAULT_RENDER_ROWS, MAX_RENDER_ROWS, render_sample
from app.explore.schema import explore_schema
from app.explore.selection import evaluate_selection, parse_predicates
from app.explore.stats import (
    MAX_BINS,
    MISSING_CELL,
    parse_numeric,
    text_values,
)
from app.research.profiling import build_profile

import numpy as np

logger = __import__("logging").getLogger(__name__)

router = APIRouter(prefix="/api", tags=["explore"])

MAX_SERIES_COLUMNS = 32
MAX_CORRELATION_COLUMNS = 30
MAX_MISSINGNESS_COLUMNS = 100


class SeriesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str] = Field(min_length=1, max_length=MAX_SERIES_COLUMNS)
    max_rows: int = Field(default=DEFAULT_RENDER_ROWS, ge=10, le=MAX_RENDER_ROWS)
    filters: list[dict[str, Any]] = Field(default_factory=list, max_length=24)


class SelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicates: list[dict[str, Any]] = Field(default_factory=list, max_length=24)


class CorrelationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str] = Field(min_length=2, max_length=MAX_CORRELATION_COLUMNS)
    method: str = Field(default="pearson", pattern="^(pearson|spearman)$")


class DistributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1, max_length=200)
    bins: int = Field(default=20, ge=5, le=MAX_BINS)
    group_by: str | None = Field(default=None, max_length=200)


class MissingnessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str] | None = Field(default=None, max_length=MAX_MISSINGNESS_COLUMNS)
    group_by: str | None = Field(default=None, max_length=200)


class RowsRequest(BaseModel):
    """Fetch concrete rows by immutable id for the row-evidence inspector."""

    model_config = ConfigDict(extra="forbid")

    ids: list[str] = Field(min_length=1, max_length=200)
    columns: list[str] | None = Field(default=None, max_length=MAX_MISSINGNESS_COLUMNS)


def _dataset(dataset_id: str):
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    record = context.studies.get(dataset_id)
    role_assignments: dict[str, list[str]] = {}
    split_labels: tuple[str | None, str | None] = (None, None)
    if record is not None:
        role_assignments = record.role_assignments
        split_labels = (record.split_train_value, record.split_test_value)
    return dataset, role_assignments, split_labels


def _detected_types(dataset) -> dict[str, str]:
    """The profiler's advisory detection, so explorer types match the Study view."""
    profile = build_profile(dataset)
    return {entry["column"]: entry["detected_type"] for entry in profile["columns"]}


@router.get("/datasets/{dataset_id}/explore/schema")
def get_explore_schema(dataset_id: str) -> dict[str, Any]:
    dataset, roles, split_labels = _dataset(dataset_id)
    detected = _detected_types(dataset)
    return explore_schema(dataset, detected_types=detected, role_assignments=roles, split_labels=split_labels)


@router.post("/datasets/{dataset_id}/explore/series")
def post_series(dataset_id: str, request: SeriesRequest) -> dict[str, Any]:
    """Point-level values for parallel coordinates and scatters.

    The payload is the render sample: a systematic grid over the *filtered*
    population when filters are active, over the whole dataset otherwise.
    Axis ranges (`scale`) always cover the FULL population: axes must not
    rescale while the user brushes, or a committed brush would drift outside
    the visible rails and the filtered view would silently redefine its own
    coordinates. `valid_count`/`missing_count` describe the full population;
    the filtered size is `filtered_population`.
    """
    dataset, _, _ = _dataset(dataset_id)
    for column in request.columns:
        if column not in dataset.columns:
            raise ValidationFailure(
                f"Column {column!r} is not present in the dataset.",
                details={"available_columns": dataset.columns[:50]},
            )
    predicates = parse_predicates(dataset, request.filters)
    selection = evaluate_selection(dataset, predicates)

    if predicates:
        mask = selection_mask(dataset, predicates)
        indices = np.flatnonzero(mask).tolist()
    else:
        indices = list(range(dataset.row_count))

    sample = render_sample(len(indices), request.max_rows)
    sampled_indices = [indices[i] for i in sample.indices]

    columns = request.columns
    types = _detected_types(dataset)
    scale: dict[str, Any] = {}
    text: dict[str, list[str]] = {}
    for column in columns:
        parsed = parse_numeric(dataset, column)
        finite = parsed.valid
        scale[column] = {
            "numeric": types.get(column) in {"numeric", "integer"},
            "min": float(np.min(finite)) if finite.size else None,
            "max": float(np.max(finite)) if finite.size else None,
            "valid_count": parsed.valid_count,
            "missing_count": parsed.missing,
            "unparsed_count": parsed.unparsed,
        }
        text[column], _ = text_values(dataset, column)

    rows = []
    for i in sampled_indices:
        values: dict[str, Any] = {}
        for column in columns:
            raw = text[column][i]
            if raw == MISSING_CELL:
                values[column] = None
            elif scale[column]["numeric"]:
                try:
                    values[column] = float(raw)
                except ValueError:
                    values[column] = None  # counted in the column's unparsed_count
            else:
                values[column] = raw
        rows.append({"id": dataset.row_ids[i], "index": i, "values": values})

    return {
        "dataset_id": dataset.dataset_id,
        "columns": columns,
        "population": dataset.row_count,
        "filtered_population": selection.total_selected if predicates else dataset.row_count,
        "filters_active": bool(predicates),
        "drawn_rows": len(rows),
        "sampling": {
            "method": sample.method,
            "stride": sample.stride,
            "description": sample.description,
        },
        "scale": scale,
        "rows": rows,
    }


def selection_mask(dataset, predicates):
    """Boolean mask of the filtered population (union within a column, intersect across columns)."""
    from app.explore.selection import _mask_for

    if not predicates:
        return np.ones(dataset.row_count, dtype=bool)
    by_column: dict[str, list[Any]] = {}
    for p in predicates:
        by_column.setdefault(p.column, []).append(p)
    combined = np.ones(dataset.row_count, dtype=bool)
    for group in by_column.values():
        union = np.zeros(dataset.row_count, dtype=bool)
        for p in group:
            union |= _mask_for(dataset, p)
        combined &= union
    return combined


@router.post("/datasets/{dataset_id}/explore/selection")
def post_selection(dataset_id: str, request: SelectionRequest) -> dict[str, Any]:
    """Evaluate brush predicates into an exact, id-keyed selection."""
    dataset, _, _ = _dataset(dataset_id)
    predicates = parse_predicates(dataset, request.predicates)
    result = evaluate_selection(dataset, predicates)
    return {
        "dataset_id": dataset.dataset_id,
        "population": result.population,
        "total_selected": result.total_selected,
        "ids_truncated": result.ids_truncated,
        "row_ids": result.row_ids,
        "predicates": [p.describe() for p in result.predicates],
    }


@router.post("/datasets/{dataset_id}/explore/correlation")
def post_correlation(dataset_id: str, request: CorrelationRequest) -> dict[str, Any]:
    dataset, _, _ = _dataset(dataset_id)
    types = _detected_types(dataset)
    non_numeric = [c for c in request.columns if types.get(c) not in {"numeric", "integer"}]
    if non_numeric:
        raise ValidationFailure(
            "Correlation needs numeric columns. "
            + ", ".join(repr(c) for c in non_numeric)
            + f" detected as {', '.join(types.get(c, 'unknown') for c in non_numeric)}.",
            details={"non_numeric": non_numeric},
        )
    if len(set(request.columns)) != len(request.columns):
        raise ValidationFailure("Correlation columns must be distinct.")
    return correlation_matrix(dataset, list(request.columns), request.method)


@router.post("/datasets/{dataset_id}/explore/distribution")
def post_distribution(dataset_id: str, request: DistributionRequest) -> dict[str, Any]:
    dataset, _, _ = _dataset(dataset_id)
    if request.column not in dataset.columns:
        raise ValidationFailure(
            f"Column {request.column!r} is not present in the dataset.",
            details={"available_columns": dataset.columns[:50]},
        )
    if request.group_by is not None:
        if request.group_by not in dataset.columns:
            raise ValidationFailure(
                f"Group column {request.group_by!r} is not present in the dataset.",
                details={"available_columns": dataset.columns[:50]},
            )
        if request.group_by == request.column:
            raise ValidationFailure("A column cannot group by itself.")
    types = _detected_types(dataset)
    return distribution_payload(
        dataset,
        request.column,
        types.get(request.column, "text"),
        bins=request.bins,
        group_by=request.group_by,
    )


@router.post("/datasets/{dataset_id}/explore/missingness")
def post_missingness(dataset_id: str, request: MissingnessRequest) -> dict[str, Any]:
    dataset, _, _ = _dataset(dataset_id)
    columns = request.columns if request.columns is not None else list(dataset.columns)
    if len(columns) > MAX_MISSINGNESS_COLUMNS:
        raise LimitExceededError(
            f"At most {MAX_MISSINGNESS_COLUMNS} columns per missingness request.",
            details={"received": len(columns)},
        )
    for column in columns:
        if column not in dataset.columns:
            raise ValidationFailure(
                f"Column {column!r} is not present in the dataset.",
                details={"available_columns": dataset.columns[:50]},
            )
    if request.group_by is not None and request.group_by not in dataset.columns:
        raise ValidationFailure(
            f"Group column {request.group_by!r} is not present in the dataset.",
            details={"available_columns": dataset.columns[:50]},
        )
    return missingness_payload(dataset, columns, group_by=request.group_by)


@router.post("/datasets/{dataset_id}/explore/rows")
def post_rows(dataset_id: str, request: RowsRequest) -> dict[str, Any]:
    """Concrete rows by immutable id, for the row-evidence inspector.

    Values are returned as the file's own text — the inspector shows what the
    CSV says, not a chart's parsed approximation. Unknown ids are reported
    rather than silently dropped, so a stale selection cannot look complete.
    """
    dataset, _, _ = _dataset(dataset_id)
    columns = request.columns if request.columns is not None else list(dataset.columns)
    for column in columns:
        if column not in dataset.columns:
            raise ValidationFailure(
                f"Column {column!r} is not present in the dataset.",
                details={"available_columns": dataset.columns[:50]},
            )
    id_to_index = {rid: i for i, rid in enumerate(dataset.row_ids)}
    rows: list[dict[str, Any]] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for rid in request.ids:
        if rid in seen:
            continue
        seen.add(rid)
        index = id_to_index.get(rid)
        if index is None:
            unknown.append(rid)
            continue
        values: dict[str, str] = {}
        for column in columns:
            raw = dataset.frame.iloc[index][column]
            if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                values[column] = MISSING_CELL
            else:
                values[column] = str(raw)
        rows.append({"id": rid, "index": index, "values": values})
    return {
        "dataset_id": dataset.dataset_id,
        "columns": columns,
        "rows": rows,
        "unknown_ids": unknown,
        "population": dataset.row_count,
    }


__all__ = ["router"]
