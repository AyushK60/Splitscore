"""Selection predicates: how a brush on a chart becomes a set of row ids.

A brush is a *predicate over immutable row ids*, evaluated server-side on the
full population. The response carries the exact selected-id count plus the ids
themselves (capped, in file order), so every linked view can highlight by id
and every count shown to the user is the true count over the whole dataset -
not a count over whichever rows happened to be drawn.

Multiple predicates on the same column are unioned; predicates across
different columns are intersected. That is the documented combination rule:
brushing "tenure between 2 and 5" *or* "tenure between 8 and 9" on one axis,
then "spend below 40" on another, selects rows matching either tenure range
AND the spend range.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.audit.dataset import Dataset
from app.core.errors import LimitExceededError, ValidationFailure
from app.explore.stats import parse_numeric, text_values

#: Hard cap on how many selected ids are returned for highlighting. The count
#: is always exact; the cap only bounds the id list other charts highlight.
MAX_SELECTED_IDS = 20000
MAX_PREDICATES = 24


@dataclass(frozen=True)
class Predicate:
    """One brush: a numeric range or an explicit value include-list."""

    column: str
    min: float | None = None
    max: float | None = None
    values: tuple[str, ...] | None = None

    def describe(self) -> dict[str, object]:
        if self.values is not None:
            return {"column": self.column, "kind": "values", "values": list(self.values)}
        return {
            "column": self.column,
            "kind": "range",
            "min": self.min,
            "max": self.max,
            "min_inclusive": True,
            "max_inclusive": True,
        }


def parse_predicates(dataset: Dataset, raw: list[dict[str, object]]) -> list[Predicate]:
    """Validate request predicates into typed brushes."""
    if len(raw) > MAX_PREDICATES:
        raise LimitExceededError(
            f"At most {MAX_PREDICATES} brush predicates are supported per selection.",
            details={"received": len(raw), "max": MAX_PREDICATES},
        )
    predicates: list[Predicate] = []
    for entry in raw:
        column = entry.get("column")
        if not isinstance(column, str) or not column:
            raise ValidationFailure("Every predicate needs a 'column' string.")
        if column not in dataset.columns:
            raise ValidationFailure(
                f"Predicate column {column!r} is not present in the dataset.",
                details={"available_columns": dataset.columns[:50]},
            )
        if "values" in entry and entry["values"] is not None:
            values = entry["values"]
            if not isinstance(values, list) or not values or len(values) > 200:
                raise ValidationFailure(
                    f"Predicate on {column!r}: 'values' must be a non-empty list of at most 200 labels."
                )
            predicates.append(
                Predicate(column=column, values=tuple(str(v) for v in values))
            )
            continue
        low, high = entry.get("min"), entry.get("max")
        if low is None and high is None:
            raise ValidationFailure(
                f"Predicate on {column!r} needs 'min', 'max' or 'values'."
            )
        try:
            lo = float(low) if low is not None else None  # type: ignore[arg-type]
            hi = float(high) if high is not None else None  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValidationFailure(
                f"Predicate on {column!r}: 'min' and 'max' must be numbers."
            ) from None
        if lo is not None and hi is not None and lo > hi:
            raise ValidationFailure(
                f"Predicate on {column!r}: min {lo} is greater than max {hi}."
            )
        predicates.append(Predicate(column=column, min=lo, max=hi))
    return predicates


def _mask_for(dataset: Dataset, predicate: Predicate) -> np.ndarray:
    if predicate.values is not None:
        values, _ = text_values(dataset, predicate.column)
        wanted = set(predicate.values)
        return np.fromiter((v in wanted for v in values), dtype=bool, count=len(values))
    parsed = parse_numeric(dataset, predicate.column)
    mask = np.isfinite(parsed.values)
    if predicate.min is not None:
        mask &= parsed.values >= predicate.min
    if predicate.max is not None:
        mask &= parsed.values <= predicate.max
    return mask


@dataclass(frozen=True)
class SelectionResult:
    """The exact outcome of evaluating predicates over the whole population."""

    row_ids: list[str]  # capped, file order
    total_selected: int
    population: int
    ids_truncated: bool
    predicates: list[Predicate]


def population_mask(dataset: Dataset, predicates: list[Predicate]) -> np.ndarray:
    """Boolean mask of the filtered population.

    Union within a column, intersection across columns - the same combination
    rule :func:`evaluate_selection` applies, exposed for aggregate endpoints
    that compute selection overlays server-side (so a distribution chart can
    show the exact selected-cohort histogram instead of a client-side guess).
    """
    n = dataset.row_count
    if not predicates:
        return np.ones(n, dtype=bool)
    by_column: dict[str, list[Predicate]] = {}
    for predicate in predicates:
        by_column.setdefault(predicate.column, []).append(predicate)
    combined = np.ones(n, dtype=bool)
    for group in by_column.values():
        union = np.zeros(n, dtype=bool)
        for predicate in group:
            union |= _mask_for(dataset, predicate)
        combined &= union
    return combined


def evaluate_selection(dataset: Dataset, predicates: list[Predicate]) -> SelectionResult:
    """Intersect per-column unions into the final selected-id set."""
    n = dataset.row_count
    if not predicates:
        return SelectionResult(
            row_ids=list(dataset.row_ids[:MAX_SELECTED_IDS]),
            total_selected=n,
            population=n,
            ids_truncated=n > MAX_SELECTED_IDS,
            predicates=[],
        )
    by_column: dict[str, list[Predicate]] = {}
    for predicate in predicates:
        by_column.setdefault(predicate.column, []).append(predicate)

    combined: np.ndarray | None = None
    for column, group in by_column.items():
        union = np.zeros(n, dtype=bool)
        for predicate in group:
            union |= _mask_for(dataset, predicate)
        combined = union if combined is None else (combined & union)

    assert combined is not None
    indices = np.flatnonzero(combined)
    total = int(indices.size)
    capped = indices[:MAX_SELECTED_IDS]
    return SelectionResult(
        row_ids=[dataset.row_ids[i] for i in capped],
        total_selected=total,
        population=n,
        ids_truncated=total > MAX_SELECTED_IDS,
        predicates=list(predicates),
    )


__all__ = [
    "MAX_PREDICATES",
    "MAX_SELECTED_IDS",
    "Predicate",
    "SelectionResult",
    "evaluate_selection",
    "parse_predicates",
    "population_mask",
]
