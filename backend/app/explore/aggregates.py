"""Payload assembly for the Visual Explorer's aggregate endpoints.

These functions turn :mod:`app.explore.stats` results into the JSON shapes the
frontend renders. Every payload repeats its denominator (population, valid,
missing, unparsed) so the UI never has to reconstruct one, and every sampled
payload carries the sampling description verbatim.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.audit.dataset import Dataset
from app.explore.sampling import RenderSample
from app.explore.stats import (
    CORRELATION_METHODS,
    CORR_MIN_PAIRS,
    MISSING_CELL,
    BoxStats,
    NumericColumn,
    box_stats,
    frequencies,
    histogram,
    parse_numeric,
    text_values,
)


def correlation_matrix(
    dataset: Dataset,
    columns: list[str],
    method: str,
) -> dict[str, Any]:
    """Pairwise coefficients over the requested numeric columns.

    Only columns detected as numeric may enter; the caller validates names.
    Each cell keeps its own valid-pair count: two columns can be highly
    correlated on 900 complete pairs while a third joins them on only 120.
    """
    compute = CORRELATION_METHODS[method]
    parsed = {name: parse_numeric(dataset, name) for name in columns}
    cells: list[dict[str, Any]] = []
    warnings: list[str] = []
    for i, a in enumerate(columns):
        for j in range(i + 1, len(columns)):
            b = columns[j]
            result = compute(parsed[a].values, parsed[b].values)
            entry: dict[str, Any] = {
                "x": a,
                "y": b,
                "method": method,
                "coefficient": result.coefficient,
                "n_valid": result.n_valid,
                "missing_policy": result.missing_policy,
                "warning": result.warning,
            }
            if result.warning:
                warnings.append(f"{a} × {b}: {result.warning}")
            cells.append(entry)
    return {
        "method": method,
        "columns": columns,
        "cells": cells,
        "min_pairs": CORR_MIN_PAIRS,
        "warnings": warnings,
        "population": dataset.row_count,
        "note": "Correlation describes association in this dataset. It is not evidence of causation.",
    }


def distribution_payload(
    dataset: Dataset,
    column: str,
    detected_type: str,
    *,
    bins: int,
    group_by: str | None,
    group_limit: int = 8,
) -> dict[str, Any]:
    """Histogram/box stats (numeric) or frequencies (categorical).

    With ``group_by``, each group's statistics are computed over that group's
    own rows; group sizes are reported so a small group is never visually
    mistaken for a large one.
    """
    is_numeric = detected_type in {"numeric", "integer"}
    if not is_numeric:
        values, missing = text_values(dataset, column)
        freq = frequencies(values)
        payload: dict[str, Any] = {
            "column": column,
            "kind": "categorical",
            "levels": [{"value": v, "count": c} for v, c in freq.levels],
            "other_count": freq.other_count,
            "distinct": freq.distinct,
            "missing_count": freq.missing,
            "population": freq.population,
            "group_by": None,
        }
        if group_by:
            payload["groups"] = _grouped_frequencies(dataset, column, group_by, group_limit)
        return payload

    parsed = parse_numeric(dataset, column)
    hist = histogram(parsed, bins=bins)
    box = box_stats(parsed)
    payload = {
        "column": column,
        "kind": "numeric",
        "bins": hist.edges,
        "counts": hist.counts,
        "valid_count": hist.valid,
        "missing_count": hist.missing,
        "unparsed_count": hist.unparsed,
        "population": hist.population,
        "box": _box_dict(box),
        "group_by": None,
    }
    if group_by:
        payload["groups"] = _grouped_numeric(dataset, column, group_by, bins, group_limit)
    return payload


def _box_dict(box: BoxStats | None) -> dict[str, Any] | None:
    if box is None:
        return None
    return {
        "n": box.n,
        "q1": box.q1,
        "median": box.median,
        "q3": box.q3,
        "whisker_low": box.whisker_low,
        "whisker_high": box.whisker_high,
        "iqr": box.iqr,
        "outlier_count": box.outlier_count,
        "outlier_examples": box.outlier_examples,
        "definition": "Quartiles: linear interpolation. Whiskers: most extreme values within 1.5×IQR fences.",
    }


def _group_values(dataset: Dataset, group_by: str, limit: int) -> list[tuple[str, np.ndarray]]:
    values, _ = text_values(dataset, group_by)
    counts: dict[str, int] = {}
    for value in values:
        if value != MISSING_CELL:
            counts[value] = counts.get(value, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    groups = [(label, np.array([v == label for v in values], dtype=bool)) for label, _ in ranked]
    missing_group = ("(missing)", np.array([v == MISSING_CELL for v in values], dtype=bool))
    if missing_group[1].any():
        groups.append(missing_group)
    return groups


def _grouped_numeric(dataset: Dataset, column: str, group_by: str, bins: int, limit: int) -> list[dict[str, Any]]:
    parsed = parse_numeric(dataset, column)
    text, _ = text_values(dataset, column)
    out = []
    for label, mask in _group_values(dataset, group_by, limit):
        # Slice the already-parsed values by the group mask; NaN marks rows
        # outside the group the same way missing/unparsable cells are marked.
        values = np.where(mask, parsed.values, np.nan)
        missing = sum(
            1 for v, keep in zip(text, mask.tolist(), strict=True) if keep and v == MISSING_CELL
        )
        unparsed = int((mask & ~np.isfinite(parsed.values)).sum()) - missing
        group_column = NumericColumn(values=values, missing=missing, unparsed=unparsed)
        hist = histogram(group_column, bins=bins)
        out.append(
            {
                "group": label,
                "rows": int(mask.sum()),
                "bins": hist.edges,
                "counts": hist.counts,
                "valid_count": hist.valid,
                "missing_count": hist.missing,
                "unparsed_count": hist.unparsed,
                "box": _box_dict(box_stats(group_column)),
            }
        )
    return out


def _grouped_frequencies(dataset: Dataset, column: str, group_by: str, limit: int) -> list[dict[str, Any]]:
    values, _ = text_values(dataset, column)
    out = []
    for label, mask in _group_values(dataset, group_by, limit):
        subset = [v for v, keep in zip(values, mask.tolist(), strict=True) if keep]
        freq = frequencies(subset)
        out.append(
            {
                "group": label,
                "rows": int(mask.sum()),
                "levels": [{"value": v, "count": c} for v, c in freq.levels],
                "other_count": freq.other_count,
                "distinct": freq.distinct,
                "missing_count": freq.missing,
            }
        )
    return out


def missingness_payload(
    dataset: Dataset,
    columns: list[str],
    *,
    group_by: str | None,
    group_limit: int = 8,
    max_matrix_rows: int = 400,
) -> dict[str, Any]:
    """Exact per-column missingness plus a bounded display matrix.

    The matrix is a *rendering* aid: it shows the first ``max_matrix_rows`` rows
    in file order (a systematic grid sample when the dataset is larger), while
    every count and percentage is computed over the full population.
    """
    per_column: list[dict[str, Any]] = []
    for name in columns:
        raw = dataset.series(name)
        missing = sum(
            1
            for v in raw.tolist()
            if v is None or (isinstance(v, float) and np.isnan(v)) or v == MISSING_CELL
        )
        per_column.append(
            {
                "column": name,
                "missing_count": missing,
                "missing_pct": round(100.0 * missing / dataset.row_count, 3) if dataset.row_count else 0.0,
            }
        )

    # Display matrix: stride-sampled rows, cell = 1 when the value is missing.
    stride = max(1, -(-dataset.row_count // max_matrix_rows))
    matrix_rows: list[dict[str, Any]] = []
    frame = dataset.frame
    for i in range(0, dataset.row_count, stride):
        cells: list[int] = []
        for name in columns:
            v = frame.iloc[i][name]
            if v is None or (isinstance(v, float) and np.isnan(v)) or v == MISSING_CELL:
                cells.append(1)
            else:
                cells.append(0)
        matrix_rows.append({"id": dataset.row_ids[i], "cells": cells})

    payload: dict[str, Any] = {
        "columns": [c["column"] for c in per_column],
        "per_column": per_column,
        "population": dataset.row_count,
        "matrix": {
            "rows": matrix_rows,
            "row_count_drawn": len(matrix_rows),
            "stride": stride,
            "method": "systematic_grid" if stride > 1 else "all",
            "description": (
                f"Grid sample: every {stride}th row of {dataset.row_count:,} in file order."
                if stride > 1
                else "All rows are drawn."
            ),
        },
        "policy": "Missing means an empty cell. No other value is treated as missing; "
        "for numeric columns, cells that do not parse as numbers are counted separately by the distribution view.",
        "group_by": None,
    }
    if group_by:
        groups: list[dict[str, Any]] = []
        for label, mask in _group_values(dataset, group_by, group_limit):
            entries = []
            for name in columns:
                raw = dataset.series(name).tolist()
                total = int(mask.sum())
                missing = sum(
                    1
                    for v, keep in zip(raw, mask.tolist(), strict=True)
                    if keep and (v is None or (isinstance(v, float) and np.isnan(v)) or v == MISSING_CELL)
                )
                entries.append(
                    {
                        "column": name,
                        "missing_count": missing,
                        "missing_pct": round(100.0 * missing / total, 3) if total else 0.0,
                    }
                )
            groups.append({"group": label, "rows": total, "per_column": entries})
        payload["groups"] = groups
        payload["group_by"] = group_by
    return payload


__all__ = ["correlation_matrix", "distribution_payload", "missingness_payload"]
