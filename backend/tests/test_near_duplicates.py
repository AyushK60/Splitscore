"""SS-NEAR-001: near-duplicate candidates, thresholds and bounds."""

from __future__ import annotations

from app.audit.rules.near_duplicates import _proportional_sample
from app.audit.types import AuditConfig, NearDuplicateSettings

from .conftest import count_for, findings_for, make_dataset, make_roles, metric_for, run_audit_for

RULE = "SS-NEAR-001"
ROLES = make_roles(features=["a", "b"], split="split")


def _config(*, audit: dict | None = None, **near_duplicate) -> AuditConfig:
    return AuditConfig(
        near_duplicates=NearDuplicateSettings(enabled=True, **near_duplicate),
        **(audit or {}),
    )


def _base_rows() -> list[dict[str, str]]:
    """a: 0..9 train, 20..29 test, plus one test row at a=9.05 that mirrors train a=9."""
    rows = [{"a": str(index), "b": str(index * 3), "split": "train"} for index in range(10)]
    rows += [{"a": str(20 + index), "b": str((20 + index) * 3), "split": "test"} for index in range(10)]
    rows.append({"a": "9.05", "b": "27.15", "split": "test"})
    return rows


def test_disabled_by_default_reports_a_disabled_status():
    result = run_audit_for(make_dataset(_base_rows()), ROLES)
    assert findings_for(result, RULE) == []
    check = next(item for item in result.evaluation.not_evaluated if item.rule_id == RULE)
    assert check.status == "disabled"


def test_planted_pair_is_found_and_other_pairs_are_not():
    result = run_audit_for(make_dataset(_base_rows()), ROLES, _config(threshold=0.05))
    findings = findings_for(result, RULE)
    assert len(findings) == 1
    finding = findings[0]

    pairs = count_for(finding, "Cross-split candidate pairs")
    assert pairs.affected == 1
    assert pairs.denominator == 11 * 10  # 11 analysed test rows x 10 analysed train rows

    assert count_for(finding, "Analysed test rows in at least one candidate pair").affected == 1
    assert count_for(finding, "Analysed train rows in at least one candidate pair").affected == 1

    example = finding.examples[0]
    train_row, test_row = example.row_ids
    assert train_row == "row-000010"  # the train row with a=9, b=27
    assert test_row == "row-000021"  # the appended test row with a=9.05, b=27.15
    assert "a:" in example.details["top_feature_differences"]


def test_severity_never_exceeds_medium():
    rows = [
        {"a": str(index), "b": str(index), "split": "test" if index % 2 == 0 else "train"}
        for index in range(60)
    ]
    result = run_audit_for(make_dataset(rows), ROLES, _config(threshold=0.5))
    finding = findings_for(result, RULE)[0]
    assert finding.severity == "medium"
    assert "screening signal" in finding.severity_rationale.lower()


def test_threshold_zero_only_matches_identical_rows():
    rows = [
        {"a": "1", "b": "2", "split": "train"},
        {"a": "1", "b": "2", "split": "test"},
        {"a": "1", "b": "2.4", "split": "test"},
        {"a": "5", "b": "9", "split": "train"},
        {"a": "12", "b": "20", "split": "test"},
    ]
    dataset = make_dataset(rows)

    strict = run_audit_for(dataset, ROLES, _config(threshold=0.0))
    assert count_for(findings_for(strict, RULE)[0], "Cross-split candidate pairs").affected == 1

    # The second pair differs by 0.4 in `b` = 0.057 interquartile ranges, so a
    # 0.06 threshold admits it and nothing else.
    near = run_audit_for(dataset, ROLES, _config(threshold=0.06))
    assert count_for(findings_for(near, RULE)[0], "Cross-split candidate pairs").affected == 2


def test_constant_numeric_columns_are_excluded_and_reported():
    rows = [{"a": str(index), "b": str(index * 3), "c": "7", "split": "train"} for index in range(10)]
    rows += [{"a": str(20 + index), "b": str((20 + index) * 3), "c": "7", "split": "test"} for index in range(10)]
    roles = make_roles(features=["a", "b", "c"], split="split")
    result = run_audit_for(make_dataset(rows), roles, _config(threshold=0.05))

    assert "c" in str(metric_for(result, RULE, "constant_columns_excluded"))
    assert "c" not in str(metric_for(result, RULE, "columns_used"))
    assert findings_for(result, RULE) == []


def test_non_numeric_columns_are_excluded_and_reported():
    rows = [{"a": str(index), "b": "text", "split": "train"} for index in range(10)]
    rows += [{"a": str(20 + index), "b": "text", "split": "test"} for index in range(10)]
    result = run_audit_for(make_dataset(rows), ROLES, _config())

    assert "b" in str(metric_for(result, RULE, "feature_columns_excluded"))
    assert metric_for(result, RULE, "numeric_feature_columns_used") == 1


def test_unsupported_when_no_feature_column_is_numeric():
    rows = [{"a": "x", "b": "y", "split": "train"}, {"a": "x2", "b": "y2", "split": "test"}]
    result = run_audit_for(make_dataset(rows), ROLES, _config())
    assert findings_for(result, RULE) == []
    check = next(item for item in result.evaluation.not_evaluated if item.rule_id == RULE)
    assert check.status == "unsupported"


def test_rows_with_too_many_missing_values_are_excluded_and_counted():
    rows = [{"a": str(index), "b": str(index * 3), "split": "train"} for index in range(10)]
    rows += [{"a": str(20 + index), "b": str((20 + index) * 3), "split": "test"} for index in range(10)]
    rows.append({"a": "", "b": "", "split": "test"})
    result = run_audit_for(make_dataset(rows), ROLES, _config())
    assert metric_for(result, RULE, "rows_excluded_missingness") == 1


def test_zero_iqr_non_constant_column_is_excluded_under_robust_scaling():
    # `b` is 0 for almost every row and 100 for two rows: interquartile range is
    # zero even though the column is not constant, so it cannot be robustly scaled.
    rows = [{"a": str(index), "b": "0", "split": "train"} for index in range(10)]
    rows += [{"a": str(20 + index), "b": "0", "split": "test"} for index in range(10)]
    rows[0]["b"] = "100"
    rows[-1]["b"] = "100"
    dataset = make_dataset(rows)

    robust = run_audit_for(dataset, ROLES, _config(scaling="robust"))
    assert "b" in str(metric_for(robust, RULE, "zero_iqr_columns_excluded"))

    unscaled = run_audit_for(dataset, ROLES, _config(scaling="none"))
    assert metric_for(unscaled, RULE, "zero_iqr_columns_excluded") == "(none)"
    assert "b" in str(metric_for(unscaled, RULE, "columns_used"))


def test_oversize_input_is_skipped_when_the_policy_is_skip():
    rows = [
        {"a": str(index), "b": str(index), "split": "test" if index % 4 == 0 else "train"}
        for index in range(600)
    ]
    result = run_audit_for(
        make_dataset(rows), ROLES, _config(oversize_policy="skip", max_combined_rows=500)
    )
    check = next(item for item in result.evaluation.not_evaluated if item.rule_id == RULE)
    assert check.status == "not_evaluated"
    assert "600" in check.reason
    assert findings_for(result, RULE) == []


def test_oversize_sample_is_disclosed_and_reproducible():
    rows = [
        {"a": str(index), "b": str(index), "split": "test" if index % 4 == 0 else "train"}
        for index in range(600)
    ]
    dataset = make_dataset(rows)
    config = _config(oversize_policy="sample", max_combined_rows=200, sample_seed=11)

    first = run_audit_for(dataset, ROLES, config)
    second = run_audit_for(dataset, ROLES, config)

    first_finding = findings_for(first, RULE)[0]
    second_finding = findings_for(second, RULE)[0]
    pairs = count_for(first_finding, "Cross-split candidate pairs")

    assert "sample" in pairs.scope.lower()
    assert "not a dataset-wide estimate" in pairs.scope.lower()
    assert metric_for(first, RULE, "sampled_rows") == 200
    assert pairs.affected == count_for(second_finding, "Cross-split candidate pairs").affected
    assert first_finding.examples[0].row_ids == second_finding.examples[0].row_ids

    assert first_finding.examples  # the sampled analysis still carries evidence
    assert int(metric_for(first, RULE, "combined_rows_before_bounding")) == 600
    assert int(metric_for(first, RULE, "effective_row_bound")) == 200


def test_proportional_sampler_is_a_pure_function_of_its_seed():
    train = list(range(0, 400))
    test = list(range(400, 600))

    first = _proportional_sample(1, train, test, 120)
    repeat = _proportional_sample(1, train, test, 120)
    other = _proportional_sample(2, train, test, 120)

    assert first == repeat
    assert len(first[0]) + len(first[1]) == 120
    assert first[0] and first[1]  # neither side is empty
    assert first != other


def test_sampler_keeps_both_sides_non_empty_at_the_smallest_bound():
    train, test = _proportional_sample(3, list(range(20)), list(range(20, 30)), 2)
    assert len(train) == 1
    assert len(test) == 1


def test_examples_are_bounded_by_max_examples():
    rows = [
        {"a": str(index), "b": str(index), "split": "test" if index % 2 == 0 else "train"}
        for index in range(60)
    ]
    result = run_audit_for(
        make_dataset(rows), ROLES, _config(audit={"max_examples": 2}, threshold=10.0)
    )
    finding = findings_for(result, RULE)[0]
    assert len(finding.examples) == 2
    assert finding.examples_truncated is True
    assert all("distance" in example.details for example in finding.examples)
