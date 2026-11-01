"""Heuristic column-role suggestions.

Suggestions only pre-fill the UI. They never run an audit, and every suggestion is
reported with the reason it was made and with a confidence level, so a user can see
why a column was proposed and override it.

The heuristics inspect only column names and whole-column statistics. Guessing
wrong is cheap because the user confirms; guessing silently is not, which is why
each suggestion carries a ``reason``.
"""

from __future__ import annotations

from typing import Any

from app.audit.dataset import Dataset
from app.audit.types import ColumnRoles, ColumnTypeInfo

TRAIN_TOKENS = ("train", "training", "tr", "fit", "develop", "development", "dev")
TEST_TOKENS = (
    "test",
    "testing",
    "te",
    "eval",
    "evaluation",
    "holdout",
    "hold",
    "validation",
    "val",
    "valid",
)

SPLIT_NAME_HINTS = ("split", "set", "partition", "fold", "subset", "datasubset")
TARGET_NAME_HINTS = (
    "target",
    "label",
    "outcome",
    "response",
    "churn",
    "defect",
    "converted",
    "conversion",
    "grade",
    "class",
    "y",
    "quality",
    "rating",
    "score",
)
TARGET_SUFFIX_HINTS = ("_flag", "_target", "_label")
ENTITY_SUFFIX_HINTS = (
    "_id",
    "_key",
    "_group",
    "_entity",
    "_no",
    "customer",
    "patient",
    "device",
    "account",
    "item",
    "part",
    "sku",
)
IDENTIFIER_NAME_HINTS = (
    "row_id",
    "rowid",
    "index",
    "row_number",
    "rownum",
    "record_id",
    "recordid",
    "uuid",
    "guid",
    "item_id",
    "reference",
)

MAX_FEATURE_SUGGESTIONS = 40


def _lower(name: str) -> str:
    return name.strip().lower()


def _looks_like_entity_name(name: str) -> bool:
    lowered = _lower(name)
    return any(lowered.endswith(hint) for hint in ENTITY_SUFFIX_HINTS) or lowered.endswith("_id")


def _suggest_split(
    columns: list[str],
    column_types: dict[str, ColumnTypeInfo],
    values: dict[str, list[str]],
) -> dict[str, Any] | None:
    for name in columns:
        info = column_types[name]
        if not 2 <= info.distinct_values <= 3:
            continue
        raw_values = sorted({value for value in values[name] if value.strip() != ""})
        lower_to_raw: dict[str, str] = {}
        for raw in raw_values:
            lower_to_raw.setdefault(raw.strip().lower(), raw)
        if len(lower_to_raw) != 2:
            continue
        train_keys = [key for key in lower_to_raw if key in TRAIN_TOKENS]
        test_keys = [key for key in lower_to_raw if key in TEST_TOKENS]
        if len(train_keys) == 1 and len(test_keys) == 1:
            return {
                "column": name,
                "train_value": lower_to_raw[train_keys[0]],
                "test_value": lower_to_raw[test_keys[0]],
                "reason": (
                    f"Column {name!r} has exactly two values, {lower_to_raw[train_keys[0]]!r} and "
                    f"{lower_to_raw[test_keys[0]]!r}, which read as train and test labels."
                ),
            }

    for name in columns:
        if _lower(name) in SPLIT_NAME_HINTS and column_types[name].distinct_values == 2:
            raw_values = sorted({value for value in values[name] if value.strip() != ""})
            if len(raw_values) == 2:
                return {
                    "column": name,
                    "train_value": raw_values[0],
                    "test_value": raw_values[1],
                    "reason": (
                        f"Column {name!r} is named like a split indicator and holds exactly two "
                        "values. Confirm which value means train; the roles form does no guessing "
                        "about that."
                    ),
                }
    return None


def _suggest_target(
    columns: list[str],
    column_types: dict[str, ColumnTypeInfo],
    taken: set[str],
) -> dict[str, Any] | None:
    for name in columns:
        if name in taken:
            continue
        lowered = _lower(name)
        if lowered in TARGET_NAME_HINTS or lowered.endswith(TARGET_SUFFIX_HINTS):
            return {"column": name, "reason": f"Column {name!r} is named like a prediction target."}
    return None


def _suggest_entity(
    columns: list[str],
    column_types: dict[str, ColumnTypeInfo],
    taken: set[str],
    row_count: int,
) -> dict[str, Any] | None:
    """Suggest a group column only when the candidate actually repeats.

    A column with one distinct value per row is an identifier, not a group. Using
    it as the entity role would produce a group split identical to a random split,
    so it is left for the user to choose deliberately instead of being pre-filled.
    """
    candidates = [
        name
        for name in columns
        if name not in taken
        and _looks_like_entity_name(name)
        and 1 < column_types[name].distinct_values < row_count
    ]
    if not candidates:
        return None
    # Prefer the candidate with the fewest distinct values: the strongest grouping.
    name = min(candidates, key=lambda candidate: (column_types[candidate].distinct_values, candidate))
    info = column_types[name]
    return {
        "column": name,
        "reason": (
            f"Column {name!r} is named like an identifier and repeats across rows "
            f"({info.distinct_values} distinct values over {row_count} rows), so it behaves like a "
            "group column."
        ),
    }


def _suggest_timestamp(
    columns: list[str],
    column_types: dict[str, ColumnTypeInfo],
    taken: set[str],
) -> dict[str, Any] | None:
    best: tuple[float, str] | None = None
    for name in columns:
        if name in taken:
            continue
        info = column_types[name]
        if info.looks_datetime and (best is None or info.datetime_parse_ratio > best[0]):
            best = (info.datetime_parse_ratio, name)
    if best is None:
        return None
    score, name = best
    return {
        "column": name,
        "reason": f"{score:.0%} of the non-missing values in {name!r} parse as timestamps.",
    }


def suggest_roles(
    dataset: Dataset, column_types: dict[str, ColumnTypeInfo]
) -> tuple[ColumnRoles, str, dict[str, Any]]:
    """Return suggested roles, a confidence level and the reasons behind them."""
    columns = list(dataset.columns)
    values = {name: dataset.values(name) for name in columns}
    row_count = dataset.row_count

    suggestions: dict[str, Any] = {}
    taken: set[str] = set()

    split = _suggest_split(columns, column_types, values)
    if split:
        suggestions["split"] = split
        taken.add(split["column"])

    target = _suggest_target(columns, column_types, taken)
    if target:
        suggestions["target"] = target
        taken.add(target["column"])

    entity = _suggest_entity(columns, column_types, taken, row_count)
    if entity:
        suggestions["entity"] = entity
        taken.add(entity["column"])

    timestamp = _suggest_timestamp(columns, column_types, taken)
    if timestamp:
        suggestions["timestamp"] = timestamp
        taken.add(timestamp["column"])

    metadata: list[str] = []
    for name in columns:
        if name in taken:
            continue
        lowered = _lower(name)
        info = column_types[name]
        if lowered in IDENTIFIER_NAME_HINTS or (
            info.looks_identifier and info.distinct_values >= 2 and not info.looks_datetime
        ):
            metadata.append(name)

    metadata_set = set(metadata)
    remaining = [name for name in columns if name not in taken and name not in metadata_set]
    features = remaining[:MAX_FEATURE_SUGGESTIONS]
    not_suggested = remaining[MAX_FEATURE_SUGGESTIONS:]

    roles = ColumnRoles(
        features=features,
        target=target["column"] if target else None,
        entity=entity["column"] if entity else None,
        timestamp=timestamp["column"] if timestamp else None,
        split=split["column"] if split else None,
        split_train_value=split["train_value"] if split else None,
        split_test_value=split["test_value"] if split else None,
        metadata_excluded=metadata,
    )

    if split and features:
        confidence = "high"
    elif split or features:
        confidence = "partial"
    else:
        confidence = "low"

    return roles, confidence, {
        "reasons": {key: value.get("reason") for key, value in suggestions.items()},
        "metadata_columns": metadata,
        "metadata_reason": (
            "Columns that look like row identifiers are placed in excluded metadata so they are "
            "never compared as features. SplitScope never uses your identifier column as a feature."
        ),
        "feature_count": len(features),
        "features_not_suggested": not_suggested,
        "roles_detected": len(suggestions),
        "note": (
            "Suggestions use column names and whole-column statistics only. They pre-fill the form; "
            "nothing is audited until the roles are confirmed and submitted."
        ),
    }


__all__ = ["suggest_roles"]
