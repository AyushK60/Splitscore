"""F05 — evaluation plans: cross-validation and rolling-origin validation.

A *plan* is a multi-fold validation design. Unlike a holdout it cannot be
audited as one split, so a plan carries its folds and the comparison
infrastructure audits each fold and aggregates the outcomes. Every fold keeps
its exact row ids, so the assignments stay reproducible and exportable.

Supported kinds and their documented feasibility gates (all failures raise the
typed :class:`InfeasibleOperationError` with a specific reason — a strategy
that cannot run is never silently swapped for one that can):

* ``repeated_stratified_cv`` — needs a target with at least two classes, each
  with at least ``n_folds`` rows (so every fold's test side can hold one row
  of each class). Deterministic via ``random_state``.
* ``group_cv`` — needs an entity column and at least ``n_folds`` groups; every
  group must have at least two rows so no fold ends up with an empty side.
  Fold assignment is deterministic (GroupKFold order, no seed).
* ``rolling_origin`` — needs a timestamp column and at least ``n_folds + 1``
  distinct timestamps. Each fold's test is the block of rows after a growing
  origin; ``gap`` rows are purged between the train block and each test block
  when a gap is requested. Deterministic without a seed.

Bounds: at most 10 folds and 3 repeats per plan, and the caller caps the total
fold count per comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from app.audit.canonical import ValueCanonicalizer
from app.audit.dataset import Dataset, SplitMasks
from app.audit.io import to_datetime_series
from app.audit.tokens import column_tokens
from app.core.errors import InfeasibleOperationError

MAX_FOLDS = 10
MAX_REPEATS = 3
MIN_GROUP_ROWS = 2

PlanKind = str  # "repeated_stratified_cv" | "group_cv" | "rolling_origin"


class PlanConfig(BaseModel):
    """A requested evaluation plan."""

    model_config = ConfigDict(extra="forbid")

    kind: PlanKind
    label: str
    n_folds: int = Field(default=5, ge=2, le=MAX_FOLDS)
    repeats: int = Field(default=1, ge=1, le=MAX_REPEATS)
    gap: int = Field(default=0, ge=0, le=1000, description="Purged rows between train and test blocks.")
    plan_id: str | None = None


class PlanFold(BaseModel):
    """One fold of an evaluation plan."""

    fold_index: int
    repeat: int = 1
    train_rows: int
    test_rows: int
    train_row_ids: list[str]
    test_row_ids: list[str]


class EvaluationPlan(BaseModel):
    """A full multi-fold design with exact, reproducible assignments."""

    plan_id: str
    kind: str
    label: str
    n_folds: int
    repeats: int
    gap: int
    seed: int | None = None
    notes: list[str] = Field(default_factory=list)
    folds: list[PlanFold]


@dataclass
class GeneratedFold:
    masks: SplitMasks
    notes: list[str] = field(default_factory=list)


def _masks(n_rows: int, train_idx: np.ndarray, test_idx: np.ndarray) -> SplitMasks:
    train = np.zeros(n_rows, dtype=bool)
    test = np.zeros(n_rows, dtype=bool)
    train[train_idx] = True
    test[test_idx] = True
    return SplitMasks(train=train, test=test)


def _check_fold(masks: SplitMasks, label: str, fold_name: str) -> None:
    if masks.train_rows < 2 or masks.test_rows < 2:
        raise InfeasibleOperationError(
            f"{label} fold {fold_name} produced {masks.train_rows} train and {masks.test_rows} "
            "test rows; both sides need at least 2 rows.",
            details={"fold": fold_name, "train_rows": masks.train_rows, "test_rows": masks.test_rows},
        )


def repeated_stratified_cv(
    frame: pd.DataFrame,
    *,
    target_column: str,
    n_folds: int,
    repeats: int,
    seed: int,
    canonicalizer: ValueCanonicalizer,
) -> list[GeneratedFold]:
    """Stratified k-fold, optionally repeated with different seeds."""
    tokens = column_tokens(frame, target_column, canonicalizer)
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    n_classes = len(counts)
    if n_classes < 2:
        raise InfeasibleOperationError(
            f"Stratified CV needs at least two target classes; {target_column!r} has {n_classes}.",
            details={"distinct_classes": n_classes},
        )
    smallest = min(counts.values())
    if smallest < n_folds:
        raise InfeasibleOperationError(
            f"Stratified CV is infeasible: the smallest target class has {smallest} row(s), "
            f"fewer than the {n_folds} folds that each need at least one of them.",
            details={"smallest_class_rows": smallest, "n_folds": n_folds},
        )

    from sklearn.model_selection import RepeatedStratifiedKFold

    splitter = RepeatedStratifiedKFold(n_splits=n_folds, n_repeats=repeats, random_state=seed)
    labels = np.asarray(tokens, dtype=object)
    folds: list[GeneratedFold] = []
    n_rows = len(frame)
    for train_idx, test_idx in splitter.split(np.zeros((n_rows, 1)), labels):
        masks = _masks(n_rows, train_idx, test_idx)
        _check_fold(masks, "The stratified CV", str(len(folds) + 1))
        folds.append(GeneratedFold(masks=masks))
    return folds


def group_cv(
    frame: pd.DataFrame,
    *,
    entity_column: str,
    n_folds: int,
    canonicalizer: ValueCanonicalizer,
) -> list[GeneratedFold]:
    """Group k-fold: every entity appears on exactly one side of one fold."""
    tokens = column_tokens(frame, entity_column, canonicalizer)
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    if len(counts) < n_folds:
        raise InfeasibleOperationError(
            f"Group CV is infeasible: {entity_column!r} yields {len(counts)} group(s), fewer than "
            f"the {n_folds} folds requested.",
            details={"groups": len(counts), "n_folds": n_folds},
        )
    tiny = sorted(token for token, count in counts.items() if count < MIN_GROUP_ROWS)
    if tiny:
        raise InfeasibleOperationError(
            f"Group CV is infeasible: {len(tiny)} group(s) have fewer than {MIN_GROUP_ROWS} rows, "
            "so at least one fold would lose a side entirely.",
            details={"tiny_groups": len(tiny), "n_folds": n_folds},
        )

    from sklearn.model_selection import GroupKFold

    groups = np.asarray(tokens, dtype=object)
    splitter = GroupKFold(n_splits=n_folds)
    folds: list[GeneratedFold] = []
    n_rows = len(frame)
    for train_idx, test_idx in splitter.split(np.zeros((n_rows, 1)), groups=groups):
        masks = _masks(n_rows, train_idx, test_idx)
        _check_fold(masks, "The group CV", str(len(folds) + 1))
        folds.append(GeneratedFold(masks=masks))
    return folds


def rolling_origin(
    frame: pd.DataFrame,
    *,
    timestamp_column: str,
    n_folds: int,
    gap: int,
) -> list[GeneratedFold]:
    """Expanding-window time validation with an optional purge gap.

    Fold k trains on everything up to origin k and tests on the following block;
    ``gap`` rows immediately after each train block are excluded from both sides,
    so a declared horizon or label delay cannot straddle the boundary.
    """
    parsed = to_datetime_series(frame[timestamp_column])
    order = parsed.sort_values(na_position="last").index
    valid = [position for position in order.tolist() if not pd.isna(parsed.iloc[position])]
    unparsable = len(frame) - len(valid)
    if len(valid) < n_folds + 1:
        raise InfeasibleOperationError(
            f"Rolling-origin validation needs at least {n_folds + 1} parsable timestamps; found "
            f"{len(valid)}.",
            details={"parsable_timestamps": len(valid), "n_folds": n_folds},
        )
    n_rows = len(frame)
    folds: list[GeneratedFold] = []
    positions = np.asarray(valid, dtype=np.int64)
    block = len(valid) // (n_folds + 1)
    for fold_index in range(n_folds):
        train_end = block * (fold_index + 1)
        test_end = min(train_end + block, len(valid))
        train_idx = positions[: train_end - gap] if gap else positions[:train_end]
        test_idx = positions[train_end:test_end]
        masks = _masks(n_rows, train_idx, test_idx)
        _check_fold(masks, "The rolling-origin plan", str(fold_index + 1))
        note = f"Train block ends at row {train_end} of {len(valid)} ordered rows."
        if gap:
            note += f" {gap} row(s) after the train block are purged from both sides."
        if unparsable:
            note += f" {unparsable} row(s) with unparsable timestamps are excluded from every fold."
        folds.append(GeneratedFold(masks=masks, notes=[note]))
    return folds


def build_plan(
    dataset: Dataset,
    *,
    resolved_entity: str | None,
    resolved_target: str | None,
    resolved_timestamp: str | None,
    config: PlanConfig,
    canonicalizer: ValueCanonicalizer,
) -> EvaluationPlan:
    """Build an evaluation plan with exact fold assignments, or raise a typed error."""
    frame = dataset.frame
    plan_id = config.plan_id or config.kind
    notes: list[str] = []
    seed: int | None = None

    if config.kind == "repeated_stratified_cv":
        if resolved_target is None:
            raise InfeasibleOperationError(
                "Stratified CV requires a target column, which was not selected.",
                details={"strategy": config.kind},
            )
        seed = 12345
        generated = repeated_stratified_cv(
            frame,
            target_column=resolved_target,
            n_folds=config.n_folds,
            repeats=config.repeats,
            seed=seed,
            canonicalizer=canonicalizer,
        )
        notes.append(
            f"{config.repeats} repeat(s) of {config.n_folds}-fold stratified CV; fold membership "
            f"differs between repeats (seeded with {seed})."
        )
        notes.append(
            "Stratification preserves class proportions per fold. It does not keep entities "
            "together; rows of one entity appear in several folds' test sides."
        )
    elif config.kind == "group_cv":
        if resolved_entity is None:
            raise InfeasibleOperationError(
                "Group CV requires an entity/group column, which was not selected.",
                details={"strategy": config.kind},
            )
        generated = group_cv(
            frame,
            entity_column=resolved_entity,
            n_folds=config.n_folds,
            canonicalizer=canonicalizer,
        )
        notes.append(
            "Group k-fold: every entity appears in exactly one fold's test side across the whole "
            "plan, so per-fold audits measure generalisation to unseen entities."
        )
        notes.append("Fold assignment is deterministic (no seed): GroupKFold balances group sizes.")
    elif config.kind == "rolling_origin":
        if resolved_timestamp is None:
            raise InfeasibleOperationError(
                "Rolling-origin validation requires a timestamp column, which was not selected.",
                details={"strategy": config.kind},
            )
        generated = rolling_origin(
            frame,
            timestamp_column=resolved_timestamp,
            n_folds=config.n_folds,
            gap=config.gap,
        )
        if config.gap:
            notes.append(
                f"{config.gap} row(s) are purged between each train block and its test block; a "
                "declared prediction horizon must not exceed this purge."
            )
        else:
            notes.append(
                "No purge gap is configured: check whether a prediction horizon or label delay "
                "straddles the train/test boundary of each fold."
            )
    else:
        raise InfeasibleOperationError(
            f"Plan kind {config.kind!r} is not supported.",
            details={"strategy": config.kind},
        )

    folds = [
        PlanFold(
            fold_index=index % config.n_folds + 1,
            repeat=index // config.n_folds + 1,
            train_rows=fold.masks.train_rows,
            test_rows=fold.masks.test_rows,
            train_row_ids=fold.masks.row_ids(dataset, "train"),
            test_row_ids=fold.masks.row_ids(dataset, "test"),
        )
        for index, fold in enumerate(generated)
    ]
    return EvaluationPlan(
        plan_id=plan_id,
        kind=config.kind,
        label=config.label,
        n_folds=config.n_folds,
        repeats=config.repeats,
        gap=config.gap,
        seed=seed,
        notes=notes + [note for fold in generated for note in fold.notes],
        folds=folds,
    )


__all__ = [
    "EvaluationPlan",
    "MAX_FOLDS",
    "MAX_REPEATS",
    "PlanConfig",
    "PlanFold",
    "build_plan",
]
