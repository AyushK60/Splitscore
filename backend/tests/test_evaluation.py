"""Focused tests for the evaluation runner itself.

These verify that the harness behaves the way it claims:

* a known-correct case passes;
* a deliberately wrong expectation fails (the harness can actually fail);
* a malformed fixture or unusable input is reported as an ERROR, clearly
  distinguished from a failing expectation;
* evidence expectations are enforced (an uncited evidence row is a failure);
* ``run_suite`` returns the documented exit statuses 0 / 1 / 2.

No test here modifies a correct expectation to match implementation output; the
"wrong expectation" cases are deliberately corrupted copies.
"""

from __future__ import annotations

import pytest

from app.audit.types import ColumnRoles
from app.core.config import Settings, get_settings
from app.evaluation.cases import CheckExpectation, EvalCase, build_cases
from app.evaluation.runner import run_case, run_suite

import app.evaluation.runner as runner_module


def _case(case_id: str) -> EvalCase:
    for case in build_cases(get_settings()):
        if case.case_id == case_id:
            return case
    raise AssertionError(f"case {case_id!r} not found")


def _outcome_status(case: EvalCase) -> str:
    return run_case(case, get_settings()).status


# --------------------------------------------------------------------------- #
# A known-correct case passes
# --------------------------------------------------------------------------- #


def test_known_correct_case_passes() -> None:
    result = run_case(_case("dup_cross_split_multi"), get_settings())
    assert result.status == "PASS", result
    assert result.checks, "expected at least one check to be compared"
    assert all(check.passed for check in result.checks)


def test_demo_case_passes_with_seed_recorded() -> None:
    result = run_case(_case("demo_exact_duplicates"), get_settings())
    assert result.status == "PASS", result
    assert result.seed == 20240202
    assert result.split is not None and result.split["kind"] == "existing"


# --------------------------------------------------------------------------- #
# Deliberately incorrect expectations fail
# --------------------------------------------------------------------------- #


def test_wrong_finding_count_fails() -> None:
    case = _case("dup_cross_split_multi")
    case.expectations = [
        CheckExpectation(rule_id="SS-DUP-001", status="evaluated", finding_count=7)
    ]
    result = run_case(case, get_settings())
    assert result.status == "FAIL"
    problem_text = " ".join(problem for check in result.checks for problem in check.problems)
    assert "finding count" in problem_text


def test_wrong_status_expectation_fails() -> None:
    case = _case("ent_shared_entities")
    case.expectations = [
        CheckExpectation(rule_id="SS-ENT-001", status="not_evaluated", finding_count=0)
    ]
    result = run_case(case, get_settings())
    assert result.status == "FAIL"
    problem_text = " ".join(problem for check in result.checks for problem in check.problems)
    assert "status" in problem_text


def test_wrong_count_expectation_fails() -> None:
    case = _case("ent_shared_entities")
    case.expectations = [
        CheckExpectation(
            rule_id="SS-ENT-001",
            status="evaluated",
            finding_count=1,
            counts={"shared groups": (99, 99)},
        )
    ]
    result = run_case(case, get_settings())
    assert result.status == "FAIL"
    problem_text = " ".join(problem for check in result.checks for problem in check.problems)
    assert "not found" in problem_text or "expected" in problem_text


def test_uncited_evidence_row_fails() -> None:
    """An evidence row id that no example cites must fail the check."""
    case = _case("dup_cross_split_multi")
    case.evidence_row_ids = {"SS-DUP-001": ["row-999999"]}
    result = run_case(case, get_settings())
    assert result.status == "FAIL"
    problem_text = " ".join(problem for check in result.checks for problem in check.problems)
    assert "row-999999" in problem_text


# --------------------------------------------------------------------------- #
# Malformed fixtures / unusable input are ERROR, not FAIL
# --------------------------------------------------------------------------- #


def test_case_without_rows_or_demo_is_error() -> None:
    case = EvalCase(
        case_id="bad_empty",
        description="A case that defines no fixture at all.",
        roles=ColumnRoles(features=["x"], split=None),
    )
    result = run_case(case, get_settings())
    assert result.status == "ERROR"
    assert result.passed is False
    assert "neither rows nor a demo_id" in (result.error or "")


def test_case_without_roles_is_error() -> None:
    case = EvalCase(
        case_id="bad_roles",
        description="Rows but no column roles.",
        rows=[{"x": "1", "split": "train"}, {"x": "2", "split": "test"}],
    )
    result = run_case(case, get_settings())
    assert result.status == "ERROR"
    assert "defines no column roles" in (result.error or "")


def test_unusable_roles_report_validation_failure() -> None:
    """Roles that cannot resolve (split column absent) are reported as ERROR."""
    case = EvalCase(
        case_id="bad_split",
        description="The split column referenced by the roles does not exist.",
        rows=[{"x": "1"}, {"x": "2"}],
        roles=ColumnRoles(
            features=["x"],
            split="split",
            split_train_value="train",
            split_test_value="test",
        ),
    )
    result = run_case(case, get_settings())
    assert result.status == "ERROR"
    assert "ValidationFailure" in (result.error or "")


def test_malformed_rows_reported_as_error() -> None:
    """A fixture that cannot even serialise is an ERROR, not a silent pass."""
    case = EvalCase(
        case_id="bad_rows",
        description="Rows with mismatched columns.",
        rows=[{"x": "1", "split": "train"}, {"y": "2", "split": "anything"}],
        roles=ColumnRoles(
            features=["x"],
            split="split",
            split_train_value="train",
            split_test_value="test",
        ),
    )
    result = run_case(case, get_settings())
    assert result.status == "ERROR"
    assert result.error


# --------------------------------------------------------------------------- #
# run_suite: exit statuses 0 / 1 / 2
# --------------------------------------------------------------------------- #


def _patch_cases(monkeypatch: pytest.MonkeyPatch, cases: list[EvalCase]) -> None:
    monkeypatch.setattr(runner_module, "build_cases", lambda settings: list(cases))


def test_exit_0_when_all_pass(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    _patch_cases(monkeypatch, [_case("dup_cross_split_multi")])
    result = run_suite(settings)
    assert result["summary"]["exit_code"] == 0
    assert result["summary"]["failed"] == 0
    assert result["summary"]["errored"] == 0


def test_exit_1_for_expectation_mismatch(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    bad = _case("dup_cross_split_multi")
    bad.expectations = [
        CheckExpectation(rule_id="SS-DUP-001", status="evaluated", finding_count=99)
    ]
    _patch_cases(monkeypatch, [bad])
    result = run_suite(settings)
    assert result["summary"]["exit_code"] == 1
    assert result["summary"]["failed"] == 1
    assert result["summary"]["errored"] == 0


def test_exit_2_for_unevaluable_case(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    broken = EvalCase(case_id="bad_empty", description="No fixture.", roles=None)
    _patch_cases(monkeypatch, [broken])
    result = run_suite(settings)
    assert result["summary"]["exit_code"] == 2
    assert result["summary"]["errored"] == 1


def test_exit_2_precedes_exit_1(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    bad = _case("dup_cross_split_multi")
    bad.expectations = [
        CheckExpectation(rule_id="SS-DUP-001", status="evaluated", finding_count=99)
    ]
    broken = EvalCase(case_id="bad_empty", description="No fixture.", roles=None)
    _patch_cases(monkeypatch, [bad, broken])
    result = run_suite(settings)
    assert result["summary"]["exit_code"] == 2
    assert result["summary"]["failed"] == 1
    assert result["summary"]["errored"] == 1


# --------------------------------------------------------------------------- #
# Split-fact verification (generated assignments)
# --------------------------------------------------------------------------- #


def test_generated_split_cases_record_facts_and_pass() -> None:
    """A generated-split case records independently computed facts."""
    result = run_case(_case("split_chronological_boundary_tie"), get_settings())
    assert result.status == "PASS", result
    assert result.split_facts is not None
    computed = result.split_facts["computed"]
    assert computed["train_rows"] == 6
    assert computed["test_rows"] == 4
    assert computed["ordered"] is True
    assert computed["tie_groups_intact"] is True
    assert computed["all_rows_assigned_exactly_once"] is True
    assert computed["deterministic_regeneration"] is True
    assert computed["input_unchanged"] is True


def test_wrong_expected_split_fact_fails_the_case() -> None:
    """A deliberately wrong split expectation fails like any other expectation."""
    case = _case("split_random_repeated_entities")
    case.expected_split_facts = {"train_rows": 12, "test_rows": 0}
    result = run_case(case, get_settings())
    assert result.status == "FAIL"
    assert result.split_facts is not None
    problems = " | ".join(result.split_facts["problems"])
    assert "train_rows" in problems and "test_rows" in problems


def test_stratified_case_verifies_class_counts_independently() -> None:
    result = run_case(_case("split_stratified_class_preservation"), get_settings())
    assert result.status == "PASS", result
    assert result.split_facts is not None
    computed = result.split_facts["computed"]
    assert computed["train_class_counts"] == {"A": 3, "B": 2}
    assert computed["test_class_counts"] == {"A": 3, "B": 2}


def test_random_case_cross_checks_entity_overlap_independently() -> None:
    """The independently recounted overlap must equal the SS-ENT-001 metric."""
    result = run_case(_case("split_random_repeated_entities"), get_settings())
    assert result.status == "PASS", result
    assert result.split_facts is not None
    computed = result.split_facts["computed"]
    assert computed["shared_groups_independent"] >= 1  # guaranteed by fixture design
    assert computed["shared_groups_matches_rule_metric"] is True


def test_unknown_case_id_raises(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    _patch_cases(monkeypatch, [_case("dup_cross_split_multi")])
    with pytest.raises(ValueError, match="unknown case id"):
        run_suite(settings, case_ids=["does_not_exist"])


def test_case_filter_runs_only_requested(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    _patch_cases(
        monkeypatch,
        [_case("dup_cross_split_multi"), _case("ent_shared_entities")],
    )
    result = run_suite(settings, case_ids=["dup_cross_split_multi"])
    assert result["summary"]["cases"] == 1
    assert result["results"][0]["case_id"] == "dup_cross_split_multi"


def test_suite_is_deterministic_across_runs(settings: Settings) -> None:
    """Two runs over the same fixtures are identical once the timestamp is dropped."""
    first = run_suite(settings)
    second = run_suite(settings)
    first.pop("generated_at_utc")
    second.pop("generated_at_utc")
    assert first == second