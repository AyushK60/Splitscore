"""integrity capabilities (F04) and the category risk scorecard (F06).

Every check gets positive, negative and ambiguous/unsupported fixtures with
independently hand-written expected results. The five original checks are
covered by their own suites and are asserted here only where integrity must prove it
did not disturb them (rule ids, not-evaluated bookkeeping, catalogue).
"""

from __future__ import annotations

from app.audit.types import AuditConfig, PreprocessingDeclaration, PreprocessingStep

from .conftest import (
    count_for,
    findings_for,
    make_dataset,
    make_roles,
    metric_for,
    outcome_for,
    run_audit_for,
)

ROLES_FEATURES = make_roles(features=["x", "y"], split="split")


# --------------------------------------------------------------------------- #
# SS-AVL-001 - feature availability ledger
# --------------------------------------------------------------------------- #


def _roles_with(features: list[str]) -> AuditConfig:
    return AuditConfig()


AVL_ROLES = make_roles(features=["x", "y"], split="split")


def test_availability_without_declarations_is_not_evaluated_never_passed():
    rows = [
        {"x": "1", "y": "2", "split": "train"},
        {"x": "3", "y": "4", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), AVL_ROLES)
    outcome = outcome_for(result, "SS-AVL-001")
    assert outcome.status == "not_evaluated"
    assert "NOT EVALUATED" in outcome.not_evaluated.reason


def test_future_only_feature_is_a_high_finding():
    rows = [
        {"x": "1", "y": "2", "split": "train"},
        {"x": "3", "y": "4", "split": "test"},
    ]
    config = AuditConfig(feature_availability={"x": "at_prediction", "y": "after_prediction"})
    result = run_audit_for(make_dataset(rows), AVL_ROLES, config)
    finding = findings_for(result, "SS-AVL-001")[0]
    assert finding.severity == "high"
    count = count_for(finding, "Features declared available only after prediction")
    assert (count.affected, count.denominator) == (1, 2)
    assert metric_for(result, "SS-AVL-001", "declared_after_prediction") == 1


def test_before_and_at_prediction_declarations_produce_no_finding():
    rows = [
        {"x": "1", "y": "2", "split": "train"},
        {"x": "3", "y": "4", "split": "test"},
    ]
    config = AuditConfig(feature_availability={"x": "before_prediction", "y": "at_prediction"})
    result = run_audit_for(make_dataset(rows), AVL_ROLES, config)
    assert findings_for(result, "SS-AVL-001") == []
    assert metric_for(result, "SS-AVL-001", "declared_at_prediction") == 1


def test_unknown_declaration_is_info_not_a_clean_result():
    rows = [
        {"x": "1", "y": "2", "split": "train"},
        {"x": "3", "y": "4", "split": "test"},
    ]
    config = AuditConfig(feature_availability={"x": "unknown", "y": "at_prediction"})
    result = run_audit_for(make_dataset(rows), AVL_ROLES, config)
    finding = findings_for(result, "SS-AVL-001")[0]
    assert finding.severity == "info"
    assert count_for(finding, "Features with unknown declared availability").affected == 1


def test_derived_feature_inheriting_a_future_only_input_is_medium():
    rows = [
        {"x": "1", "y": "2", "split": "train"},
        {"x": "3", "y": "4", "split": "test"},
    ]
    config = AuditConfig(
        feature_availability={"x": "at_prediction", "y": "after_prediction"},
        derived_feature_dependencies={"x": ["y"]},
    )
    result = run_audit_for(make_dataset(rows), AVL_ROLES, config)
    severities = sorted(finding.severity for finding in findings_for(result, "SS-AVL-001"))
    assert severities == ["high", "medium"]  # y itself, plus x derived from y


# --------------------------------------------------------------------------- #
# SS-TGT-002 - target proxy candidates
# --------------------------------------------------------------------------- #

PROXY_ROLES = make_roles(features=["signal", "noise"], target="label", split="split")


def test_proxy_screen_without_target_is_not_evaluated():
    rows = [
        {"signal": "1", "noise": "a", "split": "train"},
        {"signal": "2", "noise": "b", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), make_roles(features=["signal"], split="split"))
    assert outcome_for(result, "SS-TGT-002").status == "not_evaluated"


def test_categorical_proxy_value_is_flagged_as_info():
    # 'signal' determines the label almost always over a real share of rows.
    rows = [{"signal": "Z", "noise": "n", "label": "yes", "split": "train"} for _ in range(6)]
    rows += [{"signal": "Z", "noise": "n", "label": "no", "split": "train"}]  # 6/7 purity
    rows += [
        {"signal": "A", "noise": "n", "label": "no", "split": "train"} for _ in range(4)
    ]
    rows += [
        {"signal": "B", "noise": "n", "label": "yes", "split": "test"} for _ in range(4)
    ]
    result = run_audit_for(make_dataset(rows), PROXY_ROLES)
    finding = findings_for(result, "SS-TGT-002")[0]
    assert finding.severity == "info"
    columns = [example.details["column"] for example in finding.examples]
    assert "signal" in columns
    assert "noise" not in columns
    count = count_for(finding, "Proxy candidate columns flagged by the screen")
    assert (count.affected, count.denominator) == (1, 2)


def test_ordinary_categorical_feature_is_not_flagged():
    rows = [
        {"signal": "A", "noise": "n", "label": "yes", "split": "train"},
        {"signal": "A", "noise": "n", "label": "no", "split": "train"},
        {"signal": "B", "noise": "n", "label": "no", "split": "test"},
        {"signal": "B", "noise": "n", "label": "yes", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), PROXY_ROLES)
    assert findings_for(result, "SS-TGT-002") == []


def test_numeric_stump_separating_a_binary_target_is_flagged():
    rows = []
    # x < 10 -> yes (perfect separation on one side).
    rows += [{"signal": str(index), "noise": "n", "label": "yes", "split": "train"} for index in range(8)]
    rows += [{"signal": str(100 + index), "noise": "n", "label": "no", "split": "test"} for index in range(8)]
    result = run_audit_for(make_dataset(rows), PROXY_ROLES)
    finding = findings_for(result, "SS-TGT-002")[0]
    stump = [example for example in finding.examples if "stump" in example.details["method"]]
    assert stump and stump[0].details["column"] == "signal"
    assert "100.0% weighted purity" in stump[0].details["evidence"]


def test_continuous_target_is_unsupported_not_passed():
    rows = [{"signal": "1.5", "noise": "n", "label": str(100 + index), "split": "train"} for index in range(13)]
    rows[0]["split"] = "test"
    result = run_audit_for(make_dataset(rows), PROXY_ROLES)
    outcome = outcome_for(result, "SS-TGT-002")
    assert outcome.status == "unsupported"


def test_ambiguous_borderline_purity_is_not_flagged():
    # 5/7 purity is far below the 0.98 threshold; nothing may fire.
    rows = [{"signal": "Z", "noise": "n", "label": "yes", "split": "train"} for _ in range(5)]
    rows += [{"signal": "Z", "noise": "n", "label": "no", "split": "train"} for _ in range(2)]
    rows += [
        {"signal": "A", "noise": "n", "label": "no", "split": "test"},
        {"signal": "B", "noise": "n", "label": "yes", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), PROXY_ROLES)
    assert findings_for(result, "SS-TGT-002") == []


# --------------------------------------------------------------------------- #
# SS-ENT-002 - identifier-like feature reuse
# --------------------------------------------------------------------------- #

MEM_ROLES = make_roles(features=["badge"], target=None, split="split")


def _membrane_rows(train_badges: list[str], test_badges: list[str]) -> list[dict[str, str]]:
    rows = []
    for index, badge in enumerate(train_badges):
        rows.append({"badge": badge, "x": str(index), "split": "train"})
    for index, badge in enumerate(test_badges):
        rows.append({"badge": badge, "x": str(index), "split": "test"})
    return rows


def test_identifier_like_column_without_overlap_stays_clean_but_is_counted():
    rows = _membrane_rows(
        [f"T-{index}" for index in range(6)], [f"S-{index}" for index in range(6)]
    )
    result = run_audit_for(make_dataset(rows), MEM_ROLES)
    assert findings_for(result, "SS-ENT-002") == []
    assert metric_for(result, "SS-ENT-002", "identifier_like_columns") == 1


def test_shared_identifier_like_values_are_reported_with_real_counts():
    rows = _membrane_rows(["T-1", "T-2", "SHARED", "T-4", "T-5", "T-6"], ["SHARED", "S-2", "S-3", "S-4"])
    result = run_audit_for(make_dataset(rows), MEM_ROLES)
    finding = findings_for(result, "SS-ENT-002")[0]
    assert finding.severity == "medium"
    shared = count_for(finding, "Shared identifier-like values across the split")
    # Denominator is the column's distinct non-missing value count: 6 train
    # badges + 4 test badges with 'SHARED' repeated = 9 distinct values.
    assert (shared.affected, shared.denominator) == (1, 9)
    test_rows = count_for(finding, "Test rows carrying a shared value")
    assert (test_rows.affected, test_rows.denominator) == (1, 4)
    assert finding.examples[0].row_ids  # test rows carrying the shared value


def test_repeating_column_is_not_identifier_like_and_is_not_screened():
    rows = [{"badge": "A", "x": str(index), "split": "train"} for index in range(6)]
    rows += [{"badge": "A", "x": str(index), "split": "test"} for index in range(4)]
    rows += [{"badge": "B", "x": "9", "split": "test"}]
    result = run_audit_for(make_dataset(rows), MEM_ROLES)
    assert findings_for(result, "SS-ENT-002") == []
    assert metric_for(result, "SS-ENT-002", "identifier_like_columns") == 0


def test_identifier_screen_needs_a_minimum_row_count():
    rows = [
        {"badge": "A", "x": "1", "split": "train"},
        {"badge": "B", "x": "2", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), MEM_ROLES)
    assert outcome_for(result, "SS-ENT-002").status == "insufficient_data"


# --------------------------------------------------------------------------- #
# SS-CHR-002 - declared prediction horizon
# --------------------------------------------------------------------------- #

HZ_ROLES = make_roles(features=["x"], timestamp="ts", split="split")


def test_horizon_without_declaration_is_not_evaluated():
    rows = [
        {"ts": "2024-01-01T00:00:00Z", "x": "1", "split": "train"},
        {"ts": "2024-02-01T00:00:00Z", "x": "2", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), HZ_ROLES)
    outcome = outcome_for(result, "SS-CHR-002")
    assert outcome.status == "not_evaluated"
    assert "NOT EVALUATED" in outcome.not_evaluated.reason


def test_gap_covering_the_declared_horizon_is_clean():
    rows = [
        {"ts": "2024-01-01T00:00:00Z", "x": "1", "split": "train"},
        {"ts": "2024-02-01T00:00:00Z", "x": "2", "split": "test"},
    ]
    config = AuditConfig(temporal_horizon_days=7.0)
    result = run_audit_for(make_dataset(rows), HZ_ROLES, config)
    assert findings_for(result, "SS-CHR-002") == []
    assert metric_for(result, "SS-CHR-002", "gap_days") == 31.0


def test_test_rows_inside_the_horizon_are_reported():
    rows = [
        {"ts": "2024-01-10T00:00:00Z", "x": "1", "split": "train"},  # latest train
        {"ts": "2024-01-01T00:00:00Z", "x": "2", "split": "train"},
        {"ts": "2024-01-12T00:00:00Z", "x": "3", "split": "test"},  # inside 7d horizon
        {"ts": "2024-03-01T00:00:00Z", "x": "4", "split": "test"},  # outside
    ]
    config = AuditConfig(temporal_horizon_days=7.0, temporal_horizon_note="weekly decisions")
    result = run_audit_for(make_dataset(rows), HZ_ROLES, config)
    finding = findings_for(result, "SS-CHR-002")[0]
    # 1 of 2 ordered test rows inside the window = 50%, at or above the 10%
    # share that marks a high-severity horizon violation.
    assert finding.severity == "high"
    count = count_for(finding, "Test rows inside the declared horizon window")
    assert (count.affected, count.denominator) == (1, 2)
    assert metric_for(result, "SS-CHR-002", "horizon_note") == "weekly decisions"


def test_nonpositive_horizon_is_unsupported():
    rows = [
        {"ts": "2024-01-01T00:00:00Z", "x": "1", "split": "train"},
        {"ts": "2024-02-01T00:00:00Z", "x": "2", "split": "test"},
    ]
    config = AuditConfig(temporal_horizon_days=0)
    result = run_audit_for(make_dataset(rows), HZ_ROLES, config)
    assert outcome_for(result, "SS-CHR-002").status == "unsupported"


def test_horizon_requires_a_timestamp_role():
    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    config = AuditConfig(temporal_horizon_days=7.0)
    result = run_audit_for(make_dataset(rows), make_roles(features=["x"], split="split"), config)
    assert outcome_for(result, "SS-CHR-002").status == "not_evaluated"


# --------------------------------------------------------------------------- #
# SS-PPF-001 - preprocessing fit boundary
# --------------------------------------------------------------------------- #


def test_preprocessing_without_declaration_is_not_evaluated():
    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES_FEATURES)
    outcome = outcome_for(result, "SS-PPF-001")
    assert outcome.status == "not_evaluated"
    assert "NOT EVALUATED" in outcome.not_evaluated.reason
    assert "raw CSV" in outcome.not_evaluated.reason


def test_full_dataset_fit_declaration_is_a_high_finding():
    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    config = AuditConfig(
        preprocessing=PreprocessingDeclaration(
            steps=[
                PreprocessingStep(name="scaler", kind="scaler", columns=["x"], fit_context="full_dataset"),
                PreprocessingStep(name="imputer", kind="imputer", columns=["x"], fit_context="train_only"),
            ]
        )
    )
    result = run_audit_for(make_dataset(rows), ROLES_FEATURES, config)
    finding = findings_for(result, "SS-PPF-001")[0]
    assert finding.severity == "high"
    count = count_for(finding, "Declared steps not fitted on training data only")
    assert (count.affected, count.denominator) == (1, 2)


def test_train_only_declaration_is_clean_as_declared():
    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    config = AuditConfig(
        preprocessing=PreprocessingDeclaration(
            steps=[PreprocessingStep(name="scaler", kind="scaler", fit_context="train_only")]
        )
    )
    result = run_audit_for(make_dataset(rows), ROLES_FEATURES, config)
    assert findings_for(result, "SS-PPF-001") == []
    assert metric_for(result, "SS-PPF-001", "train_only_steps") == 1


def test_unrecorded_fit_context_is_medium_and_honest():
    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    config = AuditConfig(
        preprocessing=PreprocessingDeclaration(
            steps=[PreprocessingStep(name="encoder", kind="encoder", fit_context="not_recorded")]
        )
    )
    result = run_audit_for(make_dataset(rows), ROLES_FEATURES, config)
    finding = findings_for(result, "SS-PPF-001")[0]
    assert finding.severity == "medium"


# --------------------------------------------------------------------------- #
# SS-VRU-001 - validation reuse
# --------------------------------------------------------------------------- #

from app.audit.types import RunHistoryEntry  # noqa: E402


def test_reuse_without_history_is_not_evaluated():
    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES_FEATURES)
    outcome = outcome_for(result, "SS-VRU-001")
    assert outcome.status == "not_evaluated"
    assert "not evidence that no reuse happened" in outcome.not_evaluated.reason


def _history(count: int, dataset_id: str = "ds-test") -> list[RunHistoryEntry]:
    return [
        RunHistoryEntry(
            run_id=f"run-{index}",
            kind="audit",
            dataset_id=dataset_id,
            split_kind="existing",
            split_column="split",
            train_value="train",
            test_value="test",
            train_rows=1,
            test_rows=1,
            findings_total=0,
        )
        for index in range(count)
    ]


def test_runs_below_the_threshold_are_clean_but_counted():
    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    # Two prior runs of the same existing split -> below threshold (3).
    import app.audit.engine as engine

    from app.audit.service import resolve_or_raise, build_existing_split

    dataset = make_dataset(rows)
    resolved, _ = resolve_or_raise(dataset, ROLES_FEATURES)
    masks, summary = build_existing_split(dataset, resolved)
    from app.core.config import get_settings

    result = engine.run_audit(
        dataset=dataset,
        roles=ROLES_FEATURES,
        resolved=resolved,
        config=AuditConfig(),
        masks=masks,
        split_summary=summary,
        settings=get_settings(),
        run_history=_history(2),
    )
    assert findings_for(result, "SS-VRU-001") == []
    assert metric_for(result, "SS-VRU-001", "prior_runs_same_split") == 2


def test_repeated_runs_of_the_same_split_are_flagged_as_info():
    import app.audit.engine as engine

    from app.audit.service import resolve_or_raise, build_existing_split

    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    dataset = make_dataset(rows)
    resolved, _ = resolve_or_raise(dataset, ROLES_FEATURES)
    masks, summary = build_existing_split(dataset, resolved)
    from app.core.config import get_settings

    result = engine.run_audit(
        dataset=dataset,
        roles=ROLES_FEATURES,
        resolved=resolved,
        config=AuditConfig(),
        masks=masks,
        split_summary=summary,
        settings=get_settings(),
        run_history=_history(4),
    )
    finding = findings_for(result, "SS-VRU-001")[0]
    assert finding.severity == "info"
    count = count_for(finding, "Prior session runs of this exact split")
    assert count.affected == 4


def test_runs_of_other_splits_do_not_accumulate():
    import app.audit.engine as engine

    from app.audit.service import resolve_or_raise, build_existing_split

    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    dataset = make_dataset(rows)
    resolved, _ = resolve_or_raise(dataset, ROLES_FEATURES)
    masks, summary = build_existing_split(dataset, resolved)
    from app.core.config import get_settings

    other = [
        RunHistoryEntry(
            run_id=f"run-{index}",
            kind="audit",
            dataset_id="ds-test",
            split_kind="existing",
            split_column="split",
            train_value="tr",
            test_value="te",  # different labels -> different split
            train_rows=1,
            test_rows=1,
        )
        for index in range(5)
    ]
    result = engine.run_audit(
        dataset=dataset,
        roles=ROLES_FEATURES,
        resolved=resolved,
        config=AuditConfig(),
        masks=masks,
        split_summary=summary,
        settings=get_settings(),
        run_history=other,
    )
    assert findings_for(result, "SS-VRU-001") == []


# --------------------------------------------------------------------------- #
# F06 - risk scorecard
# --------------------------------------------------------------------------- #


def test_scorecard_reflects_findings_and_not_checked_categories():
    rows = _membrane_rows(["T-1", "T-2", "SHARED", "T-4", "T-5", "T-6"], ["SHARED", "S-2", "S-3", "S-4"])
    result = run_audit_for(make_dataset(rows), MEM_ROLES)
    scorecard = result.risk_scorecard
    assert scorecard is not None
    by_key = {category.key: category for category in scorecard.categories}
    entity = by_key["entity"]
    assert entity.status == "finding_present"
    assert entity.max_severity == "medium"
    assert entity.affected_rows == 1  # the test row carrying the shared value
    # The shared badge value is itself an exact cross-split feature duplicate,
    # so the duplicates category carries the SS-DUP-001 finding too.
    assert by_key["duplicates"].status == "finding_present"
    assert by_key["pipeline"].status == "not_checked"
    assert by_key["reuse"].status == "not_checked"


def test_scorecard_marks_declared_clean_categories():
    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    config = AuditConfig(
        preprocessing=PreprocessingDeclaration(
            steps=[PreprocessingStep(name="scaler", kind="scaler", fit_context="train_only")]
        )
    )
    result = run_audit_for(make_dataset(rows), ROLES_FEATURES, config)
    by_key = {category.key: category for category in result.risk_scorecard.categories}
    assert by_key["pipeline"].status == "evaluated_no_finding"


def test_scorecard_note_refuses_a_safety_claim():
    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES_FEATURES)
    assert "not proven safe" in result.risk_scorecard.note


def test_original_five_rule_ids_are_unchanged():
    rows = [
        {"x": "1", "y": "5", "split": "train"},
        {"x": "2", "y": "6", "split": "test"},
    ]
    result = run_audit_for(make_dataset(rows), ROLES_FEATURES)
    original = {"SS-DUP-001", "SS-ENT-001", "SS-CHR-001", "SS-TGT-001", "SS-NEAR-001"}
    assert original <= {outcome.rule_id for outcome in result.rule_outcomes}


def test_continuous_measurement_columns_are_not_screened():
    # A float measurement column is all-distinct and shares one value by
    # coincidence - it is not an identifier and must not be flagged.
    rows = []
    for index in range(6):
        rows.append({"badge": f"T-{index}", "measure": f"{index + 0.5}", "split": "train"})
    rows.append({"badge": "T-COINCIDE", "measure": "1.5", "split": "test"})
    rows[0]["measure"] = "1.5"  # duplicate value across the split
    for index in range(3):
        rows.append({"badge": f"S-{index}", "measure": f"{100 + index + 0.25}", "split": "test"})
    result = run_audit_for(make_dataset(rows), make_roles(features=["badge", "measure"], split="split"))
    assert findings_for(result, "SS-ENT-002") == []
    assert metric_for(result, "SS-ENT-002", "identifier_like_columns") == 1  # badge only
