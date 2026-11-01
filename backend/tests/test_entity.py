"""SS-ENT-001: entity / group overlap."""

from __future__ import annotations

from app.audit.types import AuditConfig

from .conftest import count_for, findings_for, make_dataset, make_roles, metric_for, run_audit_for

RULE = "SS-ENT-001"

# Entities: C1 train+test, C2 train+test, C3 train only, C4 test only.
ROWS = [
    {"entity": "C1", "x": "1", "split": "train"},
    {"entity": "C1", "x": "2", "split": "test"},
    {"entity": "C1", "x": "3", "split": "test"},
    {"entity": "C2", "x": "4", "split": "train"},
    {"entity": "C2", "x": "5", "split": "test"},
    {"entity": "C3", "x": "6", "split": "train"},
    {"entity": "C4", "x": "7", "split": "test"},
]

ROLES = make_roles(features=["x"], entity="entity", split="split")


def test_overlap_counts_shared_entities_and_affected_rows():
    result = run_audit_for(make_dataset(ROWS), ROLES)
    findings = findings_for(result, RULE)
    assert len(findings) == 1
    finding = findings[0]

    shared = count_for(finding, "Entity values present in both splits")
    assert (shared.affected, shared.denominator) == (2, 3)  # C1, C2 of {C1, C2, C4}

    test_rows = count_for(finding, "Test rows belonging to an entity also present in train")
    assert (test_rows.affected, test_rows.denominator) == (3, 4)

    # Train rows are C1 (row 1), C2 (row 4) and C3 (row 6). C3 is not shared, so
    # only 2 of the 3 train rows are implicated.
    train_rows = count_for(finding, "Train rows belonging to an entity also present in test")
    assert (train_rows.affected, train_rows.denominator) == (2, 3)

    assert metric_for(result, RULE, "shared_groups") == 2


def test_severity_is_high_when_at_least_ten_percent_of_test_rows_are_affected():
    # 3 of 4 test rows = 75%, above the 10% threshold.
    result = run_audit_for(make_dataset(ROWS), ROLES)
    assert findings_for(result, RULE)[0].severity == "high"


def test_severity_is_medium_for_a_small_share_of_test_rows():
    rows = [
        {"entity": "C1", "x": "1", "split": "train"},
        {"entity": "C1", "x": "2", "split": "test"},
    ]
    rows += [{"entity": f"U{index}", "x": str(index), "split": "test"} for index in range(38)]
    rows += [{"entity": f"T{index}", "x": str(index), "split": "train"} for index in range(9)]
    result = run_audit_for(make_dataset(rows), ROLES)
    finding = findings_for(result, RULE)[0]
    assert finding.severity == "medium"
    assert count_for(finding, "Test rows belonging to an entity").affected == 1


def test_no_finding_when_no_entity_straddles_the_boundary():
    rows = [
        {"entity": "A", "x": "1", "split": "train"},
        {"entity": "B", "x": "2", "split": "train"},
        {"entity": "C", "x": "3", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES)
    assert findings_for(result, RULE) == []
    assert metric_for(result, RULE, "shared_groups") == 0


def test_missing_entity_identifiers_are_counted_separately_and_never_merged():
    rows = [
        {"entity": "", "x": "1", "split": "train"},
        {"entity": "", "x": "2", "split": "train"},
        {"entity": "", "x": "3", "split": "test"},
        {"entity": "", "x": "4", "split": "test"},
        {"entity": "A", "x": "5", "split": "train"},
        {"entity": "B", "x": "6", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES)

    assert findings_for(result, RULE) == []
    assert metric_for(result, RULE, "shared_groups") == 0
    assert metric_for(result, RULE, "unlabelled_entity_rows_train") == 2
    assert metric_for(result, RULE, "unlabelled_entity_rows_test") == 2


def test_missing_entity_rows_are_reported_as_a_warning_during_validation():
    from app.audit.roles import validate_roles

    rows = [
        {
            "entity": f"E{index}" if index < 4 else "",
            "x": str(index),
            "split": "train" if index % 2 else "test",
        }
        for index in range(6)
    ]
    dataset = make_dataset(rows)
    validation = validate_roles(dataset, make_roles(features=["x"], entity="entity", split="split"))
    assert validation.ok is True
    assert any(issue.code == "missing_entity_values" for issue in validation.issues)


def test_an_entity_column_with_no_real_values_is_an_error():
    from app.audit.roles import validate_roles

    rows = [{"entity": "", "x": str(index), "split": "train" if index % 2 else "test"} for index in range(6)]
    validation = validate_roles(
        make_dataset(rows), make_roles(features=["x"], entity="entity", split="split")
    )
    assert validation.ok is False
    assert any(issue.code == "degenerate_groups" for issue in validation.issues)


def test_entity_role_not_selected_reports_not_evaluated():
    result = run_audit_for(make_dataset(ROWS), make_roles(features=["x"], split="split"))
    check = next(item for item in result.evaluation.not_evaluated if item.rule_id == RULE)
    assert check.status == "not_evaluated"
    assert "entity" in check.reason.lower()


def test_whitespace_only_entity_values_count_as_missing():
    rows = [
        {"entity": "  ", "x": "1", "split": "train"},
        {"entity": "  ", "x": "2", "split": "test"},
        {"entity": "A", "x": "3", "split": "train"},
        {"entity": "B", "x": "4", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES, AuditConfig(strip_whitespace=True))
    assert metric_for(result, RULE, "shared_groups") == 0
    assert metric_for(result, RULE, "unlabelled_entity_rows_test") == 1


def test_examples_name_the_shared_entity_and_its_rows():
    result = run_audit_for(make_dataset(ROWS), ROLES)
    finding = findings_for(result, RULE)[0]
    labels = [example.label for example in finding.examples]
    assert any("C1" in label for label in labels)
    assert any("C2" in label for label in labels)
