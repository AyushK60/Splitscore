"""SS-DUP-001.

Expected values in this file are written by hand from the fixtures below, not read
back from the rule.
"""

from __future__ import annotations

from app.audit.types import AuditConfig

from .conftest import count_for, findings_for, make_dataset, make_roles, metric_for, run_audit_for

RULE = "SS-DUP-001"

# 3 train rows, 4 test rows.
#   (a=1,b=x): one train, one test      -> cross-split group
#   (a=2,b=y): two train                -> within-train duplication only
#   (a=3,b=z): two test                 -> within-test duplication only
#   (a=4,b=w): one test, unique
MIXED_ROWS = [
    {"a": "1", "b": "x", "label": "0", "split": "train"},
    {"a": "1", "b": "x", "label": "1", "split": "test"},
    {"a": "2", "b": "y", "label": "0", "split": "train"},
    {"a": "2", "b": "y", "label": "1", "split": "train"},
    {"a": "3", "b": "z", "label": "0", "split": "test"},
    {"a": "3", "b": "z", "label": "1", "split": "test"},
    {"a": "4", "b": "w", "label": "0", "split": "test"},
]

MIXED_ROLES = make_roles(features=["a", "b"], target="label", split="split")


def test_cross_split_and_within_split_duplicates_are_counted_separately():
    dataset = make_dataset(MIXED_ROWS)
    result = run_audit_for(dataset, MIXED_ROLES)

    findings = findings_for(result, RULE)
    assert len(findings) == 1
    finding = findings[0]

    assert count_for(finding, "signatures present in both").affected == 1
    assert count_for(finding, "signatures present in both").denominator == 3  # distinct test signatures

    cross_test = count_for(finding, "Test rows sharing a feature signature with a train row")
    assert (cross_test.affected, cross_test.denominator) == (1, 4)

    cross_train = count_for(finding, "Train rows sharing a feature signature with a test row")
    assert (cross_train.affected, cross_train.denominator) == (1, 3)

    within_test = count_for(finding, "Test rows that are exact duplicates of another test row")
    assert (within_test.affected, within_test.denominator) == (2, 4)

    within_train = count_for(finding, "Train rows that are exact duplicates of another train row")
    assert (within_train.affected, within_train.denominator) == (2, 3)

    assert metric_for(result, RULE, "hash_bucket_collisions_rejected") == 0
    assert metric_for(result, RULE, "distinct_feature_signatures") == 4


def test_severity_follows_the_implicated_share_of_the_test_split():
    """1 of 4 test rows is 25% of the split, above the 5% high-severity threshold."""
    dataset = make_dataset(MIXED_ROWS)
    result = run_audit_for(dataset, MIXED_ROLES)
    finding = findings_for(result, RULE)[0]
    assert finding.severity == "high"
    assert "25.0%" in finding.severity_rationale


def test_severity_is_low_when_both_counts_and_share_are_small():
    rows = [{"a": str(index), "b": "b", "label": "0", "split": "train"} for index in range(400)]
    rows += [{"a": str(1000 + index), "b": "b", "label": "0", "split": "test"} for index in range(200)]
    rows.append({"a": "0", "b": "b", "label": "0", "split": "test"})  # duplicates train row 1
    result = run_audit_for(make_dataset(rows), MIXED_ROLES)

    finding = findings_for(result, RULE)[0]
    assert finding.severity == "low"
    assert count_for(finding, "Test rows sharing a feature signature").affected == 1
    assert count_for(finding, "Test rows sharing a feature signature").denominator == 201


def test_duplicates_entirely_inside_one_split_produce_no_finding():
    rows = [
        {"a": "1", "b": "x", "split": "train"},
        {"a": "1", "b": "x", "split": "train"},
        {"a": "2", "b": "y", "split": "train"},
        {"a": "3", "b": "z", "split": "test"},
        {"a": "4", "b": "w", "split": "test"},
    ]
    dataset = make_dataset(rows)
    result = run_audit_for(dataset, make_roles(features=["a", "b"], split="split"))

    assert findings_for(result, RULE) == []
    assert metric_for(result, RULE, "exact_duplicate_test_rows") == 0
    assert metric_for(result, RULE, "within_train_duplicate_rows") == 2


def test_target_and_unselected_columns_never_affect_feature_signatures():
    """Identical features with different targets are still a duplicate group."""
    rows = [
        {"a": "1", "b": "x", "noise": "alpha", "label": "0", "split": "train"},
        {"a": "1", "b": "x", "noise": "beta", "label": "1", "split": "test"},
    ]
    dataset = make_dataset(rows)
    result = run_audit_for(dataset, MIXED_ROLES)
    finding = findings_for(result, RULE)[0]
    assert count_for(finding, "Test rows sharing a feature signature").affected == 1


def test_a_difference_in_one_selected_feature_prevents_a_match():
    rows = [
        {"a": "1", "b": "x", "label": "0", "split": "train"},
        {"a": "1", "b": "X", "label": "0", "split": "test"},
    ]
    dataset = make_dataset(rows)
    result = run_audit_for(dataset, MIXED_ROLES)
    assert findings_for(result, RULE) == []


def test_missing_values_match_each_other_but_not_literal_strings():
    matching = [
        {"a": "", "b": "x", "label": "0", "split": "train"},
        {"a": "", "b": "x", "label": "0", "split": "test"},
    ]
    result = run_audit_for(make_dataset(matching), MIXED_ROLES)
    assert len(findings_for(result, RULE)) == 1

    non_matching = [
        {"a": "", "b": "x", "label": "0", "split": "train"},
        {"a": "NA", "b": "x", "label": "0", "split": "test"},
    ]
    result = run_audit_for(make_dataset(non_matching), MIXED_ROLES)
    assert findings_for(result, RULE) == []


def test_whitespace_stripping_is_applied_only_when_enabled():
    rows = [
        {"a": "1", "b": " x ", "label": "0", "split": "train"},
        {"a": "1", "b": "x", "label": "0", "split": "test"},
    ]
    dataset = make_dataset(rows)
    lenient = run_audit_for(dataset, MIXED_ROLES, AuditConfig(strip_whitespace=True))
    assert len(findings_for(lenient, RULE)) == 1

    strict = run_audit_for(dataset, MIXED_ROLES, AuditConfig(strip_whitespace=False))
    assert findings_for(strict, RULE) == []


def test_numeric_normalization_merges_one_and_one_point_zero_only_when_enabled():
    rows = [
        {"a": "1", "b": "x", "label": "0", "split": "train"},
        {"a": "1.0", "b": "x", "label": "0", "split": "test"},
    ]
    dataset = make_dataset(rows)
    default = run_audit_for(dataset, MIXED_ROLES)
    assert findings_for(default, RULE) == []

    normalized = run_audit_for(
        dataset, MIXED_ROLES, AuditConfig(normalize_numeric_strings=True)
    )
    assert len(findings_for(normalized, RULE)) == 1


def test_severity_is_high_when_ten_or_more_test_rows_are_implicated():
    rows = [{"a": str(index), "b": "b", "label": "0", "split": "train"} for index in range(200)]
    rows += [{"a": str(index), "b": "b", "label": "0", "split": "test"} for index in range(12)]
    result = run_audit_for(make_dataset(rows), MIXED_ROLES)
    finding = findings_for(result, RULE)[0]
    assert finding.severity == "high"  # 12 rows, and 12/12 = 100% of the test split
    assert count_for(finding, "Test rows sharing a feature signature").affected == 12


def test_evidence_examples_are_bounded_and_report_the_truncation():
    rows = [{"a": str(index), "b": "b", "label": "0", "split": "train"} for index in range(15)]
    rows += [{"a": str(index), "b": "b", "label": "0", "split": "test"} for index in range(15)]
    dataset = make_dataset(rows)
    result = run_audit_for(dataset, MIXED_ROLES, AuditConfig(max_examples=3))
    finding = findings_for(result, RULE)[0]
    assert len(finding.examples) == 3
    assert finding.example_total == 15
    assert finding.examples_truncated is True
    for example in finding.examples:
        assert len(example.row_ids) <= 2 * 4  # max_example_rows_per_example per side


def test_rule_reports_not_evaluated_without_feature_columns():
    """A target-only audit is allowed; feature-based checks step aside explicitly."""
    dataset = make_dataset(MIXED_ROWS)
    result = run_audit_for(dataset, make_roles(features=[], target="label", split="split"))

    assert findings_for(result, RULE) == []
    check = next(item for item in result.evaluation.not_evaluated if item.rule_id == RULE)
    assert check.status == "not_evaluated"
    assert any(
        check.status == "not_evaluated" for check in result.evaluation.not_evaluated
    )
    assert RULE not in result.evaluation.evaluated_rule_ids


def test_audit_is_rejected_when_no_check_could_run():
    import pytest

    from app.core.errors import ValidationFailure

    dataset = make_dataset(MIXED_ROWS)
    with pytest.raises(ValidationFailure) as error:
        run_audit_for(dataset, make_roles(features=[], split="split"))
    codes = {issue["code"] for issue in error.value.details["issues"]}
    assert "no_analysis_roles" in codes
