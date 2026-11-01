"""SS-TGT-001: feature values that match the target."""

from __future__ import annotations

from app.audit.types import AuditConfig

from .conftest import count_for, findings_for, make_dataset, make_roles, metric_for, run_audit_for

RULE = "SS-TGT-001"


def _rows(feature_values, target_values, extra=None):
    rows = []
    for index, (feature, target) in enumerate(zip(feature_values, target_values, strict=True)):
        row = {"f": feature, "y": target, "split": "train" if index % 3 else "test"}
        if extra:
            row.update(extra(index))
        rows.append(row)
    return rows


BACKUP_ROLES = make_roles(features=["f"], target="y", split="split")


def test_perfect_copy_is_reported_as_high_with_full_coverage():
    targets = ["0", "1"] * 20
    dataset = make_dataset(_rows(list(targets), targets))
    result = run_audit_for(dataset, BACKUP_ROLES)

    finding = findings_for(result, RULE)[0]
    assert finding.severity == "high"
    matches = count_for(finding, "Comparable values where the feature equals the target")
    assert (matches.affected, matches.denominator) == (40, 40)
    assert count_for(finding, "Comparable values where the feature differs").affected == 0


def test_partial_copy_above_ninety_percent_is_medium():
    targets = ["0", "1"] * 50
    feature = list(targets)
    for index in range(0, 100, 20):  # flip 5 of 100 -> 95% coverage
        feature[index] = "1" if feature[index] == "0" else "0"
    dataset = make_dataset(_rows(feature, targets))
    result = run_audit_for(dataset, BACKUP_ROLES)

    finding = findings_for(result, RULE)[0]
    assert finding.severity == "medium"
    matches = count_for(finding, "Comparable values where the feature equals the target")
    assert (matches.affected, matches.denominator) == (95, 100)
    assert count_for(finding, "Comparable values where the feature differs").affected == 5
    assert any("Counterexamples" in example.label for example in finding.examples)


def test_coverage_below_the_threshold_is_not_reported():
    targets = ["0", "1"] * 50
    feature = list(targets)
    for index in range(0, 100, 5):  # flip 20 of 100 -> 80% coverage, below 90%
        feature[index] = "1" if feature[index] == "0" else "0"
    result = run_audit_for(make_dataset(_rows(feature, targets)), BACKUP_ROLES)
    assert findings_for(result, RULE) == []


def test_coverage_explained_by_the_majority_class_is_downgraded_to_low():
    # Target: 90 ones and 10 zeros. The feature matches the target on 80 of the
    # ones and all 10 zeros: coverage 90 of 100 = 90%, exactly the target's
    # majority-class rate, so predicting the majority class alone would achieve it.
    targets = ["1"] * 90 + ["0"] * 10
    feature = ["1"] * 80 + ["0"] * 20
    dataset = make_dataset(_rows(feature, targets))
    result = run_audit_for(dataset, BACKUP_ROLES)

    finding = findings_for(result, RULE)[0]
    assert finding.severity == "low"
    assert count_for(finding, "Comparable values where the feature equals the target").affected == 90
    assert "majority-class rate" in finding.severity_rationale


def test_constant_feature_against_a_varying_target_is_skipped():
    targets = ["0", "1"] * 20
    dataset = make_dataset(_rows(["same"] * 40, targets))
    result = run_audit_for(dataset, BACKUP_ROLES)

    assert findings_for(result, RULE) == []
    assert "f" in str(metric_for(result, RULE, "constant_features_skipped"))


def test_constant_target_reports_insufficient_data():
    dataset = make_dataset(_rows(["1"] * 40, ["1"] * 40))
    result = run_audit_for(dataset, BACKUP_ROLES)
    check = next(item for item in result.evaluation.not_evaluated if item.rule_id == RULE)
    assert check.status == "insufficient_data"
    assert findings_for(result, RULE) == []


def test_numeric_equivalence_matches_one_against_one_point_zero():
    targets = [str(index % 2) for index in range(40)]
    features = ["1.0" if value == "1" else "0.0" for value in targets]
    result = run_audit_for(make_dataset(_rows(features, targets)), BACKUP_ROLES)
    finding = findings_for(result, RULE)[0]
    assert count_for(finding, "Comparable values where the feature equals the target").affected == 40


def test_missing_values_are_excluded_and_counted():
    targets = ["0", "1"] * 20
    features = list(targets)
    features[0] = ""
    features[1] = ""
    dataset = make_dataset(_rows(features, targets))
    result = run_audit_for(dataset, BACKUP_ROLES)

    finding = findings_for(result, RULE)[0]
    assert count_for(finding, "Rows excluded because the feature value is missing").affected == 2
    comparable = count_for(finding, "Rows where both the feature and the target are non-missing")
    assert comparable.affected == 38


def test_minimum_comparable_rows_guard_prevents_small_sample_matches():
    targets = ["0", "1", "0", "1"]
    dataset = make_dataset(_rows(list(targets), targets))
    result = run_audit_for(dataset, BACKUP_ROLES)
    assert findings_for(result, RULE) == []
    assert metric_for(result, RULE, "min_coverage_threshold") == 0.9


def test_two_features_can_produce_two_separate_findings():
    targets = ["0", "1"] * 20
    rows = []
    for index, target in enumerate(targets):
        rows.append(
            {
                "f": target,
                "g": "1" if target == "0" else "0",  # deliberately inverted: no match
                "y": target,
                "split": "train" if index % 3 else "test",
            }
        )
    result = run_audit_for(make_dataset(rows), make_roles(features=["f", "g"], target="y", split="split"))
    findings = findings_for(result, RULE)
    assert len(findings) == 1
    assert "'f'" in findings[0].title

    rows_inverted = []
    for index, target in enumerate(targets):
        rows_inverted.append(
            {"f": target, "g": target, "y": target, "split": "train" if index % 3 else "test"}
        )
    result = run_audit_for(
        make_dataset(rows_inverted), make_roles(features=["f", "g"], target="y", split="split")
    )
    assert len(findings_for(result, RULE)) == 2


def test_high_coverage_threshold_is_configurable():
    targets = ["0", "1"] * 20
    features = list(targets)
    features[0] = "1" if features[0] == "0" else "0"
    dataset = make_dataset(_rows(features, targets))
    strict = run_audit_for(dataset, BACKUP_ROLES, AuditConfig(target_copy_high_coverage=1.0))
    assert findings_for(strict, RULE)[0].severity == "medium"
