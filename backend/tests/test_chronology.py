"""SS-CHR-001: chronological split violation."""

from __future__ import annotations

from app.audit.types import AuditConfig

from .conftest import count_for, findings_for, make_dataset, make_roles, metric_for, run_audit_for

RULE = "SS-CHR-001"
ROLES = make_roles(features=["x"], timestamp="ts", split="split")


def test_ordered_split_produces_no_finding_and_reports_ordered():
    rows = [
        {"ts": "2024-01-01T00:00:00Z", "x": "1", "split": "train"},
        {"ts": "2024-01-02T00:00:00Z", "x": "2", "split": "train"},
        {"ts": "2024-01-03T00:00:00Z", "x": "3", "split": "test"},
        {"ts": "2024-01-04T00:00:00Z", "x": "4", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES)
    assert findings_for(result, RULE) == []
    assert metric_for(result, RULE, "chronology_status") == "ordered"


def test_violation_is_reported_with_counts_and_boundary_dates():
    rows = [
        {"ts": "2024-01-05T00:00:00Z", "x": "1", "split": "train"},  # newer than earliest test
        {"ts": "2024-01-06T00:00:00Z", "x": "2", "split": "train"},
        {"ts": "2024-01-01T00:00:00Z", "x": "3", "split": "test"},  # earliest test
        {"ts": "2024-01-07T00:00:00Z", "x": "4", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES)
    finding = findings_for(result, RULE)[0]

    affected = count_for(finding, "Train rows newer than the earliest test timestamp")
    assert (affected.affected, affected.denominator) == (2, 2)
    assert metric_for(result, RULE, "chronology_status") == "violation"
    assert metric_for(result, RULE, "test_min_timestamp") == "2024-01-01T00:00:00+00:00"
    assert metric_for(result, RULE, "train_max_timestamp") == "2024-01-06T00:00:00+00:00"
    assert finding.severity == "high"  # 100% of train rows, above the 2% threshold


def test_rows_tied_exactly_at_the_boundary_are_not_a_violation():
    rows = [
        {"ts": "2023-12-01T00:00:00Z", "x": "1", "split": "train"},
        {"ts": "2024-01-01T00:00:00Z", "x": "2", "split": "train"},  # ties with earliest test
        {"ts": "2024-01-01T00:00:00Z", "x": "3", "split": "train"},  # ties with earliest test
        {"ts": "2024-01-01T00:00:00Z", "x": "4", "split": "test"},
        {"ts": "2024-01-02T00:00:00Z", "x": "5", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES)

    assert findings_for(result, RULE) == []
    assert metric_for(result, RULE, "boundary_tie_rows") == 2
    assert metric_for(result, RULE, "chronology_status") == "ordered"


def test_affected_share_above_the_threshold_is_high():
    rows = [{"ts": "2024-01-01T00:00:00Z", "x": "0", "split": "train"}]
    rows += [{"ts": "2024-01-02T00:00:00Z", "x": str(index), "split": "train"} for index in range(99)]
    rows += [{"ts": "2024-01-01T12:00:00Z", "x": "test-1", "split": "test"}]
    rows += [{"ts": "2024-01-03T00:00:00Z", "x": "test-2", "split": "test"}]
    result = run_audit_for(make_dataset(rows), ROLES)
    # 99 of 100 train rows are newer than 2024-01-01T12:00 -> 99%, above the 2% threshold.
    assert findings_for(result, RULE)[0].severity == "high"


def test_a_small_share_of_out_of_order_train_rows_is_medium_not_high():
    rows = [{"ts": "2024-06-02T00:00:00Z", "x": "test-2", "split": "test"}]
    rows += [{"ts": "2024-06-01T12:00:00Z", "x": "test-1", "split": "test"}]
    rows += [{"ts": "2024-06-01T13:00:00Z", "x": "late", "split": "train"}]
    rows += [{"ts": "2023-12-31T00:00:00Z", "x": str(index), "split": "train"} for index in range(500)]
    result = run_audit_for(make_dataset(rows), ROLES)
    finding = findings_for(result, RULE)[0]
    # 1 of 501 train rows is newer than the earliest test timestamp -> 0.2%.
    assert finding.severity == "medium"
    assert count_for(finding, "Train rows newer than the earliest test timestamp").affected == 1


def test_unparsable_timestamps_are_counted_and_excluded_from_ordering():
    rows = [
        {"ts": "2024-01-01T00:00:00Z", "x": "1", "split": "train"},
        {"ts": "not-a-date", "x": "2", "split": "train"},
        {"ts": "2024-01-02T00:00:00Z", "x": "3", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES)
    assert metric_for(result, RULE, "unparsable_train_timestamps") == 1
    assert metric_for(result, RULE, "chronology_status") == "ordered"


def test_a_mostly_invalid_timestamp_column_blocks_the_audit():
    """Invalid timestamps are a configuration error, not a silent skip."""
    import pytest

    from app.core.errors import ValidationFailure

    rows = [
        {"ts": "nope", "x": "1", "split": "train"},
        {"ts": "also-nope", "x": "2", "split": "test"},
    ]
    with pytest.raises(ValidationFailure) as error:
        run_audit_for(make_dataset(rows), ROLES)
    codes = {issue["code"] for issue in error.value.details["issues"]}
    assert "invalid_timestamp_values" in codes


def test_rule_reports_insufficient_data_when_no_side_has_a_valid_timestamp():
    """Direct rule check: the engine never sees this case, the rule still handles it."""
    from app.audit.dataset import SplitMasks
    from app.audit.engine import build_canonicalizer
    from app.audit.roles import validate_roles
    from app.audit.rules import chronology
    from app.audit.rules.base import RuleContext
    from app.audit.types import AuditConfig
    from app.core.config import get_settings

    dataset = make_dataset([
        {"ts": "2024-01-01T00:00:00Z", "x": "1", "split": "train"},
        {"ts": "2024-01-02T00:00:00Z", "x": "2", "split": "test"},
    ])
    roles = ROLES
    resolved = validate_roles(dataset, roles).resolved
    assert resolved is not None
    config = AuditConfig(chronology_intent="not_applicable")
    context = RuleContext(
        dataset=dataset,
        masks=SplitMasks(
            train=dataset.frame["split"].eq("train").to_numpy(),
            test=dataset.frame["split"].eq("test").to_numpy(),
        ),
        resolved=resolved,
        config=config,
        settings=get_settings(),
        canonicalizer=build_canonicalizer(config),
    )
    output = chronology.run(context)
    assert output.status == "not_evaluated"
    assert output.not_evaluated is not None
    assert output.not_evaluated.status == "not_evaluated"


def test_chronology_intent_not_applicable_skips_the_check():
    rows = [
        {"ts": "2024-01-05T00:00:00Z", "x": "1", "split": "train"},
        {"ts": "2024-01-06T00:00:00Z", "x": "2", "split": "train"},
        {"ts": "2024-01-01T00:00:00Z", "x": "3", "split": "test"},
        {"ts": "2024-01-02T00:00:00Z", "x": "4", "split": "test"},
    ]
    result = run_audit_for(
        make_dataset(rows), ROLES, AuditConfig(chronology_intent="not_applicable")
    )
    assert findings_for(result, RULE) == []
    check = next(item for item in result.evaluation.not_evaluated if item.rule_id == RULE)
    assert check.status == "not_evaluated"


def test_timestamp_role_not_selected_reports_not_evaluated():
    result = run_audit_for(make_dataset([
        {"ts": "2024-01-01T00:00:00Z", "x": "1", "split": "train"},
        {"ts": "2024-01-01T00:00:00Z", "x": "2", "split": "train"},
        {"ts": "2024-01-02T00:00:00Z", "x": "3", "split": "test"},
        {"ts": "2024-01-03T00:00:00Z", "x": "4", "split": "test"},
    ]), make_roles(features=["x"], split="split"))
    check = next(item for item in result.evaluation.not_evaluated if item.rule_id == RULE)
    assert check.status == "not_evaluated"


def test_naive_timestamps_are_read_as_utc():
    rows = [
        {"ts": "2024-01-05 00:00:00", "x": "1", "split": "train"},
        {"ts": "2024-01-06 00:00:00", "x": "2", "split": "train"},
        {"ts": "2024-01-01 00:00:00", "x": "3", "split": "test"},
        {"ts": "2024-01-02 00:00:00", "x": "4", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES)
    assert metric_for(result, RULE, "chronology_status") == "violation"
    assert metric_for(result, RULE, "test_min_timestamp") == "2024-01-01T00:00:00+00:00"
