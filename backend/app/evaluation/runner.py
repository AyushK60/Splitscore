"""The synthetic evaluation runner.

Executes each :class:`~app.evaluation.cases.EvalCase` through the **public**
audit interfaces — :func:`app.audit.service.audit_existing_split` for cases
that audit the split column present in the fixture, and the strategy +
:func:`app.audit.engine.run_audit` composition (the same one
:mod:`app.splits.comparison` uses) for cases that evaluate a generated
candidate split. No rule is invoked directly and no production detection code
is duplicated; the runner only reads the resulting
:class:`~app.audit.types.AuditResult` and compares it against the case's
hand-written or oracle-derived expectations.

For every finding the runner also verifies that the evidence resolves: every
cited row id must exist in the fixture, truncated findings must declare it via
``examples_truncated`` with a larger ``example_total``, untruncated findings
must display every example, and (for the near-duplicate demo) every planted
pair from the manifest must appear among the candidate pairs.

Exit-status contract used by the CLI and the tests:

* ``0`` — every case passed;
* ``1`` — at least one case failed an expectation (a real mismatch);
* ``2`` — a case could not be evaluated at all (invalid fixture, missing
  dataset file, unexpected runtime error). This is deliberately distinct from
  a failing expectation so automation can tell "the engine disagrees" from
  "the harness broke".
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from app.audit.canonical import ValueCanonicalizer
from app.audit.dataset import Dataset
from app.audit.engine import run_audit
from app.audit.io import read_csv_bytes
from app.audit.service import audit_existing_split, resolve_or_raise
from app.audit.types import AuditConfig, AuditResult, Finding, SplitConfig
from app.core.config import Settings
from app.core.errors import SplitScopeError
from app.evaluation.cases import (
    RULE_UNITS,
    CaseResult,
    CheckExpectation,
    CheckResult,
    EvalCase,
    build_cases,
)
from app.splits.strategies import generate_split, summarise

# --------------------------------------------------------------------------- #
# Dataset construction (hand-built fixtures go through the real CSV loader)
# --------------------------------------------------------------------------- #


def rows_to_csv(rows: list[dict[str, str]]) -> bytes:
    """Serialise rows to CSV text, exactly as a user file would look."""
    fieldnames = list(rows[0].keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return buffer.getvalue().encode("utf-8")


def build_dataset(rows: list[dict[str, str]], *, name: str) -> Dataset:
    """Build a Dataset from fixture rows through the production CSV loader."""
    payload = rows_to_csv(rows)
    loaded = read_csv_bytes(
        payload,
        max_bytes=10 * 1024 * 1024,
        max_rows=100_000,
        max_columns=1_000,
        min_rows=1,
        min_columns=1,
        filename=name,
    )
    return Dataset(
        dataset_id="ds-eval",
        name=name,
        source="upload",
        is_synthetic=True,
        fingerprint_sha256=loaded.fingerprint_sha256,
        frame=loaded.frame,
        row_ids=loaded.row_ids,
        columns=loaded.columns,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        encoding=loaded.encoding,
        size_bytes=len(payload),
        warnings=list(loaded.warnings),
        demo=None,
    )


# --------------------------------------------------------------------------- #
# Result readers
# --------------------------------------------------------------------------- #


def _metric_map(result: AuditResult, rule_id: str) -> dict[str, Any]:
    for outcome in result.rule_outcomes:
        if outcome.rule_id == rule_id:
            return {metric.key: metric.value for metric in outcome.metrics}
    return {}


def _outcome(result: AuditResult, rule_id: str):
    for outcome in result.rule_outcomes:
        if outcome.rule_id == rule_id:
            return outcome
    return None


def _findings(result: AuditResult, rule_id: str) -> list[Finding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def _count_value(finding: Finding, label_fragment: str) -> tuple[int, int] | None:
    for count in finding.counts:
        if label_fragment.lower() in count.label.lower():
            return (count.affected, count.denominator)
    return None


# --------------------------------------------------------------------------- #
# Expectation comparison
# --------------------------------------------------------------------------- #


def _compare_check(
    result: AuditResult,
    expectation: CheckExpectation,
    fixture_row_ids: set[str],
    case: EvalCase,
) -> CheckResult:
    problems: list[str] = []
    outcome = _outcome(result, expectation.rule_id)
    findings = _findings(result, expectation.rule_id)

    actual_status = outcome.status if outcome is not None else "(rule missing from result)"
    if actual_status != expectation.status:
        problems.append(f"status: expected {expectation.status!r}, got {actual_status!r}")

    if len(findings) != expectation.finding_count:
        problems.append(f"finding count: expected {expectation.finding_count}, got {len(findings)}")

    if expectation.severity is not None and findings:
        actual_severities = {finding.severity for finding in findings}
        if actual_severities != {expectation.severity}:
            problems.append(
                f"severity: expected {expectation.severity!r}, got {sorted(actual_severities)}"
            )

    metrics = _metric_map(result, expectation.rule_id)
    for key, expected_value in expectation.metrics.items():
        actual_value = metrics.get(key, "(missing)")
        if key == "constant_columns_excluded" and expected_value not in str(actual_value):
            problems.append(
                f"metric {key!r}: expected to contain {expected_value!r}, got {actual_value!r}"
            )
        elif actual_value != expected_value:
            problems.append(f"metric {key!r}: expected {expected_value!r}, got {actual_value!r}")

    if findings:
        primary = findings[0]
        for fragment, expected_pair in expectation.counts.items():
            actual_pair = _count_value(primary, fragment)
            if actual_pair is None:
                problems.append(f"count containing {fragment!r} not found in the finding")
            elif actual_pair != expected_pair:
                problems.append(f"count {fragment!r}: expected {expected_pair}, got {actual_pair}")

    if expectation.reason_contains is not None and outcome is not None:
        reason = outcome.not_evaluated.reason if outcome.not_evaluated else ""
        if expectation.reason_contains.lower() not in reason.lower():
            problems.append(
                f"reason: expected to contain {expectation.reason_contains!r}, got {reason!r}"
            )

    # -- evidence verification -------------------------------------------- #
    for finding in findings:
        for example in finding.examples:
            for row_id in example.row_ids:
                if row_id not in fixture_row_ids:
                    problems.append(f"evidence row id {row_id!r} does not resolve to a fixture record")
        if finding.examples_truncated:
            if finding.example_total <= len(finding.examples):
                problems.append(
                    "examples_truncated is true but example_total does not exceed the "
                    "displayed examples"
                )
        elif finding.example_total != len(finding.examples):
            problems.append(
                f"example_total {finding.example_total} != displayed examples "
                f"{len(finding.examples)} while untruncated"
            )

    cited = {
        row_id
        for finding in findings
        for example in finding.examples
        for row_id in example.row_ids
    }
    for row_id in case.evidence_row_ids.get(expectation.rule_id, []):
        if row_id not in cited:
            problems.append(f"expected evidence row {row_id!r} is not cited by any example")

    expected_distances = case.example_distances.get(expectation.rule_id, [])
    if expected_distances:
        shown = {
            example.details.get("distance")
            for finding in findings
            for example in finding.examples
        }
        for distance in expected_distances:
            if distance not in shown:
                problems.append(
                    f"expected candidate distance {distance!r} not among the examples "
                    f"(shown: {sorted(d for d in shown if d)})"
                )

    for train_row, test_row in case.planted_pair_row_ids.get(expectation.rule_id, []):
        pairs = {
            frozenset(example.row_ids)
            for finding in findings
            for example in finding.examples
            if len(example.row_ids) == 2
        }
        if frozenset({train_row, test_row}) not in pairs:
            problems.append(
                f"planted near-duplicate pair ({train_row}, {test_row}) is not among "
                "the candidate pairs"
            )

    return CheckResult(
        rule_id=expectation.rule_id,
        passed=not problems,
        expected={
            "status": expectation.status,
            "finding_count": expectation.finding_count,
            "severity": expectation.severity,
            "counts": {fragment: list(pair) for fragment, pair in expectation.counts.items()},
            "metrics": dict(expectation.metrics),
            "reason_contains": expectation.reason_contains,
            "evaluation_unit": RULE_UNITS.get(expectation.rule_id),
        },
        actual={
            "status": actual_status,
            "finding_count": len(findings),
            "severities": sorted({finding.severity for finding in findings}),
            "metrics": {key: metrics.get(key) for key in expectation.metrics},
            "counts": [
                {
                    "label": count.label,
                    "affected": count.affected,
                    "denominator": count.denominator,
                    "unit": count.unit,
                }
                for finding in findings
                for count in finding.counts
            ],
        },
        problems=problems,
    )


# --------------------------------------------------------------------------- #
# Case execution and split-fact verification
# --------------------------------------------------------------------------- #

#: Facts that must hold for every generated assignment, whether or not the
#: case pins a specific expected value. A violation fails the case.
UNIVERSAL_SPLIT_FACTS: tuple[str, ...] = (
    "all_rows_assigned_exactly_once",
    "unassigned_rows",
    "input_unchanged",
    "deterministic_regeneration",
    "shared_groups_matches_rule_metric",
    "chronology_matches_rule_metrics",
)


def _build_generated_split(
    case: EvalCase, dataset: Dataset, roles: ColumnRoles, config: AuditConfig
):
    """Generate the assignment through the same public interface the
    comparison uses. Raises the strategy's typed errors unchanged."""
    resolved, _ = resolve_or_raise(dataset, roles)
    canonicalizer = ValueCanonicalizer(
        strip_whitespace=config.strip_whitespace,
        normalize_numeric_strings=config.normalize_numeric_strings,
        missing_tokens=config.missing_tokens,
    )
    strategy: SplitConfig = case.split
    assert strategy is not None  # guarded by the caller
    generated = generate_split(
        dataset,
        resolved_entity=resolved.entity_column,
        resolved_target=resolved.target_column,
        resolved_timestamp=resolved.timestamp_column,
        config=strategy,
        canonicalizer=canonicalizer,
    )
    return resolved, generated


def _compute_split_facts(
    *,
    case: EvalCase,
    dataset: Dataset,
    roles: ColumnRoles,
    config: AuditConfig,
    generated,
    result: AuditResult,
    input_unchanged: bool,
) -> dict[str, Any]:
    """Independently computed facts about one generated assignment.

    Every value here is recomputed from the fixture rows and the generated
    assignment (masks / row-id lists) with plain pandas/numpy set logic --
    never by reading a production rule's output. Where a fact must agree with
    a rule metric (entity overlap, chronology), both are compared explicitly.
    """
    import numpy as np
    import pandas as pd

    masks = generated.masks
    train_ids = masks.row_ids(dataset, "train")
    test_ids = masks.row_ids(dataset, "test")
    all_ids = set(dataset.row_ids)

    facts: dict[str, Any] = {
        "train_rows": masks.train_rows,
        "test_rows": masks.test_rows,
        "unassigned_rows": len(dataset.row_ids) - masks.train_rows - masks.test_rows,
        "all_rows_assigned_exactly_once": (
            len(train_ids) + len(test_ids) == len(dataset.row_ids)
            and set(train_ids).isdisjoint(test_ids)
            and set(train_ids) | set(test_ids) == all_ids
            and len(set(train_ids)) == len(train_ids)
            and len(set(test_ids)) == len(test_ids)
        ),
        "input_unchanged": input_unchanged,
    }

    # Determinism: regenerating with the same configuration must reproduce
    # the assignment (all four strategies are deterministic for their config).
    _resolved, rerun = _build_generated_split(case, dataset, roles, config)
    facts["deterministic_regeneration"] = bool(
        np.array_equal(rerun.masks.train, masks.train)
        and np.array_equal(rerun.masks.test, masks.test)
    )

    # Entity overlap, recomputed by set intersection over the assignment and
    # compared against the SS-ENT-001 metric.
    if roles.entity:
        series = dataset.frame[roles.entity]
        train_positions = np.nonzero(masks.train)[0].tolist()
        test_positions = np.nonzero(masks.test)[0].tolist()
        train_values = {str(value).strip() for value in series.iloc[train_positions]} - {"", "nan"}
        test_values = {str(value).strip() for value in series.iloc[test_positions]} - {"", "nan"}
        facts["shared_groups_independent"] = len(train_values & test_values)
        metric = _metric_map(result, "SS-ENT-001").get("shared_groups")
        facts["shared_groups_matches_rule_metric"] = metric == facts["shared_groups_independent"]

    # Chronological facts, computed from the original fixture timestamps
    # joined to the generated assignment through row positions.
    if roles.timestamp and case.split is not None and case.split.kind == "chronological":
        parsed = pd.to_datetime(dataset.frame[roles.timestamp], errors="coerce", utc=True)
        train_positions = np.nonzero(masks.train)[0].tolist()
        test_positions = np.nonzero(masks.test)[0].tolist()
        train_times = parsed.iloc[train_positions].dropna()
        test_times = parsed.iloc[test_positions].dropna()
        test_min = test_times.min()
        affected = int((train_times > test_min).sum())
        facts["ordered"] = bool(train_times.max() < test_min)
        facts["tie_groups_intact"] = not bool(set(train_times) & set(test_times))
        independent_status = "ordered" if affected == 0 else "violation"
        metrics = _metric_map(result, "SS-CHR-001")
        facts["chronology_status_independent"] = independent_status
        facts["chronology_matches_rule_metrics"] = (
            metrics.get("chronology_status") == independent_status
            and (
                independent_status == "ordered"
                or metrics.get("train_rows_after_earliest_test") == affected
            )
        )

    # Stratified class allocation, counted per side straight from the fixture.
    if roles.target and case.split is not None and case.split.kind == "stratified":
        series = dataset.frame[roles.target]
        train_counts = series[masks.train].value_counts().to_dict()
        test_counts = series[masks.test].value_counts().to_dict()
        facts["train_class_counts"] = {str(key): int(value) for key, value in sorted(train_counts.items())}
        facts["test_class_counts"] = {str(key): int(value) for key, value in sorted(test_counts.items())}

    # Compare against hand-written expectations, and enforce the universal
    # invariants regardless of what the case pins.
    problems: list[str] = []
    for key, expected in case.expected_split_facts.items():
        actual = facts.get(key, "(missing)")
        if actual != expected:
            problems.append(f"split fact {key!r}: expected {expected!r}, got {actual!r}")
    for key in UNIVERSAL_SPLIT_FACTS:
        if key in facts:
            expected = 0 if key == "unassigned_rows" else True
            if facts[key] != expected:
                problems.append(f"split invariant {key!r} violated: got {facts[key]!r}")

    return {"computed": facts, "expected": dict(case.expected_split_facts), "problems": problems}


def _audit_for_case(case: EvalCase, dataset: Dataset, settings: Settings) -> AuditResult:
    """Run the audit for one case through the public interfaces."""
    config = case.config if case.config is not None else AuditConfig()

    if case.split is None:
        return audit_existing_split(dataset, roles=case.roles, config=config, settings=settings)

    resolved, generated = _build_generated_split(case, dataset, case.roles, config)
    summary = summarise(
        strategy_id=case.split.kind,
        label=case.split.label,
        kind=case.split.kind,
        generated=generated,
    )
    return run_audit(
        dataset=dataset,
        roles=case.roles,
        resolved=resolved,
        config=config,
        masks=generated.masks,
        split_summary=summary,
        settings=settings,
    )


def run_case(case: EvalCase, settings: Settings) -> CaseResult:
    """Execute one case and compare every expectation against the actual result."""
    from app.synthetic.manifest import get_demo, recommended_roles

    try:
        if case.demo_id is not None:
            dataset = get_demo(case.demo_id).load(settings=settings)
            roles = case.roles if case.roles is not None else recommended_roles(case.demo_id)
            seed: int | None = dataset.demo.seed if dataset.demo else None
        elif case.rows is not None:
            dataset = build_dataset(case.rows, name=f"{case.case_id}.csv")
            roles = case.roles
            seed = None
        else:
            return CaseResult(
                case_id=case.case_id,
                description=case.description,
                passed=False,
                status="ERROR",
                error="The case defines neither rows nor a demo_id; it cannot be built.",
            )
        if roles is None:
            return CaseResult(
                case_id=case.case_id,
                description=case.description,
                passed=False,
                status="ERROR",
                error="The case defines no column roles.",
            )

        # Rebind the (possibly demo-derived) roles onto the case for the audit.
        case.roles = roles
        frame_before = dataset.frame.copy(deep=True)
        result = _audit_for_case(case, dataset, settings)

        split_facts: dict[str, Any] | None = None
        if case.split is not None:
            config = case.config if case.config is not None else AuditConfig()
            _resolved, generated = _build_generated_split(case, dataset, roles, config)
            split_facts = _compute_split_facts(
                case=case,
                dataset=dataset,
                roles=roles,
                config=config,
                generated=generated,
                result=result,
                input_unchanged=dataset.frame.equals(frame_before),
            )
    except SplitScopeError as exc:
        return CaseResult(
            case_id=case.case_id,
            description=case.description,
            passed=False,
            status="ERROR",
            error=f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 - reported as a harness-level error
        return CaseResult(
            case_id=case.case_id,
            description=case.description,
            passed=False,
            status="ERROR",
            error=f"unexpected {type(exc).__name__}: {exc}",
        )

    fixture_row_ids = set(dataset.row_ids)
    checks = [
        _compare_check(result, expectation, fixture_row_ids, case)
        for expectation in case.expectations
    ]
    passed = all(check.passed for check in checks) and not (
        split_facts["problems"] if split_facts else []
    )
    return CaseResult(
        case_id=case.case_id,
        description=case.description,
        passed=passed,
        status="PASS" if passed else "FAIL",
        checks=checks,
        seed=seed,
        roles={
            "features": list(roles.features),
            "target": roles.target,
            "entity": roles.entity,
            "timestamp": roles.timestamp,
            "split": roles.split,
            "split_train_value": roles.split_train_value,
            "split_test_value": roles.split_test_value,
            "metadata_excluded": list(roles.metadata_excluded),
        },
        split=(
            {
                "kind": case.split.kind,
                "test_fraction": case.split.test_fraction,
                "seed": case.split.seed,
            }
            if case.split is not None
            else {
                "kind": "existing",
                "split_column": roles.split,
                "train_value": roles.split_train_value,
                "test_value": roles.split_test_value,
            }
        ),
        split_facts=split_facts,
    )


# --------------------------------------------------------------------------- #
# Suite execution
# --------------------------------------------------------------------------- #


def run_suite(
    settings: Settings,
    *,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run the suite and return a machine-readable summary.

    The returned dictionary is JSON-serialisable and deliberately free of
    timestamps and runtime identifiers so that two runs over the same fixtures
    can be compared for reproducibility after removing ``generated_at_utc``.
    """
    cases = build_cases(settings)
    if case_ids is not None:
        wanted = set(case_ids)
        unknown = wanted - {case.case_id for case in cases}
        if unknown:
            raise ValueError(f"unknown case id(s): {sorted(unknown)}")
        cases = [case for case in cases if case.case_id in wanted]

    results = [run_case(case, settings) for case in cases]

    failed = [result for result in results if result.status == "FAIL"]
    errored = [result for result in results if result.status == "ERROR"]
    if errored:
        exit_code = 2
    elif failed:
        exit_code = 1
    else:
        exit_code = 0

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "cases": len(results),
            "passed": sum(1 for result in results if result.status == "PASS"),
            "failed": len(failed),
            "errored": len(errored),
            "checks_total": sum(len(result.checks) for result in results),
            "checks_failed": sum(
                1 for result in results for check in result.checks if not check.passed
            ),
            "exit_code": exit_code,
        },
        "results": [result.as_dict() for result in results],
    }


__all__ = ["build_dataset", "rows_to_csv", "run_case", "run_suite"]
