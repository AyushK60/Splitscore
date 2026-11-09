"""Rule protocol, shared context and helpers.

Every leakage check is an independent :class:`Rule`. A rule receives a
:class:`RuleContext` (dataset, split masks, resolved roles, audit config) and
returns a :class:`RuleOutput` that is either a set of findings, or an explicit
"this did not run" record with a reason.

Rules never raise for expected conditions: they return a status. The engine
still wraps each rule in a guard so that an unexpected exception in one rule
cannot take down the whole audit - it is reported as a rule of status
``error``, which is visibly different from "clean".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from app.audit.canonical import ValueCanonicalizer
from app.audit.dataset import Dataset, SplitMasks
from app.audit.types import (
    AuditConfig,
    EvidenceExample,
    Finding,
    NotEvaluatedCheck,
    ResolvedRoles,
    RuleMetric,
    RunHistoryEntry,
    Severity,
    SplitSummary,
)
from app.core.config import Settings
from app.core.hashing import signature_hash


@dataclass
class RuleContext:
    """Everything a rule is allowed to see."""

    dataset: Dataset
    masks: SplitMasks
    resolved: ResolvedRoles
    config: AuditConfig
    settings: Settings
    canonicalizer: ValueCanonicalizer
    # What was actually audited: the summary of the split this run uses. Needed
    # by rules that reason about the run itself rather than the data.
    split_summary: SplitSummary | None = None
    # Prior audit runs in this session, when the caller can supply them. None
    # means "no history available" (the validation-reuse check reports NOT
    # EVALUATED); an empty list is a real observation of no prior runs.
    run_history: list[RunHistoryEntry] | None = None

    @property
    def train_frame(self) -> pd.DataFrame:
        return self.dataset.frame.loc[self.masks.train]

    @property
    def test_frame(self) -> pd.DataFrame:
        return self.dataset.frame.loc[self.masks.test]

    def train_values(self, column: str) -> list[str]:
        return self.dataset.frame[column].to_numpy()[self.masks.train].tolist()

    def test_values(self, column: str) -> list[str]:
        return self.dataset.frame[column].to_numpy()[self.masks.test].tolist()

    def row_id(self, position: int) -> str:
        return self.dataset.row_ids[position]

    def train_positions(self) -> list[int]:
        return [i for i, keep in enumerate(self.masks.train.tolist()) if keep]

    def test_positions(self) -> list[int]:
        return [i for i, keep in enumerate(self.masks.test.tolist()) if keep]


@dataclass
class RuleOutput:
    """What a rule returns."""

    status: str = "evaluated"
    findings: list[Finding] = field(default_factory=list)
    metrics: list[RuleMetric] = field(default_factory=list)
    not_evaluated: NotEvaluatedCheck | None = None

    @classmethod
    def not_run(cls, rule_id: str, title: str, status: str, reason: str, **details: str) -> RuleOutput:
        return cls(
            status=status,
            not_evaluated=NotEvaluatedCheck(
                rule_id=rule_id, title=title, status=status, reason=reason, details=details
            ),
        )


class Rule(Protocol):
    """Interface implemented by every leakage check."""

    rule_id: str
    title: str

    def run(self, ctx: RuleContext) -> RuleOutput:  # pragma: no cover - protocol
        ...


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def bound_examples(
    examples: Sequence[EvidenceExample], ctx: RuleContext
) -> tuple[list[EvidenceExample], int, bool]:
    """Cap the number of examples carried into a finding.

    Returns ``(kept, total_available, truncated)``. Bounding happens here so no
    rule can accidentally emit thousands of rows into a report.
    """
    limit = ctx.config.max_examples
    total = len(examples)
    kept = list(examples[:limit])
    return kept, total, total > limit


def cap_values(values: Sequence[str], ctx: RuleContext) -> list[str]:
    return list(values[: ctx.config.max_example_rows_per_example])


def format_value(value: str, *, limit: int = 60) -> str:
    """Render a cell for display, escaping nothing (reports escape on output)."""
    if value == "":
        return "(empty)"
    if len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def feature_value_details(
    frame: pd.DataFrame, feature_columns: Sequence[str], position: int, *, limit: int = 6
) -> dict[str, str]:
    """Feature values for one row, bounded to keep evidence readable."""
    details: dict[str, str] = {}
    for column in feature_columns[:limit]:
        details[column] = format_value(str(frame[column].iloc[position]))
    if len(feature_columns) > limit:
        details["…"] = f"{len(feature_columns) - limit} further feature column(s) not shown"
    return details


def grouped_by_signature(
    signatures: Sequence[tuple[str, ...]],
) -> tuple[dict[tuple[str, ...], list[int]], int]:
    """Group row positions by their canonical feature signature.

    Two-stage, collision-safe grouping:

    1. bucket positions by a short SHA-256 prefix of the injective encoding, then
    2. confirm equality by comparing the *full* canonical tuple inside each
       bucket.

    Step 2 is what makes the result correct rather than merely likely: a hash
    bucket that contains more than one distinct tuple is split, and the count of
    such splits is returned so the audit can show that collisions were checked
    for (the expected value is 0).
    """
    buckets: dict[str, list[int]] = {}
    for position, signature in enumerate(signatures):
        buckets.setdefault(signature_hash(signature), []).append(position)

    groups: dict[tuple[str, ...], list[int]] = {}
    mismatches = 0
    for positions in buckets.values():
        if len(positions) == 1:
            signature = signatures[positions[0]]
            groups.setdefault(signature, []).append(positions[0])
            continue
        local: dict[tuple[str, ...], list[int]] = {}
        for position in positions:
            local.setdefault(signatures[position], []).append(position)
        if len(local) > 1:
            mismatches += 1
        for signature, members in local.items():
            groups.setdefault(signature, []).extend(members)
    return groups, mismatches


def severity_ordered(severity: Severity) -> int:
    return {"high": 0, "medium": 1, "low": 2, "info": 3}[severity]


__all__ = [
    "Rule",
    "RuleContext",
    "RuleOutput",
    "bound_examples",
    "cap_values",
    "feature_value_details",
    "format_value",
    "grouped_by_signature",
    "severity_ordered",
]
