"""Candidate train/test split strategies.

Four strategies are implemented, each with an explicit statement of the
evaluation assumption it serves:

``random``
    Exchangeable rows. Assumes every row is an independent sample from the same
    distribution, which is the assumption that duplicated rows and repeated
    entities break.
``stratified``
    Exchangeable rows with the target's class proportions preserved across the
    boundary, for a categorical target. It protects class balance and nothing
    else: it does not deduplicate and it does not separate entities.
``group``
    Whole entities (or whole whatever-the-group-column-is) stay on one side. This
    is the strategy that matches "predict for an entity never seen before".
``chronological``
    Earlier records train, later records test, with equal timestamps kept
    together. This matches a future-prediction evaluation.

None of these is universally correct. The right one is the one whose test split
resembles the data the deployed model will actually be asked about.

Every randomised strategy takes an explicit seed. All strategies are pure: they
read the dataset and return masks, and never modify the stored frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from app.audit.canonical import MISSING_TOKEN, ValueCanonicalizer
from app.audit.dataset import Dataset, SplitMasks
from app.audit.io import to_datetime_series
from app.audit.tokens import column_missing_mask, column_tokens
from app.audit.types import SplitConfig, SplitSummary
from app.core.errors import InfeasibleOperationError

#: Minimum rows required on each side of any generated split.
MIN_SIDE_ROWS = 2

#: Missing entity identifiers are made their own singleton groups rather than
#: merged into one artificial entity.
MISSING_GROUP_PREFIX = "\x00ungrouped:"

@dataclass
class GeneratedSplit:
    """A strategy's output: masks plus an honest description of what it achieved."""

    masks: SplitMasks
    requested_test_fraction: float | None
    seed: int | None
    proportion_note: str | None = None
    notes: list[str] = field(default_factory=list)
    extra_metrics: dict[str, float | int | str] = field(default_factory=dict)


def _check_sides(masks: SplitMasks, strategy_label: str) -> None:
    if masks.train_rows < MIN_SIDE_ROWS or masks.test_rows < MIN_SIDE_ROWS:
        raise InfeasibleOperationError(
            f"{strategy_label} produced {masks.train_rows} train and {masks.test_rows} test rows; "
            f"both sides need at least {MIN_SIDE_ROWS} rows.",
            details={"train_rows": masks.train_rows, "test_rows": masks.test_rows},
        )


def _validate_fraction(test_fraction: float) -> float:
    if not 0.0 < test_fraction < 1.0:
        raise InfeasibleOperationError(
            f"The test fraction must be strictly between 0 and 1; received {test_fraction}.",
            details={"test_fraction": test_fraction},
        )
    return test_fraction


def random_holdout(n_rows: int, test_fraction: float, seed: int) -> GeneratedSplit:
    """Uniform random holdout with a seeded permutation."""
    _validate_fraction(test_fraction)
    if n_rows < 2 * MIN_SIDE_ROWS:
        raise InfeasibleOperationError(
            f"A random holdout needs at least {2 * MIN_SIDE_ROWS} rows; the dataset has {n_rows}.",
            details={"rows": n_rows},
        )
    rng = np.random.default_rng(seed)
    permutation = rng.permutation(n_rows)
    n_test = int(round(test_fraction * n_rows))
    n_test = min(max(n_test, MIN_SIDE_ROWS), n_rows - MIN_SIDE_ROWS)
    test_idx = permutation[:n_test]
    train_idx = permutation[n_test:]

    train_mask = np.zeros(n_rows, dtype=bool)
    test_mask = np.zeros(n_rows, dtype=bool)
    train_mask[train_idx] = True
    test_mask[test_idx] = True
    masks = SplitMasks(train=train_mask, test=test_mask)
    _check_sides(masks, "The random holdout")
    return GeneratedSplit(
        masks=masks,
        requested_test_fraction=test_fraction,
        seed=seed,
        proportion_note=(
            f"Requested test fraction {test_fraction:.4f}; achieved "
            f"{masks.achieved_test_fraction:.4f} after rounding to whole rows."
        ),
    )


def stratified_holdout(
    frame: pd.DataFrame,
    *,
    target_column: str,
    test_fraction: float,
    seed: int,
    canonicalizer: ValueCanonicalizer,
) -> GeneratedSplit:
    """Class-proportion-preserving holdout for a categorical target.

    Feasibility is checked *before* delegating to scikit-learn, so the caller gets
    a specific reason (which class is too small, or that the requested test size
    cannot hold one row per class) rather than a generic library error.
    """
    _validate_fraction(test_fraction)
    n_rows = len(frame)
    tokens = column_tokens(frame, target_column, canonicalizer)
    labels = np.asarray(tokens, dtype=object)

    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    n_classes = len(counts)
    rare = sorted(token for token, count in counts.items() if count < 2)

    if n_classes < 2:
        raise InfeasibleOperationError(
            f"Stratification needs at least two target classes; {target_column!r} has {n_classes}.",
            details={"distinct_classes": n_classes},
        )
    if rare:
        shown = ", ".join("(missing)" if token == MISSING_TOKEN else repr(token) for token in rare[:10])
        raise InfeasibleOperationError(
            f"Stratification is infeasible: {len(rare)} target class(es) have fewer than two rows "
            f"({shown}), so those classes cannot appear in both splits.",
            details={
                "rare_classes": len(rare),
                "rare_class_examples": shown,
                "hint": "Merge small classes, use a random holdout, or lower the number of classes.",
            },
        )

    n_test = int(round(test_fraction * n_rows))
    if n_test < n_classes:
        raise InfeasibleOperationError(
            f"Stratification is infeasible: a test fraction of {test_fraction:.4f} gives {n_test} "
            f"test row(s), fewer than the {n_classes} classes that each need at least one row.",
            details={"test_rows_requested": n_test, "classes": n_classes},
        )
    if n_rows - n_test < n_classes:
        raise InfeasibleOperationError(
            f"Stratification is infeasible: the train side would hold {n_rows - n_test} rows for "
            f"{n_classes} classes.",
            details={"train_rows_requested": n_rows - n_test, "classes": n_classes},
        )

    try:
        train_idx, test_idx = train_test_split(
            np.arange(n_rows),
            test_size=test_fraction,
            random_state=seed,
            shuffle=True,
            stratify=labels,
        )
    except ValueError as exc:  # pragma: no cover - guarded above, kept as a typed fallback
        raise InfeasibleOperationError(
            f"Stratification failed for this target: {exc}",
            details={"target_column": target_column},
        ) from None

    train_mask = np.zeros(n_rows, dtype=bool)
    test_mask = np.zeros(n_rows, dtype=bool)
    train_mask[train_idx] = True
    test_mask[test_idx] = True
    masks = SplitMasks(train=train_mask, test=test_mask)
    _check_sides(masks, "The stratified holdout")

    achieved_test_rows = masks.test_rows
    return GeneratedSplit(
        masks=masks,
        requested_test_fraction=test_fraction,
        seed=seed,
        proportion_note=(
            f"Requested test fraction {test_fraction:.4f}; achieved "
            f"{masks.achieved_test_fraction:.4f} ({achieved_test_rows} of "
            f"{masks.assigned_rows} rows). Protections are applied per class, so the test size is "
            f"rounded within each of the {n_classes} classes."
        ),
        notes=[
            f"Stratified over {n_classes} target classes, including a distinct stratum for missing "
            "target values so that missingness is not concentrated on one side.",
            "Stratification preserves class proportions only. It does not deduplicate rows and does "
            "not keep entities together.",
        ],
        extra_metrics={"strata": n_classes},
    )


def group_holdout(
    frame: pd.DataFrame,
    *,
    entity_column: str,
    test_fraction: float,
    seed: int,
    canonicalizer: ValueCanonicalizer,
) -> GeneratedSplit:
    """Holdout that keeps each entity entirely on one side."""
    _validate_fraction(test_fraction)
    n_rows = len(frame)
    tokens = column_tokens(frame, entity_column, canonicalizer)
    missing = column_missing_mask(frame, entity_column, canonicalizer)

    group_of: list[str] = []
    ungrouped = 0
    for position, token in enumerate(tokens):
        if missing[position]:
            group_of.append(f"{MISSING_GROUP_PREFIX}{position}")
            ungrouped += 1
        else:
            group_of.append(token)

    group_sizes: dict[str, int] = {}
    for group in group_of:
        group_sizes[group] = group_sizes.get(group, 0) + 1
    groups = sorted(group_sizes)
    if len(groups) < 2:
        raise InfeasibleOperationError(
            f"A group holdout needs at least two groups; {entity_column!r} yields {len(groups)}.",
            details={"groups": len(groups)},
        )

    rng = np.random.default_rng(seed)
    order = rng.permutation(len(groups))
    target_test_rows = max(MIN_SIDE_ROWS, int(round(test_fraction * n_rows)))

    test_groups: list[str] = []
    current = 0
    for index in order.tolist():
        group = groups[index]
        size = group_sizes[group]
        if current + size <= target_test_rows:
            test_groups.append(group)
            current += size
    if not test_groups:
        # Every group is larger than the requested test size; take the smallest one
        # so that the split is still usable, and say so.
        smallest = min(groups, key=lambda group: (group_sizes[group], group))
        test_groups.append(smallest)
        current = group_sizes[smallest]

    test_group_set = set(test_groups)
    if len(test_group_set) == len(groups):
        keep = min(test_groups, key=lambda group: (group_sizes[group], group))
        test_group_set.discard(keep)

    train_mask = np.zeros(n_rows, dtype=bool)
    test_mask = np.zeros(n_rows, dtype=bool)
    for position, group in enumerate(group_of):
        if group in test_group_set:
            test_mask[position] = True
        else:
            train_mask[position] = True

    masks = SplitMasks(train=train_mask, test=test_mask)
    _check_sides(masks, "The group holdout")

    achieved = masks.achieved_test_fraction
    return GeneratedSplit(
        masks=masks,
        requested_test_fraction=test_fraction,
        seed=seed,
        proportion_note=(
            f"Requested test fraction {test_fraction:.4f}; achieved {achieved:.4f} "
            f"({masks.test_rows} of {masks.assigned_rows} rows). Whole entities are assigned to one "
            "side, so the achieved row proportion can only move in steps of group size and will "
            "usually differ from the requested fraction."
        ),
        notes=[
            f"{len(groups)} distinct entity value(s) were split as {len(test_group_set)} test group(s) "
            f"and {len(groups) - len(test_group_set)} train group(s). Groups are never divided "
            "across the boundary.",
            (
                f"{ungrouped} row(s) had an empty entity identifier and were each treated as their "
                "own group, so they cannot leak through a shared entity."
                if ungrouped
                else "No row had an empty entity identifier."
            ),
        ],
        extra_metrics={"groups": len(groups), "test_groups": len(test_group_set)},
    )


def chronological_holdout(
    frame: pd.DataFrame,
    *,
    timestamp_column: str,
    test_fraction: float,
) -> GeneratedSplit:
    """Holdout by time, keeping equal timestamps on one side of the cut."""
    _validate_fraction(test_fraction)
    n_rows = len(frame)
    parsed = to_datetime_series(frame[timestamp_column])
    invalid = int(parsed.isna().sum())
    if invalid:
        raise InfeasibleOperationError(
            f"A chronological split needs every row to be orderable, but {invalid} of {n_rows} "
            f"values in {timestamp_column!r} do not parse as timestamps. Rows are not dropped "
            "silently, so no split is produced.",
            details={"invalid_timestamps": invalid, "rows": n_rows},
        )

    values = parsed.to_numpy()
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]

    requested_test_rows = int(round(test_fraction * n_rows))
    cut = n_rows - min(max(requested_test_rows, MIN_SIDE_ROWS), n_rows - MIN_SIDE_ROWS)

    boundary = cut
    while boundary < n_rows and boundary > 0 and sorted_values[boundary] == sorted_values[boundary - 1]:
        boundary += 1
    if boundary >= n_rows:
        # The final timestamp covers the whole tail; move the cut left instead so
        # that at least one test row remains.
        boundary = cut
        while boundary > 1 and sorted_values[boundary] == sorted_values[boundary - 1]:
            boundary -= 1
    if boundary <= 0:
        boundary = 1
    if boundary >= n_rows:
        boundary = n_rows - 1
    boundary_moved = boundary != cut

    train_idx = order[:boundary]
    test_idx = order[boundary:]
    train_mask = np.zeros(n_rows, dtype=bool)
    test_mask = np.zeros(n_rows, dtype=bool)
    train_mask[train_idx] = True
    test_mask[test_idx] = True
    masks = SplitMasks(train=train_mask, test=test_mask)
    _check_sides(masks, "The chronological holdout")

    boundary_timestamp = pd.Timestamp(sorted_values[boundary]).isoformat()
    tie_size = int((sorted_values == sorted_values[boundary - 1]).sum())
    achieved = masks.achieved_test_fraction

    note = (
        f"Requested test fraction {test_fraction:.4f}; achieved {achieved:.4f} "
        f"({masks.test_rows} of {masks.assigned_rows} rows)."
    )
    if boundary_moved:
        note += (
            " The cut was moved to keep every row sharing the boundary timestamp together, so the "
            "achieved test fraction differs from the requested one by up to the size of one "
            "timestamp group."
        )

    return GeneratedSplit(
        masks=masks,
        requested_test_fraction=test_fraction,
        seed=None,
        proportion_note=note,
        notes=[
            f"The split point falls at the first timestamp strictly later than "
            f"{boundary_timestamp}; all rows sharing a timestamp stay on the same side.",
            f"The boundary timestamp {boundary_timestamp} occurs {tie_size} time(s) in total; equal "
            "timestamps are never divided across the boundary.",
            "Ordering is by the parsed timestamp only. Ties keep their original file order, so the "
            "result is deterministic without a seed.",
        ],
        extra_metrics={
            "boundary_timestamp": boundary_timestamp,
            "boundary_tie_count": tie_size,
        },
    )


def generate_split(
    dataset: Dataset,
    *,
    resolved_entity: str | None,
    resolved_target: str | None,
    resolved_timestamp: str | None,
    config: SplitConfig,
    canonicalizer: ValueCanonicalizer,
) -> GeneratedSplit:
    """Dispatch to the requested strategy, raising a typed error when infeasible."""
    frame = dataset.frame
    if config.kind == "random":
        return random_holdout(len(frame), config.test_fraction, config.seed)
    if config.kind == "stratified":
        if resolved_target is None:
            raise InfeasibleOperationError(
                "A stratified holdout requires a target column, which was not selected.",
                details={"strategy": config.kind},
            )
        return stratified_holdout(
            frame,
            target_column=resolved_target,
            test_fraction=config.test_fraction,
            seed=config.seed,
            canonicalizer=canonicalizer,
        )
    if config.kind == "group":
        if resolved_entity is None:
            raise InfeasibleOperationError(
                "A group holdout requires an entity/group column, which was not selected.",
                details={"strategy": config.kind},
            )
        return group_holdout(
            frame,
            entity_column=resolved_entity,
            test_fraction=config.test_fraction,
            seed=config.seed,
            canonicalizer=canonicalizer,
        )
    if config.kind == "chronological":
        if resolved_timestamp is None:
            raise InfeasibleOperationError(
                "A chronological holdout requires a timestamp column, which was not selected.",
                details={"strategy": config.kind},
            )
        return chronological_holdout(
            frame,
            timestamp_column=resolved_timestamp,
            test_fraction=config.test_fraction,
        )
    raise InfeasibleOperationError(
        f"Strategy {config.kind!r} cannot be generated; it is not a supported candidate strategy.",
        details={"strategy": config.kind},
    )


def existing_split(
    dataset: Dataset,
    *,
    split_column: str,
    train_value: str,
    test_value: str,
    strategy_id: str = "existing",
    label: str = "Existing split column",
) -> tuple[SplitMasks, SplitSummary]:
    """Read the split that is already present in the uploaded file.

    Rows carrying neither label are excluded from both sides and reported. They
    are never folded into train or test, because that would silently audit a
    different split from the one in the file.
    """
    from app.audit.dataset import select_existing_split

    selection = select_existing_split(
        dataset,
        split_column=split_column,
        train_value=train_value,
        test_value=test_value,
    )
    masks = selection.masks
    notes = [
        f"Labels were read from the column {split_column!r} with train={train_value!r} and "
        f"test={test_value!r}.",
    ]
    if selection.unassigned_rows:
        shown = ", ".join(
            f"{value!r} ({count})" for value, count in list(selection.other_labels.items())[:5]
        )
        notes.append(
            f"{selection.unassigned_rows} row(s) carry neither label and are excluded from both "
            f"sides of the audited split ({shown})."
        )

    achieved = masks.achieved_test_fraction
    proportion_note = (
        f"The existing split places {achieved:.4f} of its {masks.assigned_rows} assigned rows in "
        "test."
    )
    if selection.unassigned_rows:
        proportion_note += (
            f" A further {selection.unassigned_rows} row(s) carry neither label and are excluded "
            "from the denominator."
        )

    return masks, SplitSummary(
        strategy_id=strategy_id,
        label=label,
        kind="existing",
        requested_test_fraction=None,
        achieved_test_fraction=round(achieved, 6),
        train_rows=masks.train_rows,
        test_rows=masks.test_rows,
        seed=None,
        split_column=split_column,
        train_value=train_value,
        test_value=test_value,
        proportion_note=proportion_note,
        notes=notes,
        assignment_id=None,
    )


def summarise(
    *,
    strategy_id: str,
    label: str,
    kind: str,
    generated: GeneratedSplit,
    split_column: str | None = None,
    train_value: str | None = None,
    test_value: str | None = None,
    assignment_id: str | None = None,
) -> SplitSummary:
    return SplitSummary(
        strategy_id=strategy_id,
        label=label,
        kind=kind,  # type: ignore[arg-type]
        requested_test_fraction=generated.requested_test_fraction,
        achieved_test_fraction=round(generated.masks.achieved_test_fraction, 6),
        train_rows=generated.masks.train_rows,
        test_rows=generated.masks.test_rows,
        seed=generated.seed,
        split_column=split_column,
        train_value=train_value,
        test_value=test_value,
        proportion_note=generated.proportion_note,
        notes=list(generated.notes),
        assignment_id=assignment_id,
    )


__all__ = [
    "MIN_SIDE_ROWS",
    "GeneratedSplit",
    "chronological_holdout",
    "existing_split",
    "generate_split",
    "group_holdout",
    "random_holdout",
    "stratified_holdout",
    "summarise",
]
