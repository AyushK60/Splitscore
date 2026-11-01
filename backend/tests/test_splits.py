"""Split strategies and comparison.

These tests check the properties that make a strategy trustworthy: determinism,
group isolation, tie preservation, achieved-fraction honesty, and explicit
refusal when a strategy is infeasible.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.audit.canonical import ValueCanonicalizer
from app.audit.service import resolve_or_raise
from app.audit.types import AuditConfig, SplitConfig
from app.core.errors import InfeasibleOperationError
from app.splits.comparison import compare_splits
from app.splits.strategies import (
    chronological_holdout,
    group_holdout,
    random_holdout,
    stratified_holdout,
)

from .conftest import make_dataset, make_roles


def _panel_rows(customers: int = 20, months: int = 6) -> list[dict[str, str]]:
    rows = []
    for customer in range(customers):
        for month in range(months):
            rows.append(
                {
                    "customer_id": f"C-{customer:03d}",
                    "tenure_months": str(month + 1),
                    "spend": str(10 * customer + month),
                    "split": "train" if (customer + month) % 3 else "test",
                }
            )
    return rows


# --------------------------------------------------------------------------- #
# Random holdout
# --------------------------------------------------------------------------- #


def test_random_holdout_is_reproducible_for_a_seed():
    first = random_holdout(100, 0.25, seed=7)
    second = random_holdout(100, 0.25, seed=7)
    third = random_holdout(100, 0.25, seed=8)

    assert np.array_equal(first.masks.test, second.masks.test)
    assert not np.array_equal(first.masks.test, third.masks.test)
    assert first.masks.test_rows == 25
    assert first.masks.train_rows == 75


def test_random_holdout_rejects_an_out_of_range_fraction():
    with pytest.raises(InfeasibleOperationError):
        random_holdout(100, 1.5, seed=1)
    with pytest.raises(InfeasibleOperationError):
        random_holdout(100, 0.0, seed=1)


def test_random_holdout_refuses_datasets_too_small_for_two_rows_per_side():
    with pytest.raises(InfeasibleOperationError):
        random_holdout(3, 0.25, seed=1)


# --------------------------------------------------------------------------- #
# Group holdout
# --------------------------------------------------------------------------- #


def test_group_holdout_keeps_every_entity_on_one_side():
    dataset = make_dataset(_panel_rows())
    canonicalizer = ValueCanonicalizer()
    generated = group_holdout(
        dataset.frame,
        entity_column="customer_id",
        test_fraction=0.25,
        seed=12345,
        canonicalizer=canonicalizer,
    )
    frame = dataset.frame
    train = frame[generated.masks.train]
    test = frame[generated.masks.test]

    assert set(train["customer_id"]).isdisjoint(set(test["customer_id"]))
    assert generated.masks.train_rows + generated.masks.test_rows == len(frame)
    assert "requested" in (generated.proportion_note or "")
    assert "can only move in steps of group size" in (generated.proportion_note or "")


def test_group_holdout_is_deterministic_and_group_count_is_reported():
    dataset = make_dataset(_panel_rows())
    canonicalizer = ValueCanonicalizer()
    kwargs = {
        "entity_column": "customer_id",
        "test_fraction": 0.25,
        "seed": 99,
        "canonicalizer": canonicalizer,
    }
    first = group_holdout(dataset.frame, **kwargs)
    second = group_holdout(dataset.frame, **kwargs)
    assert np.array_equal(first.masks.test, second.masks.test)
    assert first.extra_metrics["groups"] == 20


def test_rows_without_an_entity_identifier_become_their_own_groups():
    rows = _panel_rows()
    rows.append({"customer_id": "", "tenure_months": "1", "spend": "1", "split": "train"})
    rows.append({"customer_id": "", "tenure_months": "2", "spend": "2", "split": "test"})
    dataset = make_dataset(rows)
    generated = group_holdout(
        dataset.frame,
        entity_column="customer_id",
        test_fraction=0.5,
        seed=5,
        canonicalizer=ValueCanonicalizer(),
    )
    # 22 groups: 20 customers plus two singletons for the empty identifiers.
    assert generated.extra_metrics["groups"] == 22
    assert any("empty entity identifier" in note for note in generated.notes)


def test_group_holdout_requires_an_entity_column():
    dataset = make_dataset(_panel_rows())
    resolved, _ = resolve_or_raise(
        dataset, make_roles(features=["spend"], split="split")
    )
    from app.splits.strategies import generate_split

    with pytest.raises(InfeasibleOperationError) as error:
        generate_split(
            dataset,
            resolved_entity=resolved.entity_column,
            resolved_target=resolved.target_column,
            resolved_timestamp=resolved.timestamp_column,
            config=SplitConfig(kind="group", label="Group", test_fraction=0.25, seed=1),
            canonicalizer=ValueCanonicalizer(),
        )
    assert "entity" in error.value.message


# --------------------------------------------------------------------------- #
# Stratified holdout
# --------------------------------------------------------------------------- #


def test_stratified_holdout_preserves_class_proportions():
    rows = []
    for index in range(100):
        rows.append(
            {
                "x": str(index),
                "label": "positive" if index < 30 else "negative",
                "split": "train" if index % 4 else "test",
            }
        )
    dataset = make_dataset(rows)
    generated = stratified_holdout(
        dataset.frame,
        target_column="label",
        test_fraction=0.25,
        seed=3,
        canonicalizer=ValueCanonicalizer(),
    )
    frame = dataset.frame
    train_positive = int((frame.loc[generated.masks.train, "label"] == "positive").sum())
    test_positive = int((frame.loc[generated.masks.test, "label"] == "positive").sum())

    assert train_positive + test_positive == 30  # no row is lost or duplicated
    assert train_positive > 0 and test_positive > 0  # both classes on both sides
    train_share = train_positive / generated.masks.train_rows
    test_share = test_positive / generated.masks.test_rows
    assert abs(train_share - test_share) <= 0.05
    assert "class" in generated.notes[0].lower()


def test_stratified_holdout_is_infeasible_when_a_class_has_one_row():
    rows = [{"x": str(index), "label": "common" if index else "rare", "split": "train"} for index in range(40)]
    dataset = make_dataset(rows)
    with pytest.raises(InfeasibleOperationError) as error:
        stratified_holdout(
            dataset.frame,
            target_column="label",
            test_fraction=0.25,
            seed=1,
            canonicalizer=ValueCanonicalizer(),
        )
    assert "fewer than two rows" in error.value.message


def test_stratified_holdout_is_infeasible_when_the_test_size_cannot_hold_every_class():
    # 20 classes with 2 rows each, but a 5% test fraction allows only 2 test rows.
    rows = []
    for label in range(20):
        for _ in range(2):
            rows.append({"x": str(len(rows)), "label": f"class-{label}", "split": "train"})
    dataset = make_dataset(rows)
    with pytest.raises(InfeasibleOperationError) as error:
        stratified_holdout(
            dataset.frame,
            target_column="label",
            test_fraction=0.05,
            seed=1,
            canonicalizer=ValueCanonicalizer(),
        )
    assert "fewer than the" in error.value.message


def test_stratified_holdout_is_infeasible_with_a_constant_target():
    rows = [{"x": str(index), "label": "same", "split": "train"} for index in range(20)]
    dataset = make_dataset(rows)
    with pytest.raises(InfeasibleOperationError):
        stratified_holdout(
            dataset.frame,
            target_column="label",
            test_fraction=0.25,
            seed=1,
            canonicalizer=ValueCanonicalizer(),
        )


# --------------------------------------------------------------------------- #
# Chronological holdout
# --------------------------------------------------------------------------- #


def test_chronological_holdout_orders_records_and_keeps_ties_together():
    rows = []
    for index in range(100):
        # Four rows share each timestamp, so the cut must land on a boundary.
        rows.append({"ts": f"2024-01-{index // 4 + 1:02d}T00:00:00Z", "x": str(index), "split": "train"})
    dataset = make_dataset(rows)
    generated = chronological_holdout(dataset.frame, timestamp_column="ts", test_fraction=0.25)

    import pandas as pd

    parsed = pd.to_datetime(dataset.frame["ts"], utc=True)
    train_max = parsed[generated.masks.train].max()
    test_min = parsed[generated.masks.test].min()
    assert train_max < test_min

    # 25 test rows requested, but ties push the cut to 24 or 28 (a whole 4-row block).
    assert generated.masks.test_rows in (24, 28)
    assert "keep every row sharing the boundary timestamp together" in (generated.proportion_note or "")


def test_chronological_holdout_refuses_unparsable_timestamps():
    rows = [
        {"ts": "2024-01-01", "x": "1", "split": "train"},
        {"ts": "not-a-timestamp", "x": "2", "split": "test"},
    ]
    dataset = make_dataset(rows)
    with pytest.raises(InfeasibleOperationError) as error:
        chronological_holdout(dataset.frame, timestamp_column="ts", test_fraction=0.5)
    assert "do not parse as timestamps" in error.value.message


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #


def _compare(dataset, roles, strategies, config=None):
    resolved, _validation = resolve_or_raise(dataset, roles)
    from app.core.config import get_settings

    return compare_splits(
        dataset=dataset,
        roles=roles,
        resolved=resolved,
        strategies=strategies,
        config=config or AuditConfig(),
        settings=get_settings(),
    )


def test_group_holdout_removes_entity_overlap_that_the_existing_split_has():
    dataset = make_dataset(_panel_rows())
    roles = make_roles(features=["tenure_months", "spend"], entity="customer_id", split="split")
    strategies = [
        SplitConfig(kind="group", label="Group holdout", test_fraction=0.25, seed=12345),
        SplitConfig(kind="random", label="Random holdout", test_fraction=0.25, seed=12345),
    ]
    result, assignments, _meta = _compare(dataset, roles, strategies)

    by_label = {row.label: row for row in result.rows}
    assert by_label["Existing split column"].entity_shared_groups and by_label["Existing split column"].entity_shared_groups > 0
    assert by_label["Group holdout"].entity_shared_groups == 0
    assert by_label["Group holdout"].finding_counts.get("SS-ENT-001") is None
    assert by_label["Random holdout"].entity_shared_groups and by_label["Random holdout"].entity_shared_groups > 0

    group_assignment = next(
        assignment for assignment in assignments.values() if assignment.summary.kind == "group"
    )
    train_entities = {
        dataset.frame.iloc[index]["customer_id"]
        for index, row_id in enumerate(dataset.row_ids)
        if row_id in set(group_assignment.train_row_ids)
    }
    test_entities = {
        dataset.frame.iloc[index]["customer_id"]
        for index, row_id in enumerate(dataset.row_ids)
        if row_id in set(group_assignment.test_row_ids)
    }
    assert train_entities.isdisjoint(test_entities)


def test_comparison_generates_stratified_and_chronological_assignments_end_to_end():
    """The public comparison orchestrates stratified + chronological generation,
    auditing, and assignment export: every row appears exactly once per
    assignment, and the chronology verdict agrees with temporal facts computed
    from the original fixture timestamps joined through the row ids."""
    import pandas as pd

    rows = []
    for index in range(20):
        rows.append(
            {
                "ts": f"2024-02-{index + 1:02d}T00:00:00Z",
                "x": str(index),
                "label": "A" if index < 8 else "B",
                "split": "train" if index % 4 else "test",
            }
        )
    dataset = make_dataset(rows)
    roles = make_roles(features=["x"], target="label", timestamp="ts", split="split")
    strategies = [
        SplitConfig(kind="stratified", label="Stratified", test_fraction=0.25, seed=5),
        SplitConfig(kind="chronological", label="Chronological", test_fraction=0.25, seed=1),
    ]
    result, assignments, _meta = _compare(dataset, roles, strategies)

    by_label = {row.label: row for row in result.rows}
    assert by_label["Stratified"].supported is True
    assert by_label["Chronological"].supported is True

    all_ids = set(dataset.row_ids)
    parsed = pd.to_datetime(dataset.frame["ts"], utc=True)
    row_id_to_position = {row_id: index for index, row_id in enumerate(dataset.row_ids)}

    for kind in ("stratified", "chronological"):
        assignment = next(a for a in assignments.values() if a.summary.kind == kind)
        train_ids, test_ids = set(assignment.train_row_ids), set(assignment.test_row_ids)
        assert train_ids.isdisjoint(test_ids)
        assert train_ids | test_ids == all_ids
        assert len(assignment.train_row_ids) == len(train_ids)
        assert len(assignment.test_row_ids) == len(test_ids)

    chrono = next(a for a in assignments.values() if a.summary.kind == "chronological")
    train_times = parsed.iloc[[row_id_to_position[r] for r in chrono.train_row_ids]]
    test_times = parsed.iloc[[row_id_to_position[r] for r in chrono.test_row_ids]]
    assert train_times.max() < test_times.min()
    assert set(train_times).isdisjoint(test_times)
    assert by_label["Chronological"].chronology_status == "ordered"

    stratified = next(a for a in assignments.values() if a.summary.kind == "stratified")
    frame = dataset.frame
    train_labels = frame.iloc[[row_id_to_position[r] for r in stratified.train_row_ids]]["label"]
    test_labels = frame.iloc[[row_id_to_position[r] for r in stratified.test_row_ids]]["label"]
    assert set(train_labels) == {"A", "B"} and set(test_labels) == {"A", "B"}
    # Documented contract: class *proportions* are preserved across the cut.
    train_share_a = (train_labels == "A").sum() / len(train_labels)
    test_share_a = (test_labels == "A").sum() / len(test_labels)
    assert abs(train_share_a - test_share_a) < 1e-9


def test_comparison_marks_infeasible_strategies_and_still_lists_them():
    dataset = make_dataset(_panel_rows())
    roles = make_roles(features=["tenure_months", "spend"], split="split")
    strategies = [
        SplitConfig(kind="group", label="Group by missing entity role", test_fraction=0.25, seed=1),
        SplitConfig(kind="stratified", label="Stratified without a target", test_fraction=0.25, seed=1),
        SplitConfig(kind="random", label="Random holdout", test_fraction=0.25, seed=1),
    ]
    result, _assignments, meta = _compare(dataset, roles, strategies)

    by_id = {row.strategy_id: row for row in result.rows}
    assert by_id["group-1"].supported is False
    assert "entity" in (by_id["group-1"].unsupported_reason or "")
    assert by_id["stratified-2"].supported is False
    assert "target" in (by_id["stratified-2"].unsupported_reason or "")
    assert by_id["random-3"].supported is True
    assert len(meta["unsupported"]) == 2
    assert set(result.per_strategy_findings) == {"existing", "random-3"}


def test_comparison_does_not_modify_the_uploaded_dataset():
    dataset = make_dataset(_panel_rows())
    before = dataset.frame.copy(deep=True)
    roles = make_roles(features=["tenure_months", "spend"], entity="customer_id", split="split")
    _compare(
        dataset,
        roles,
        [SplitConfig(kind="group", label="Group", test_fraction=0.25, seed=1)],
    )
    assert dataset.frame.equals(before)
    assert dataset.frame.columns.tolist() == before.columns.tolist()


def test_comparison_rows_expose_requested_and_achieved_fractions_separately():
    dataset = make_dataset(_panel_rows())
    roles = make_roles(features=["tenure_months", "spend"], entity="customer_id", split="split")
    result, _assignments, _meta = _compare(
        dataset, roles, [SplitConfig(kind="group", label="Group", test_fraction=0.10, seed=2)]
    )
    row = next(row for row in result.rows if row.kind == "group")
    assert row.requested_test_fraction == 0.10
    assert row.achieved_test_fraction is not None
    assert row.proportion_note


def test_comparison_carries_a_selection_note_and_limitations():
    dataset = make_dataset(_panel_rows())
    roles = make_roles(features=["tenure_months", "spend"], entity="customer_id", split="split")
    result, _assignments, _meta = _compare(dataset, roles, [])
    assert "no universally best split" in result.selection_note.lower()
    assert any("does not remove" in limitation for limitation in result.limitations)
