"""F06 — category-based leakage risk scorecard.

A real overview derived from one audit's rule outcomes. There is deliberately
no numeric score: each category is either carrying findings, clean under the
checks that ran, not applicable, or not checked. Absence of findings is never
presented as proof of safety — that sentence is on the scorecard itself.

Category status derivation (documented, deterministic):

* ``finding_present`` — any rule in the category reported a finding.
* ``error`` — no findings, but a rule raised.
* ``evaluated_no_finding`` — at least one rule ran to completion and none
  reported findings (remaining not-checked rules are visible per rule).
* ``not_applicable`` — every rule in the category was disabled by the user.
* ``not_checked`` — nothing ran: rules were skipped for missing inputs,
  unsupported data, or unavailable metadata.

``affected_rows`` is a best-effort display figure: the largest rows-unit count
of each finding, summed. Exact counts and denominators stay in the linked
findings, which the UI links to.
"""

from __future__ import annotations

from app.audit.types import (
    AuditResult,
    Finding,
    RuleOutcome,
    ScorecardCategory,
    ScorecardRule,
    RiskScorecard,
    Severity,
)

SCORECARD_NOTE = (
    "Derived only from this audit's outcomes. A category marked 'evaluated, no "
    "finding' is clean under the checks that ran — not proven safe. 'Not "
    "checked' means the checks could not run; read the reasons, not a green "
    "tick. There is deliberately no combined score."
)

CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("duplicates", "Duplicate / Similarity", ("SS-DUP-001", "SS-NEAR-001")),
    ("entity", "Entity", ("SS-ENT-001", "SS-ENT-002")),
    ("time", "Time", ("SS-CHR-001", "SS-CHR-002")),
    ("target", "Target", ("SS-TGT-001", "SS-TGT-002")),
    ("pipeline", "Pipeline", ("SS-PPF-001",)),
    ("reuse", "Validation Reuse", ("SS-VRU-001",)),
    ("availability", "Availability", ("SS-AVL-001",)),
)

_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2, "info": 3}


def _worst(severities: list[Severity]) -> Severity | None:
    if not severities:
        return None
    return min(severities, key=lambda severity: _SEVERITY_ORDER[severity])


def _affected_rows(findings: list[Finding]) -> int | None:
    total = 0
    seen = False
    for finding in findings:
        rows_counts = [count.affected for count in finding.counts if count.unit == "rows"]
        if rows_counts:
            seen = True
            total += max(rows_counts)
    return total if seen else None


def build_risk_scorecard(result: AuditResult) -> RiskScorecard:
    outcome_by_rule: dict[str, RuleOutcome] = {
        outcome.rule_id: outcome for outcome in result.rule_outcomes
    }
    findings_by_rule: dict[str, list[Finding]] = {}
    for finding in result.findings:
        findings_by_rule.setdefault(finding.rule_id, []).append(finding)

    categories: list[ScorecardCategory] = []
    for key, label, rule_ids in CATEGORIES:
        rules: list[ScorecardRule] = []
        category_findings: list[Finding] = []
        statuses: list[str] = []
        severities: list[Severity] = []
        for rule_id in rule_ids:
            outcome = outcome_by_rule.get(rule_id)
            if outcome is None:
                # The rule never registered (older schema or an engine that did
                # not run it): treat as not checked rather than inventing state.
                rules.append(
                    ScorecardRule(
                        rule_id=rule_id,
                        title=rule_id,
                        status="not_evaluated",
                        not_evaluated_reason="This check did not run in this audit.",
                    )
                )
                statuses.append("not_evaluated")
                continue
            rule_findings = findings_by_rule.get(rule_id, [])
            category_findings.extend(rule_findings)
            rule_severities = [finding.severity for finding in rule_findings]
            severities.extend(rule_severities)
            rules.append(
                ScorecardRule(
                    rule_id=rule_id,
                    title=outcome.title,
                    status=outcome.status,
                    finding_count=len(rule_findings),
                    max_severity=_worst(rule_severities),
                    not_evaluated_reason=(
                        outcome.not_evaluated.reason if outcome.not_evaluated else None
                    ),
                )
            )
            statuses.append(outcome.status)

        if category_findings:
            status = "finding_present"
        elif "error" in statuses:
            status = "error"
        elif "evaluated" in statuses:
            status = "evaluated_no_finding"
        elif statuses and all(status == "disabled" for status in statuses):
            status = "not_applicable"
        else:
            status = "not_checked"

        categories.append(
            ScorecardCategory(
                key=key,
                label=label,
                status=status,
                finding_count=len(category_findings),
                max_severity=_worst(severities),
                affected_rows=_affected_rows(category_findings),
                rules=rules,
            )
        )

    return RiskScorecard(categories=categories, note=SCORECARD_NOTE)


__all__ = ["CATEGORIES", "SCORECARD_NOTE", "build_risk_scorecard"]
