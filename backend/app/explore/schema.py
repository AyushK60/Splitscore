"""Variable catalogue for the Visual Explorer.

The schema describes what can be plotted: every column with its detected type
(the profiler's advisory detection, same thresholds), the numeric range that
axes will use, the categorical levels a colour legend needs, and the role
information the Study Card contributes (split labels, target, entity). The
explorer treats roles as *suggestions for defaults* - it never edits them and
never blocks a chart because a role is missing.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.audit.dataset import Dataset
from app.explore.stats import MAX_CATEGORY_LEVELS, MISSING_CELL, parse_numeric, text_values

#: Distinct levels at or below this count make a column useful as a colour
#: grouping; above it a legend would be unreadable.
COLOR_LEVEL_LIMIT = 12


def _numeric_summary(dataset: Dataset, column: str) -> dict[str, Any]:
    parsed = parse_numeric(dataset, column)
    valid = parsed.valid
    summary: dict[str, Any] = {
        "missing_count": parsed.missing,
        "unparsed_count": parsed.unparsed,
        "valid_count": parsed.valid_count,
    }
    if valid.size:
        summary["min"] = float(np.min(valid))
        summary["max"] = float(np.max(valid))
        summary["mean"] = float(np.mean(valid))
        summary["median"] = float(np.median(valid))
        summary["all_integer"] = bool(np.all(np.mod(valid, 1) == 0))
    return summary


def _text_summary(dataset: Dataset, column: str) -> dict[str, Any]:
    values, missing = text_values(dataset, column)
    counts: dict[str, int] = {}
    for value in values:
        if value != MISSING_CELL:
            counts[value] = counts.get(value, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "missing_count": missing,
        "distinct": len(counts),
        "top_levels": [{"value": v, "count": c} for v, c in ranked[:MAX_CATEGORY_LEVELS]],
    }


def explore_schema(
    dataset: Dataset,
    *,
    detected_types: dict[str, str],
    role_assignments: dict[str, list[str]],
    split_labels: tuple[str | None, str | None],
) -> dict[str, Any]:
    """Build the explorer's variable catalogue for one dataset."""
    columns: list[dict[str, Any]] = []
    numeric_names: list[str] = []
    color_candidates: list[str] = []

    for name in dataset.columns:
        detected = detected_types.get(name, "text")
        entry: dict[str, Any] = {
            "name": name,
            "detected_type": detected,
            "roles": sorted(role_assignments.get(name, [])),
        }
        if detected in {"numeric", "integer"}:
            entry["numeric"] = _numeric_summary(dataset, name)
            numeric_names.append(name)
        elif detected in {"categorical", "boolean", "identifier", "text", "datetime", "empty"}:
            entry["text"] = _text_summary(dataset, name)
            levels = entry["text"]["distinct"]
            if detected in {"categorical", "boolean"} and 1 < levels <= COLOR_LEVEL_LIMIT:
                color_candidates.append(name)
        columns.append(entry)

    # Suggested defaults, in priority order: the declared split column shows
    # train/test differences; the target shows class structure; the entity
    # explains grouped data; then any low-cardinality category.
    suggested_color: str | None = None
    for candidate in color_candidates:
        if "split" in role_assignments.get(candidate, []):
            suggested_color = candidate
            break
    if suggested_color is None:
        for candidate in color_candidates:
            if "target" in role_assignments.get(candidate, []):
                suggested_color = candidate
                break
    if suggested_color is None and color_candidates:
        suggested_color = color_candidates[0]

    return {
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "source": "demo" if dataset.source == "demo" else "upload",
            "is_synthetic": dataset.is_synthetic,
            "fingerprint_sha256": dataset.fingerprint_sha256,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
            "demo_id": dataset.demo.demo_id if dataset.demo else None,
        },
        "row_id_scheme": "load-time immutable row ids (row-000001…), stable for the dataset's lifetime",
        "row_count": dataset.row_count,
        "columns": columns,
        "numeric_columns": numeric_names,
        "color_candidates": color_candidates,
        "suggested_color_column": suggested_color,
        "split": {
            "column": next(
                (c for c, roles in role_assignments.items() if "split" in roles), None
            ),
            "train_value": split_labels[0],
            "test_value": split_labels[1],
        }
        if split_labels[0] or split_labels[1]
        else None,
    }


__all__ = ["COLOR_LEVEL_LIMIT", "explore_schema"]
