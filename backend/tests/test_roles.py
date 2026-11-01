"""Column-role validation and resolution."""

from __future__ import annotations

from app.audit.roles import validate_roles

from .conftest import make_dataset, make_roles

ROWS = [
    {"grp": "G1", "feat": "1", "label": "0", "ts": "2024-01-01T00:00:00Z", "split": "train", "note": "a"},
    {"grp": "G1", "feat": "2", "label": "1", "ts": "2024-01-02T00:00:00Z", "split": "train", "note": "b"},
    {"grp": "G2", "feat": "3", "label": "0", "ts": "2024-01-03T00:00:00Z", "split": "test", "note": "c"},
    {"grp": "G2", "feat": "4", "label": "1", "ts": "2024-01-04T00:00:00Z", "split": "test", "note": "d"},
]


def codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_valid_roles_resolve_with_unused_columns_listed():
    dataset = make_dataset(ROWS)
    validation = validate_roles(
        dataset,
        make_roles(features=["feat"], target="label", entity="grp", timestamp="ts", split="split"),
    )
    assert validation.ok is True
    assert validation.resolved is not None
    assert validation.resolved.feature_columns == ["feat"]
    assert validation.resolved.unused_columns == ["note"]


def test_unknown_columns_are_reported_for_every_role():
    dataset = make_dataset(ROWS)
    validation = validate_roles(
        dataset,
        make_roles(features=["nope"], target="missing", entity="also_missing", split="split"),
    )
    assert validation.ok is False
    assert codes(validation) == {"unknown_column"}
    messages = " ".join(issue.message for issue in validation.issues)
    assert "feature column" in messages
    assert "target column" in messages
    assert "entity column" in messages


def test_role_overlap_between_feature_and_target_is_an_error():
    dataset = make_dataset(ROWS)
    validation = validate_roles(dataset, make_roles(features=["label"], target="label", split="split"))
    assert validation.ok is False
    assert "role_overlap" in codes(validation)


def test_metadata_column_cannot_also_be_a_feature():
    dataset = make_dataset(ROWS)
    validation = validate_roles(
        dataset,
        make_roles(features=["note"], split="split", metadata_excluded=["note"]),
    )
    assert validation.ok is False
    assert "column_multi_role" in codes(validation)


def test_duplicate_feature_entries_are_collapsed_with_a_warning():
    dataset = make_dataset(ROWS)
    validation = validate_roles(dataset, make_roles(features=["feat", "feat"], split="split"))
    assert validation.ok is True
    assert validation.resolved is not None
    assert validation.resolved.feature_columns == ["feat"]
    assert "duplicate_feature_entry" in codes(validation)


def test_missing_or_equal_split_labels_are_errors():
    dataset = make_dataset(ROWS)
    missing = validate_roles(dataset, make_roles(features=["feat"], split="split", train_value=None, test_value=None))
    assert missing.ok is False
    assert "missing_split_values" in codes(missing)

    equal = validate_roles(
        dataset, make_roles(features=["feat"], split="split", train_value="train", test_value="train")
    )
    assert equal.ok is False
    assert "split_values_equal" in codes(equal)


def test_split_label_that_does_not_occur_is_an_error():
    dataset = make_dataset(ROWS)
    validation = validate_roles(
        dataset, make_roles(features=["feat"], split="split", train_value="train", test_value="holdout")
    )
    assert validation.ok is False
    assert "split_value_absent" in codes(validation)


def test_extra_split_labels_are_a_warning_and_are_not_folded_in():
    rows = [
        *ROWS,
        {
            "grp": "G3",
            "feat": "5",
            "label": "0",
            "ts": "2024-01-05T00:00:00Z",
            "split": "validation",
            "note": "e",
        },
    ]
    validation = validate_roles(
        make_dataset(rows), make_roles(features=["feat"], split="split")
    )
    assert validation.ok is True
    issue = next(issue for issue in validation.issues if issue.code == "split_labels_unsupported")
    assert issue.severity == "warning"
    assert "validation" in issue.message


def test_constant_feature_and_constant_target_produce_warnings():
    rows = [
        {"flat": "7", "label": "0", "split": "train"},
        {"flat": "7", "label": "0", "split": "train"},
        {"flat": "7", "label": "0", "split": "test"},
        {"flat": "7", "label": "0", "split": "test"},
    ]
    validation = validate_roles(make_dataset(rows), make_roles(features=["flat"], target="label", split="split"))
    assert validation.ok is True
    assert {"constant_feature", "constant_target"} <= codes(validation)


def test_invalid_timestamps_are_a_warning_when_most_values_parse():
    rows = [
        {"ts": "2024-01-01T00:00:00Z", "feat": "1", "split": "train"},
        {"ts": "bad", "feat": "2", "split": "train"},
        {"ts": "2024-01-03T00:00:00Z", "feat": "3", "split": "test"},
        {"ts": "2024-01-04T00:00:00Z", "feat": "4", "split": "test"},
    ]
    validation = validate_roles(make_dataset(rows), make_roles(features=["feat"], timestamp="ts", split="split"))
    assert validation.ok is True
    issue = next(issue for issue in validation.issues if issue.code == "invalid_timestamp_values")
    assert issue.severity == "warning"


def test_invalid_timestamps_are_an_error_when_most_values_do_not_parse():
    rows = [
        {"ts": "bad", "feat": "1", "split": "train"},
        {"ts": "worse", "feat": "2", "split": "train"},
        {"ts": "2024-01-03T00:00:00Z", "feat": "3", "split": "test"},
        {"ts": "nope", "feat": "4", "split": "test"},
    ]
    validation = validate_roles(make_dataset(rows), make_roles(features=["feat"], timestamp="ts", split="split"))
    assert validation.ok is False
    issue = next(issue for issue in validation.issues if issue.code == "invalid_timestamp_values")
    assert issue.severity == "error"


def test_single_row_per_side_is_a_warning_not_an_error():
    rows = [
        {"feat": "1", "split": "train"},
        {"feat": "2", "split": "test"},
    ]
    validation = validate_roles(make_dataset(rows), make_roles(features=["feat"], split="split"))
    assert validation.ok is True
    issue = next(issue for issue in validation.issues if issue.code == "insufficient_split_size")
    assert issue.severity == "warning"


def test_audit_without_any_analysable_role_is_rejected():
    validation = validate_roles(make_dataset(ROWS), make_roles(features=[], split="split"))
    assert validation.ok is False
    assert "no_analysis_roles" in codes(validation)


def test_all_missing_feature_is_flagged():
    rows = [
        {"empty": "", "feat": "1", "split": "train"},
        {"empty": "", "feat": "2", "split": "train"},
        {"empty": "", "feat": "3", "split": "test"},
        {"empty": "", "feat": "4", "split": "test"},
    ]
    validation = validate_roles(make_dataset(rows), make_roles(features=["empty"], split="split"))
    assert validation.ok is True
    assert "all_missing_feature" in codes(validation)


def test_degenerate_group_column_that_is_unique_per_row_is_a_warning():
    rows = [
        {"rowkey": "r1", "feat": "1", "split": "train"},
        {"rowkey": "r2", "feat": "2", "split": "train"},
        {"rowkey": "r3", "feat": "3", "split": "test"},
        {"rowkey": "r4", "feat": "4", "split": "test"},
    ]
    validation = validate_roles(make_dataset(rows), make_roles(features=["feat"], entity="rowkey", split="split"))
    assert validation.ok is True
    assert "degenerate_groups" in codes(validation)


def test_invalid_labels_do_not_produce_a_resolved_role_set():
    validation = validate_roles(make_dataset(ROWS), make_roles(features=["nope"], split="split"))
    assert validation.resolved is None
