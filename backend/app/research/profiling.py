"""Computed dataset profile and data dictionary.

Everything here is measured from the loaded frame; nothing is estimated from a
column's name. Two conventions are fixed and documented because they change the
numbers a reader sees:

* **Missing means an empty cell.** SplitScope never decides on its own that the
  string ``"NA"`` is missing — V1 made that choice deliberately and the profile
  inherits it. Any other missing convention is a *declared* study field, not an
  inferred one.
* **Numeric summaries ignore unparsable cells** and report how many were
  ignored, so a "mean" is never computed over a silently coerced column.

Detected types are advisory. A user-confirmed type from the data dictionary is
carried alongside and never overwritten by detection.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from app.audit.dataset import Dataset
from app.audit.io import infer_column_types, to_datetime_series

MISSING_CELL = ""

#: A column whose values parse as numbers above this ratio is treated as numeric.
NUMERIC_RATIO = 0.99
#: Below this, mixed values are reported as a candidate type inconsistency.
MIXED_RATIO_FLOOR = 0.5
#: Timestamps need this share of parsable values to be called a datetime column.
DATETIME_RATIO = 0.9
#: Distinct values at or below this count describe a categorical column.
CATEGORICAL_MAX_DISTINCT = 20
#: A column with this many distinct values per row behaves like an identifier.
IDENTIFIER_MIN_ROWS = 10
#: IQR multiplier for outlier *candidates* (never labelled errors).
IQR_MULTIPLIER = 1.5
MAX_EXAMPLES = 3
MAX_EXAMPLE_CHARS = 60


def _examples(values: list[str]) -> list[str]:
    """The first distinct values in file order.

    For identifiers this is the same as the first rows; for a boolean or a
    low-cardinality category it shows the actual variety instead of repeating
    whichever label happened to come first.
    """
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
            if len(seen) >= MAX_EXAMPLES:
                break
    return [value[:MAX_EXAMPLE_CHARS] for value in seen]


def _as_float_list(values: list[str]) -> tuple[np.ndarray, int]:
    """Parse numeric cells, returning the parsed values and the count ignored."""
    if not values:
        return np.empty(0, dtype=float), 0
    series = pd.Series(values, dtype="object")
    coerced = pd.to_numeric(series.where(series != MISSING_CELL), errors="coerce")
    arr = coerced.to_numpy(dtype=float)
    mask = ~np.isnan(arr)
    return arr[mask], int((~mask).sum())


def _numeric_stats(arr: np.ndarray) -> dict[str, float | int] | None:
    if arr.size == 0:
        return None
    q1 = float(np.percentile(arr, 25))
    q3 = float(np.percentile(arr, 75))
    iqr = q3 - q1
    low = q1 - IQR_MULTIPLIER * iqr
    high = q3 + IQR_MULTIPLIER * iqr
    outliers = int(np.sum((arr < low) | (arr > high))) if iqr > 0 else 0
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0,
        "q1": q1,
        "q3": q3,
        "outlier_candidates": outliers,
        "outlier_rule": f"IQR × {IQR_MULTIPLIER}",
    }


def _datetime_stats(values: list[str], row_count: int) -> dict[str, Any] | None:
    if not values:
        return None
    parsed = to_datetime_series(pd.Series(values, dtype="object"))
    valid = parsed.notna()
    n_valid = int(valid.sum())
    if n_valid == 0:
        return None
    stamps = parsed[valid]
    return {
        "parsed": n_valid,
        "unparsed": int(row_count - n_valid),
        "parse_ratio": round(n_valid / row_count, 4) if row_count else 0.0,
        "min_utc": stamps.min().isoformat(),
        "max_utc": stamps.max().isoformat(),
        "span_days": round((stamps.max() - stamps.min()).total_seconds() / 86400, 3),
    }


def _detect_type(
    *,
    name: str,
    values: list[str],
    distinct: int,
    row_count: int,
    numeric_ratio: float,
    datetime_ratio: float,
    all_integral: bool,
) -> tuple[str, str]:
    """Return ``(type, reason)``. Advisory only; the reason is shown in the UI."""
    if not values:
        return "empty", "Every cell in this column is empty."
    lowered = {value.strip().lower() for value in values}
    if lowered <= {"true", "false", "yes", "no", "0", "1", "t", "f", "y", "n"} and distinct <= 2:
        return "boolean", "Only two distinct values, both recognisable as boolean labels."
    if datetime_ratio >= DATETIME_RATIO and numeric_ratio < NUMERIC_RATIO:
        return "datetime", f"{datetime_ratio:.0%} of values parse as a timestamp."
    if numeric_ratio >= NUMERIC_RATIO:
        return (
            ("integer" if all_integral else "numeric"),
            f"{numeric_ratio:.0%} of values parse as numbers"
            + (", all whole" if all_integral else ", with fractional values"),
        )
    if distinct == len(values) and row_count >= IDENTIFIER_MIN_ROWS:
        return "identifier", "Every value is unique, so the column behaves like an identifier."
    if distinct <= CATEGORICAL_MAX_DISTINCT:
        return "categorical", f"Only {distinct} distinct values."
    return "text", f"{distinct} distinct free-text values."


def _duplicate_row_groups(frame: pd.DataFrame, row_ids: list[str]) -> dict[str, Any]:
    if frame.empty:
        return {"duplicate_rows": 0, "groups": 0, "example_row_ids": []}
    duplicated = frame.duplicated(keep="first")
    duplicate_rows = int(duplicated.sum())
    if duplicate_rows == 0:
        return {"duplicate_rows": 0, "groups": 0, "example_row_ids": []}
    signatures = frame[duplicated].astype(str).agg("\x1f".join, axis=1)
    example_ids = [row_ids[i] for i in np.flatnonzero(duplicated.to_numpy())[:5]]
    return {
        "duplicate_rows": duplicate_rows,
        "groups": int(signatures.nunique()),
        "example_row_ids": example_ids,
    }


def build_profile(
    dataset: Dataset,
    *,
    assignments: dict[str, list[str]] | None = None,
    declarations: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Profile every column of a loaded dataset."""
    frame = dataset.frame
    row_count = dataset.row_count
    types = infer_column_types(frame)
    assignments = assignments or {}
    declarations = declarations or {}

    columns: list[dict[str, Any]] = []
    warnings: list[str] = []
    numeric_columns = 0
    datetime_columns = 0

    for name in dataset.columns:
        info = types[name]
        raw = frame[name].tolist()
        non_missing = [value for value in raw if value != MISSING_CELL]
        distinct = len(set(non_missing))
        parsed_numbers, unparsed = _as_float_list(non_missing)
        all_integral = bool(parsed_numbers.size) and bool(np.all(np.mod(parsed_numbers, 1) == 0))
        detected, reason = _detect_type(
            name=name,
            values=non_missing,
            distinct=distinct,
            row_count=row_count,
            numeric_ratio=info.numeric_parse_ratio,
            datetime_ratio=info.datetime_parse_ratio,
            all_integral=all_integral,
        )
        numeric_stats = _numeric_stats(parsed_numbers) if detected in {"numeric", "integer"} else None
        datetime_stats = _datetime_stats(non_missing, row_count) if detected == "datetime" else None
        declaration = declarations.get(name, {})
        roles = assignments.get(name, [])

        flags: list[str] = []
        if detected == "identifier":
            flags.append("identifier_like")
        if distinct == 1 and non_missing:
            flags.append("constant")
        if not non_missing:
            flags.append("all_missing")
        if dataset.row_count >= IDENTIFIER_MIN_ROWS and distinct == len(non_missing):
            flags.append("unique_per_row")
        if numeric_stats and numeric_stats["outlier_candidates"] > 0:
            flags.append("outlier_candidates")
        if (
            MIXED_RATIO_FLOOR <= info.numeric_parse_ratio < NUMERIC_RATIO
            and info.datetime_parse_ratio < DATETIME_RATIO
        ):
            flags.append("mixed_types")
            warnings.append(
                f"{name!r} parses as numeric for {info.numeric_parse_ratio:.0%} of values; "
                "the rest may be text, units or missing-value tokens."
            )

        if numeric_stats:
            numeric_columns += 1
        if datetime_stats:
            datetime_columns += 1

        columns.append(
            {
                "column": name,
                "detected_type": detected,
                "detected_type_reason": reason,
                "declared_type": declaration.get("declared_type") or None,
                "description": declaration.get("description") or None,
                "unit": declaration.get("unit") or None,
                "measurement_scale": declaration.get("measurement_scale") or None,
                "roles": roles,
                "missing_count": int(row_count - len(non_missing)),
                "missing_ratio": round((row_count - len(non_missing)) / row_count, 4)
                if row_count
                else 0.0,
                "distinct_count": distinct,
                "distinct_ratio": round(distinct / len(non_missing), 4) if non_missing else 0.0,
                "examples": _examples(non_missing),
                "numeric_parse_ratio": info.numeric_parse_ratio,
                "datetime_parse_ratio": info.datetime_parse_ratio,
                "unparsed_numeric_cells": unparsed if parsed_numbers.size else 0,
                "numeric": numeric_stats,
                "datetime": datetime_stats,
                "flags": flags,
            }
        )

    duplicates = _duplicate_row_groups(frame, dataset.row_ids)
    if duplicates["duplicate_rows"]:
        warnings.append(
            f"{duplicates['duplicate_rows']} row(s) repeat an earlier row exactly. Repetition is a "
            "fact about the file, not by itself evidence of leakage across a split."
        )

    constants = [column["column"] for column in columns if "constant" in column["flags"]]
    all_missing = [column["column"] for column in columns if "all_missing" in column["flags"]]
    identifiers = [column["column"] for column in columns if "identifier_like" in column["flags"]]
    mixed = [column["column"] for column in columns if "mixed_types" in column["flags"]]

    return {
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "row_count": row_count,
            "column_count": dataset.column_count,
            "fingerprint_sha256": dataset.fingerprint_sha256,
            "is_synthetic": dataset.is_synthetic,
            "duplicate_rows": duplicates["duplicate_rows"],
            "duplicate_row_groups": duplicates["groups"],
            "duplicate_example_row_ids": duplicates["example_row_ids"],
            "numeric_columns": numeric_columns,
            "datetime_columns": datetime_columns,
        },
        "columns": columns,
        "summary": {
            "constant_columns": constants,
            "all_missing_columns": all_missing,
            "identifier_like_columns": identifiers,
            "mixed_type_columns": mixed,
            "columns_with_outlier_candidates": [
                column["column"] for column in columns if "outlier_candidates" in column["flags"]
            ],
        },
        "warnings": warnings,
        "conventions": [
            "A missing value is an empty cell in the source file; the strings 'NA' and 'NaN' are "
            "ordinary values unless you say otherwise in the Study Card.",
            "Numeric summaries ignore cells that do not parse as numbers and report how many were "
            "ignored.",
            "Detected types are advisory. A type you confirm in the dictionary is kept separately "
            "and never overwritten.",
            "Outliers are candidates under an IQR rule, not data errors.",
        ],
        "notes": [
            "Every figure here is computed from the loaded file. Opening this view does not change "
            "the dataset or any audit result.",
        ],
    }


def _finite(value: float) -> float | None:
    """JSON cannot carry NaN/Infinity; report those as null instead of guessing."""
    if value is None:
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if math.isnan(value) or math.isinf(value):
        return None
    return float(value)


__all__ = ["build_profile"]
