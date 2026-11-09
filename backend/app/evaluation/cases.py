"""The synthetic evaluation suite.

Two kinds of cases:

* **Hand-built fixtures** - a handful of rows written out below, with every
  expectation (statuses, counts, severities, evidence row ids) written by hand
  from the documented rule definitions. Nothing here is derived by running a
  detector.
* **Committed demo datasets** - the six bundled CSVs, audited with their
  recommended roles/config. The *complete* expected outcome for each evaluated
  check is computed by the independent oracles in :mod:`app.evaluation.oracles`
  (never by the detectors), because generated data can contain additional
  matches beyond the planted ones. For the near-duplicate demo the planted
  pairs from the manifest are additionally required to appear as evidence.

Cases cover, per check: positives, negatives, boundary conditions, and the
documented "did not run" paths (not evaluated / insufficient data / unsupported
/ disabled), plus a diagnostics case confirming that class imbalance and
distribution shift are reported as diagnostics rather than as leakage findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.audit.types import AuditConfig, ColumnRoles, NearDuplicateSettings, SplitConfig
from app.core.config import Settings
from app.evaluation import oracles

# --------------------------------------------------------------------------- #
# Expectation model
# --------------------------------------------------------------------------- #

#: The evaluation unit asserted for each rule. Statuses and counts are always
#: evaluated per unit below; metrics are rule-specific summaries.
RULE_UNITS: dict[str, str] = {
    "SS-DUP-001": "distinct feature signature shared across the split "
    "(finding unit); affected-counts are rows",
    "SS-ENT-001": "distinct non-missing entity value (finding unit); "
    "affected-counts are rows",
    "SS-CHR-001": "train row newer than the earliest test timestamp "
    "(finding unit: the boundary condition over train rows)",
    "SS-TGT-001": "selected feature column (one finding per matching feature); "
    "counts are comparable rows/values",
    "SS-NEAR-001": "cross-split candidate row pair (one aggregated finding); "
    "counts are pairs and analysed rows",
    "SS-DIAG-000": "dataset diagnostics (no leakage unit)",
}


@dataclass
class CheckExpectation:
    """Expected outcome of one check for one case."""

    rule_id: str
    status: str  # evaluated | not_evaluated | insufficient_data | unsupported | disabled
    finding_count: int = 0
    severity: str | None = None
    #: label fragment (case-insensitive) -> (affected, denominator)
    counts: dict[str, tuple[int, int]] = field(default_factory=dict)
    #: metric key -> expected value
    metrics: dict[str, Any] = field(default_factory=dict)
    reason_contains: str | None = None


@dataclass
class EvalCase:
    """One evaluation case: a fixture, the audit configuration, expectations."""

    case_id: str
    description: str
    #: Hand-built rows (all values as text) when not a demo case.
    rows: list[dict[str, str]] | None = None
    #: Committed demo id when not a hand-built case.
    demo_id: str | None = None
    roles: ColumnRoles | None = None
    config: AuditConfig | None = None
    #: None audits the existing split column; otherwise a generated strategy.
    split: SplitConfig | None = None
    expectations: list[CheckExpectation] = field(default_factory=list)
    #: rule_id -> row ids that must appear in that rule's finding examples.
    evidence_row_ids: dict[str, list[str]] = field(default_factory=dict)
    #: rule_id -> exact `distance` detail values expected among the examples.
    example_distances: dict[str, list[str]] = field(default_factory=dict)
    #: rule_id -> manifest planted-pair row ids that must appear as candidate
    #: evidence (demo near-duplicate cases only).
    planted_pair_row_ids: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    #: For generated-split cases: hand-written expected split facts, checked
    #: against values computed independently from the fixture + assignment
    #: (sizes, temporal ordering, class counts, ...). See runner.split_facts.
    expected_split_facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckResult:
    rule_id: str
    passed: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    problems: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    description: str
    passed: bool
    status: str  # PASS | FAIL | ERROR
    checks: list[CheckResult] = field(default_factory=list)
    error: str | None = None
    seed: int | None = None
    roles: dict[str, Any] | None = None
    split: dict[str, Any] | None = None
    #: For generated-split cases: computed/expected facts and their problems.
    split_facts: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "description": self.description,
            "status": self.status,
            "passed": self.passed,
            "seed": self.seed,
            "roles": self.roles,
            "split": self.split,
            "split_facts": self.split_facts,
            "error": self.error,
            "checks": [
                {
                    "rule_id": check.rule_id,
                    "passed": check.passed,
                    "expected": check.expected,
                    "actual": check.actual,
                    "problems": check.problems,
                }
                for check in self.checks
            ],
        }


def _roles(
    features: list[str],
    *,
    target: str | None = None,
    entity: str | None = None,
    timestamp: str | None = None,
    split: str = "split",
    train_value: str = "train",
    test_value: str = "test",
    metadata_excluded: list[str] | None = None,
) -> ColumnRoles:
    return ColumnRoles(
        features=list(features),
        target=target,
        entity=entity,
        timestamp=timestamp,
        split=split if split else None,
        split_train_value=train_value if split else None,
        split_test_value=test_value if split else None,
        metadata_excluded=list(metadata_excluded or []),
    )


# --------------------------------------------------------------------------- #
# SS-DUP-001 cases
# --------------------------------------------------------------------------- #


def _dup_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []

    # Signature A: 2 train + 3 test rows. Signature B: 1 train + 1 test.
    # Signature C: 1 train only. Signature D: 1 test only.
    # Test rows = 3 (A) + 1 (B) + 1 (D) = 5; affected test rows = 4 -> share
    # 0.8 >= 5% -> high severity (share-based, as documented).
    cross_rows = [
        {"f1": "1", "f2": "a", "label": "0", "split": "train"},  # row-000001 A
        {"f1": "1", "f2": "a", "label": "0", "split": "train"},  # row-000002 A
        {"f1": "9", "f2": "c", "label": "1", "split": "train"},  # row-000003 C
        {"f1": "1", "f2": "a", "label": "1", "split": "test"},  # row-000004 A
        {"f1": "1", "f2": "a", "label": "0", "split": "test"},  # row-000005 A
        {"f1": "1", "f2": "a", "label": "1", "split": "test"},  # row-000006 A
        {"f1": "5", "f2": "b", "label": "0", "split": "test"},  # row-000007 B
        {"f1": "5", "f2": "b", "label": "0", "split": "train"},  # row-000008 B
        {"f1": "7", "f2": "d", "label": "1", "split": "test"},  # row-000009 D
    ]
    cases.append(
        EvalCase(
            case_id="dup_cross_split_multi",
            description=(
                "Cross-split duplicates with multiple records sharing one signature "
                "(2 train + 3 test of signature A), one 1+1 spanning group, and one "
                "single-sided row each side."
            ),
            rows=cross_rows,
            roles=_roles(["f1", "f2"], target="label"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-DUP-001",
                    status="evaluated",
                    finding_count=1,
                    severity="high",
                    counts={
                        "signatures present in both": (2, 3),  # 2 shared of 3 distinct test signatures
                        "Test rows sharing a feature signature with a train row": (4, 5),
                        "Train rows sharing a feature signature with a test row": (3, 4),
                        "exact duplicates of another test row": (3, 5),
                        "exact duplicates of another train row": (2, 4),
                    },
                    metrics={
                        "exact_duplicate_test_rows": 4,
                        "exact_duplicate_shared_signatures": 2,
                        "hash_bucket_collisions_rejected": 0,
                        "distinct_feature_signatures": 4,  # A, B, C, D
                    },
                )
            ],
            evidence_row_ids={
                "SS-DUP-001": [
                    "row-000001",
                    "row-000002",
                    "row-000004",
                    "row-000005",
                    "row-000006",
                    "row-000007",
                    "row-000008",
                ]
            },
        )
    )

    # Duplicates exist only inside one split each: the check runs and finds
    # nothing cross-split, but the within-split metrics still report the rows.
    within_rows = [
        {"f1": "1", "f2": "a", "label": "0", "split": "train"},  # row-000001 E
        {"f1": "1", "f2": "a", "label": "0", "split": "train"},  # row-000002 E
        {"f1": "1", "f2": "a", "label": "1", "split": "train"},  # row-000003 E
        {"f1": "2", "f2": "b", "label": "0", "split": "train"},  # row-000004 unique
        {"f1": "3", "f2": "c", "label": "0", "split": "test"},  # row-000005 F
        {"f1": "3", "f2": "c", "label": "1", "split": "test"},  # row-000006 F
        {"f1": "4", "f2": "d", "label": "0", "split": "test"},  # row-000007 unique
    ]
    cases.append(
        EvalCase(
            case_id="dup_within_split_only",
            description=(
                "Signatures duplicated only within train (3 rows) or within test "
                "(2 rows): evaluated with no finding, within-split metrics non-zero."
            ),
            rows=within_rows,
            roles=_roles(["f1", "f2"], target="label"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-DUP-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={
                        "exact_duplicate_test_rows": 0,
                        "within_train_duplicate_rows": 3,
                        "within_test_duplicate_rows": 2,
                    },
                )
            ],
        )
    )

    # Missing matches missing; the literal string 'NA' is a value, not missing.
    missing_rows = [
        {"f1": "NA", "f2": "x", "label": "0", "split": "train"},  # row-000001 literal pair
        {"f1": "NA", "f2": "x", "label": "1", "split": "test"},  # row-000002 literal pair
        {"f1": "", "f2": "y", "label": "0", "split": "train"},  # row-000003 missing vs literal
        {"f1": "NA", "f2": "y", "label": "0", "split": "test"},  # row-000004 (literal 'NA')
        {"f1": "", "f2": "z", "label": "0", "split": "train"},  # row-000005 missing pair
        {"f1": "", "f2": "z", "label": "1", "split": "test"},  # row-000006 missing pair
    ]
    cases.append(
        EvalCase(
            case_id="dup_missing_vs_literal",
            description=(
                "Empty cells match each other; the literal 'NA' matches the literal "
                "'NA' but never the empty cell."
            ),
            rows=missing_rows,
            roles=_roles(["f1", "f2"], target="label"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-DUP-001",
                    status="evaluated",
                    finding_count=1,
                    severity="high",  # 2 affected of 3 test rows -> 66% share
                    counts={
                        "signatures present in both": (2, 3),
                        "Test rows sharing a feature signature with a train row": (2, 3),
                    },
                )
            ],
        )
    )

    # Same rows, but 'NA' is configured as a missing token: now all three
    # groups collapse into missing-value groups and the literal/missing pair
    # spans the boundary too.
    cases.append(
        EvalCase(
            case_id="dup_missing_tokens_configured",
            description="With missing_tokens=['NA'], 'NA' becomes missing and matches empty cells.",
            rows=missing_rows,
            roles=_roles(["f1", "f2"], target="label"),
            config=AuditConfig(missing_tokens=["NA"]),
            expectations=[
                CheckExpectation(
                    rule_id="SS-DUP-001",
                    status="evaluated",
                    finding_count=1,
                    severity="high",  # 3 affected of 3 test rows
                    counts={
                        "signatures present in both": (3, 3),
                        "Test rows sharing a feature signature with a train row": (3, 3),
                    },
                )
            ],
        )
    )

    # The target column is not compared: rows identical in the selected
    # features are duplicates even when the target differs; rows differing in
    # a selected feature are not.
    excluded_rows = [
        {"f1": "1", "f2": "a", "label": "0", "split": "train"},  # row-000001 X
        {"f1": "1", "f2": "a", "label": "1", "split": "test"},  # row-000002 X (target differs)
        {"f1": "1", "f2": "b", "label": "0", "split": "train"},  # row-000003
        {"f1": "2", "f2": "b", "label": "0", "split": "test"},  # row-000004 (feature differs)
        {"f1": "3", "f2": "c", "label": "1", "split": "test"},  # row-000005 unique
    ]
    cases.append(
        EvalCase(
            case_id="dup_target_not_compared",
            description=(
                "A differing target does not prevent an exact-duplicate finding "
                "(only selected features are compared); a differing selected "
                "feature prevents one."
            ),
            rows=excluded_rows,
            roles=_roles(["f1", "f2"], target="label"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-DUP-001",
                    status="evaluated",
                    finding_count=1,
                    severity="high",  # 1 of 3 test rows -> 33% share
                    counts={
                        "signatures present in both": (1, 3),
                        "Test rows sharing a feature signature with a train row": (1, 3),
                        "Train rows sharing a feature signature with a test row": (1, 2),
                    },
                )
            ],
            evidence_row_ids={"SS-DUP-001": ["row-000001", "row-000002"]},
        )
    )

    return cases


# --------------------------------------------------------------------------- #
# SS-ENT-001 cases
# --------------------------------------------------------------------------- #


def _entity_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []

    shared_rows = [
        {"entity": "E1", "x": "1", "split": "train"},  # row-000001
        {"entity": "E1", "x": "2", "split": "train"},  # row-000002
        {"entity": "E2", "x": "3", "split": "train"},  # row-000003
        {"entity": "E1", "x": "4", "split": "test"},  # row-000004
        {"entity": "E1", "x": "5", "split": "test"},  # row-000005
        {"entity": "E3", "x": "6", "split": "test"},  # row-000006
    ]
    cases.append(
        EvalCase(
            case_id="ent_shared_entities",
            description="Entity E1 appears on both sides (2 train + 2 test rows).",
            rows=shared_rows,
            roles=_roles(["x"], entity="entity"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-ENT-001",
                    status="evaluated",
                    finding_count=1,
                    severity="high",  # 2 of 3 test rows = 66.7% >= 10%
                    counts={
                        "Entity values present in both splits": (1, 2),
                        "Test rows belonging to an entity also present in train": (2, 3),
                        "Train rows belonging to an entity also present in test": (2, 3),
                    },
                    metrics={
                        "shared_groups": 1,
                        "train_distinct_groups": 2,
                        "test_distinct_groups": 2,
                        "unlabelled_entity_rows_train": 0,
                        "unlabelled_entity_rows_test": 0,
                    },
                )
            ],
            evidence_row_ids={"SS-ENT-001": ["row-000001", "row-000002", "row-000004", "row-000005"]},
        )
    )

    disjoint_rows = [
        {"entity": "E1", "x": "1", "split": "train"},
        {"entity": "E2", "x": "2", "split": "train"},
        {"entity": "E3", "x": "3", "split": "test"},
        {"entity": "E4", "x": "4", "split": "test"},
    ]
    cases.append(
        EvalCase(
            case_id="ent_disjoint_entities",
            description="Completely disjoint entities: evaluated, no finding.",
            rows=disjoint_rows,
            roles=_roles(["x"], entity="entity"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-ENT-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"shared_groups": 0, "train_distinct_groups": 2, "test_distinct_groups": 2},
                )
            ],
        )
    )

    within_rows = [
        {"entity": "E1", "x": "1", "split": "train"},
        {"entity": "E1", "x": "2", "split": "train"},
        {"entity": "E1", "x": "3", "split": "train"},
        {"entity": "E2", "x": "4", "split": "test"},
        {"entity": "E2", "x": "5", "split": "test"},
        {"entity": "E3", "x": "6", "split": "test"},
    ]
    cases.append(
        EvalCase(
            case_id="ent_repeated_within_split_only",
            description="Entities repeated only inside one split: no overlap finding.",
            rows=within_rows,
            roles=_roles(["x"], entity="entity"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-ENT-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"shared_groups": 0},
                )
            ],
        )
    )

    missing_rows = [
        {"entity": "E1", "x": "1", "split": "train"},  # row-000001
        {"entity": "E2", "x": "5", "split": "train"},  # row-000002 second non-missing entity
        {"entity": "", "x": "2", "split": "train"},  # row-000003 unlabelled
        {"entity": "E1", "x": "3", "split": "test"},  # row-000004
        {"entity": "E3", "x": "6", "split": "test"},  # row-000005
        {"entity": "", "x": "4", "split": "test"},  # row-000006 unlabelled
    ]
    cases.append(
        EvalCase(
            case_id="ent_missing_identifiers",
            description=(
                "Empty entity identifiers are counted separately on each side and "
                "never merged into one shared entity. Three non-missing entities "
                "keep role validation happy (a single distinct non-missing value is "
                "rejected as degenerate for group purposes)."
            ),
            rows=missing_rows,
            roles=_roles(["x"], entity="entity"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-ENT-001",
                    status="evaluated",
                    finding_count=1,
                    severity="high",  # 1 of 3 test rows = 33% >= 10% high threshold
                    counts={
                        "Entity values present in both splits": (1, 2),
                        "Test rows belonging to an entity also present in train": (1, 3),
                        "Train rows belonging to an entity also present in test": (1, 3),
                        "Test rows with an empty entity": (1, 3),
                        "Train rows with an empty entity": (1, 3),
                    },
                    metrics={
                        "shared_groups": 1,
                        "unlabelled_entity_rows_train": 1,
                        "unlabelled_entity_rows_test": 1,
                    },
                )
            ],
            evidence_row_ids={"SS-ENT-001": ["row-000001", "row-000004"]},
        )
    )

    # Group holdout isolates entities by construction; the audit of the
    # generated assignment must report zero overlap.
    cases.append(
        EvalCase(
            case_id="ent_group_holdout_isolation",
            description=(
                "A group holdout on the shared-entity fixture keeps every entity on "
                "one side, so the audit of that assignment has no overlap finding. "
                "The fixture has three entities; how they split between the two "
                "sides belongs to the seeded group strategy and is not asserted "
                "here, only that none straddles the boundary."
            ),
            rows=shared_rows,
            roles=_roles(["x"], entity="entity"),
            split=SplitConfig(kind="group", label="Group holdout", test_fraction=0.4, seed=7),
            expectations=[
                CheckExpectation(
                    rule_id="SS-ENT-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"shared_groups": 0, "entity_overlap_test_share": 0.0},
                )
            ],
        )
    )

    return cases


# --------------------------------------------------------------------------- #
# SS-CHR-001 cases
# --------------------------------------------------------------------------- #


def _chronology_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []
    ts_role = _roles(["x"], timestamp="ts")

    ordered_rows = [
        {"ts": "2024-01-01", "x": "1", "split": "train"},
        {"ts": "2024-01-02", "x": "2", "split": "train"},
        {"ts": "2024-01-03", "x": "3", "split": "train"},
        {"ts": "2024-01-04", "x": "4", "split": "train"},
        {"ts": "2024-01-05", "x": "5", "split": "train"},
        {"ts": "2024-01-06", "x": "6", "split": "test"},
        {"ts": "2024-01-07", "x": "7", "split": "test"},
    ]
    cases.append(
        EvalCase(
            case_id="chr_ordered",
            description="Chronologically ordered split: evaluated, no finding.",
            rows=ordered_rows,
            roles=ts_role,
            expectations=[
                CheckExpectation(
                    rule_id="SS-CHR-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"chronology_status": "ordered", "boundary_tie_rows": 0},
                )
            ],
        )
    )

    violation_rows = [
        {"ts": "2024-01-01", "x": "1", "split": "train"},
        {"ts": "2024-01-03", "x": "2", "split": "train"},
        {"ts": "2024-01-05", "x": "3", "split": "train"},
        {"ts": "2024-01-02", "x": "4", "split": "test"},
        {"ts": "2024-01-04", "x": "5", "split": "test"},
    ]
    cases.append(
        EvalCase(
            case_id="chr_violation",
            description=(
                "Two of three valid train rows are strictly later than the earliest "
                "test timestamp (2024-01-02)."
            ),
            rows=violation_rows,
            roles=ts_role,
            expectations=[
                CheckExpectation(
                    rule_id="SS-CHR-001",
                    status="evaluated",
                    finding_count=1,
                    severity="high",  # 2/3 = 66.7% >= 2%
                    counts={
                        "Train rows newer than the earliest test timestamp": (2, 3),
                        "tied exactly at the earliest test timestamp": (0, 3),
                    },
                    metrics={
                        "chronology_status": "violation",
                        "train_rows_after_earliest_test": 2,
                        "boundary_tie_rows": 0,
                    },
                )
            ],
        )
    )

    tie_rows = [
        {"ts": "2024-01-01", "x": "1", "split": "train"},
        {"ts": "2024-01-02", "x": "2", "split": "train"},
        {"ts": "2024-01-02", "x": "3", "split": "train"},
        {"ts": "2024-01-02", "x": "4", "split": "test"},
        {"ts": "2024-01-03", "x": "5", "split": "test"},
    ]
    cases.append(
        EvalCase(
            case_id="chr_boundary_ties",
            description=(
                "Train rows exactly equal to the earliest test timestamp are boundary "
                "ties, not violations; the check reports ordered with tie rows counted."
            ),
            rows=tie_rows,
            roles=ts_role,
            expectations=[
                CheckExpectation(
                    rule_id="SS-CHR-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"chronology_status": "ordered", "boundary_tie_rows": 2},
                )
            ],
        )
    )

    invalid_rows = [
        {"ts": "2024-01-01", "x": "1", "split": "train"},
        {"ts": "not-a-date", "x": "2", "split": "train"},
        {"ts": "2024-01-05", "x": "3", "split": "train"},
        {"ts": "2024-01-02", "x": "4", "split": "test"},
        {"ts": "", "x": "5", "split": "test"},
        {"ts": "2024-01-03", "x": "6", "split": "test"},
    ]
    cases.append(
        EvalCase(
            case_id="chr_invalid_timestamps",
            description=(
                "Unparsable timestamps are excluded from ordering and counted; the "
                "later valid train row is still a violation."
            ),
            rows=invalid_rows,
            roles=ts_role,
            expectations=[
                CheckExpectation(
                    rule_id="SS-CHR-001",
                    status="evaluated",
                    finding_count=1,
                    severity="high",  # 1 of 2 valid train rows
                    counts={
                        "Train rows newer than the earliest test timestamp": (1, 2),
                        "timestamp could not be parsed (excluded from ordering)": (1, 3),
                    },
                    metrics={
                        "unparsable_train_timestamps": 1,
                        "unparsable_test_timestamps": 1,
                        "train_rows_after_earliest_test": 1,
                    },
                )
            ],
        )
    )

    insufficient_rows = [
        {"ts": "not-a-date", "x": "1", "split": "train"},
        {"ts": "??? ", "x": "2", "split": "train"},  # trailing space still unparsable
        {"ts": "2024-01-02", "x": "3", "split": "test"},
        {"ts": "2024-01-03", "x": "4", "split": "test"},
    ]
    cases.append(
        EvalCase(
            case_id="chr_insufficient_data",
            description=(
                "No parsable train timestamp: the check reports insufficient data "
                "(a 'did not run' status), not a clean result."
            ),
            rows=insufficient_rows,
            roles=ts_role,
            expectations=[
                CheckExpectation(
                    rule_id="SS-CHR-001",
                    status="insufficient_data",
                    finding_count=0,
                    reason_contains="at least one parsable timestamp in each split",
                )
            ],
        )
    )

    cases.append(
        EvalCase(
            case_id="chr_intent_not_applicable",
            description=(
                "With chronology_intent='not_applicable' the check reports itself as "
                "not evaluated even on a violating split."
            ),
            rows=violation_rows,
            roles=ts_role,
            config=AuditConfig(chronology_intent="not_applicable"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-CHR-001",
                    status="not_evaluated",
                    finding_count=0,
                    reason_contains="declared as not future-prediction",
                )
            ],
        )
    )

    # Chronological splitting with timestamp ties: the cut moves so that every
    # row sharing the boundary timestamp stays on one side. Timestamps (sorted):
    # 1..8, 9, 9, 10, 11 with test_fraction 0.25 -> requested cut would fall
    # between the two 9s; the boundary must move right, leaving the ts=10 and
    # ts=11 rows as the 2-row test side.
    tied_sorted = [1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 10, 11]
    tie_split_rows = [
        {"ts": f"2024-03-{value:02d}", "x": str(index), "split": "unused"}
        for index, value in enumerate(tied_sorted)
    ]
    cases.append(
        EvalCase(
            case_id="chr_split_with_ties",
            description=(
                "A chronological holdout over timestamps with a tie group straddling "
                "the requested cut keeps every tied row on the train side; the audit "
                "of the generated assignment is ordered with zero ties at the "
                "boundary."
            ),
            rows=tie_split_rows,
            roles=_roles(["x"], timestamp="ts", split=""),
            split=SplitConfig(kind="chronological", label="Chronological", test_fraction=0.25),
            expectations=[
                CheckExpectation(
                    rule_id="SS-CHR-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"chronology_status": "ordered", "boundary_tie_rows": 0},
                )
            ],
        )
    )

    return cases


# --------------------------------------------------------------------------- #
# SS-TGT-001 cases
# --------------------------------------------------------------------------- #


def _target_copy_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []

    exact_rows = [
        {"c": "0", "noise": str(index), "t": "0" if index % 2 == 0 else "1", "split": "train"}
        if index < 8
        else {"c": "1", "noise": str(index), "t": "1", "split": "test"}
        for index in range(12)
    ]
    # Make 'c' an exact copy of 't' on every row.
    for row in exact_rows:
        row["c"] = row["t"]
    cases.append(
        EvalCase(
            case_id="tgt_exact_copy",
            description="A feature equal to the target on all comparable rows: high severity.",
            rows=exact_rows,
            roles=_roles(["c", "noise"], target="t"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-TGT-001",
                    status="evaluated",
                    finding_count=1,  # only 'c'; 'noise' never matches
                    severity="high",
                    counts={
                        "Rows where both the feature and the target are non-missing": (12, 12),
                        "Comparable values where the feature equals the target": (12, 12),
                    },
                )
            ],
        )
    )

    no_match_rows = [
        {"f": str(100 + index), "t": "0" if index % 2 == 0 else "1", "split": "train"}
        for index in range(10)
    ] + [{"f": str(200 + index), "t": "1", "split": "test"} for index in range(4)]
    cases.append(
        EvalCase(
            case_id="tgt_no_match",
            description="No feature reproduces the target: evaluated, no findings.",
            rows=no_match_rows,
            roles=_roles(["f"], target="t"),
            expectations=[
                CheckExpectation(rule_id="SS-TGT-001", status="evaluated", finding_count=0)
            ],
        )
    )

    # Partial missingness: 20 rows, feature missing on 5 -> comparable = 15,
    # matches = 14 -> coverage 14/15 = 0.933333 (>= 0.90, < 0.99). Target over
    # the comparable rows: 8 'yes' / 7 'no' -> baseline 0.5333; 0.9333 exceeds
    # baseline + 0.05 -> medium.
    partial_rows = []
    for index in range(15):
        target = "yes" if index % 2 == 0 else "no"  # 8 yes / 7 no
        partial_rows.append({"f": target, "t": target, "split": "train" if index < 10 else "test"})
    partial_rows[14]["f"] = "other"  # the single counterexample
    for index in range(5):
        partial_rows.append({"f": "", "t": "yes", "split": "train" if index < 3 else "test"})
    cases.append(
        EvalCase(
            case_id="tgt_partial_missingness",
            description=(
                "Coverage is measured only over comparable rows: 14 of 15 (93.3%) "
                "with one counterexample and five feature-missing rows excluded."
            ),
            rows=partial_rows,
            roles=_roles(["f"], target="t"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-TGT-001",
                    status="evaluated",
                    finding_count=1,
                    severity="medium",
                    counts={
                        "Rows where both the feature and the target are non-missing": (15, 20),
                        "Comparable values where the feature equals the target": (14, 15),
                        "Comparable values where the feature differs from the target": (1, 15),
                        "Rows excluded because the feature value is missing": (5, 20),
                    },
                )
            ],
        )
    )

    constant_target_rows = [
        {"f": str(index), "t": "always", "split": "train" if index < 8 else "test"}
        for index in range(12)
    ]
    cases.append(
        EvalCase(
            case_id="tgt_constant_target",
            description=(
                "A target with one distinct value makes the check insufficient "
                "(did not run), regardless of the features."
            ),
            rows=constant_target_rows,
            roles=_roles(["f"], target="t"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-TGT-001",
                    status="insufficient_data",
                    finding_count=0,
                    reason_contains="1 distinct non-missing",
                )
            ],
        )
    )

    # One qualifying exact-copy feature alongside a constant feature and a
    # feature with fewer than 10 comparable rows: only the copy is reported.
    small_rows = [
        {
            "copy": "0" if index % 2 == 0 else "1",
            "const": "k",
            "small": str(index % 2) if index < 5 else "",
            "t": "0" if index % 2 == 0 else "1",
            "split": "train" if index < 8 else "test",
        }
        for index in range(12)
    ]
    cases.append(
        EvalCase(
            case_id="tgt_constant_feature_and_small_sample",
            description=(
                "Only the exact-copy feature is reported: the constant feature has "
                "one distinct non-missing value and the sparse feature, though "
                "varying, has only 5 comparable rows (below the 10-row minimum); "
                "both skips are recorded in metrics."
            ),
            rows=small_rows,
            roles=_roles(["copy", "const", "small"], target="t"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-TGT-001",
                    status="evaluated",
                    finding_count=1,
                    severity="high",
                    metrics={
                        "constant_features_skipped": "const",
                        "features_below_min_comparable_rows": "small",
                    },
                )
            ],
        )
    )

    # Majority-class artefact: target 92% 'yes' (23/25); the feature predicts
    # 'yes' on every row except the two 'no' rows, where it says a third value
    # -> coverage 23/25 = 0.92 >= 0.90, but the target's majority rate is also
    # 0.92, so 0.92 < 0.92 + margin 0.05 -> low severity. The feature is NOT
    # constant (values 'yes' and 'other'), so the constant skip does not apply.
    artefact_rows = []
    for index in range(25):
        target = "yes" if index < 23 else "no"
        feature = "yes"
        artefact_rows.append({"f": feature, "t": target, "split": "train" if index < 16 else "test"})
    # Both 'no' rows miss: the feature predicts a third value there.
    artefact_rows[23]["f"] = "other"
    artefact_rows[24]["f"] = "other"
    cases.append(
        EvalCase(
            case_id="tgt_majority_artefact_low",
            description=(
                "Coverage 92% on a 92%-majority target does not clear the baseline "
                "margin, so the finding is low severity and says so."
            ),
            rows=artefact_rows,
            roles=_roles(["f"], target="t"),
            expectations=[
                CheckExpectation(
                    rule_id="SS-TGT-001",
                    status="evaluated",
                    finding_count=1,
                    severity="low",
                    counts={"Comparable values where the feature equals the target": (23, 25)},
                )
            ],
        )
    )

    return cases


# --------------------------------------------------------------------------- #
# SS-NEAR-001 cases
# --------------------------------------------------------------------------- #


def _near_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []
    near_none = AuditConfig(
        near_duplicates=NearDuplicateSettings(enabled=True, threshold=0.25, scaling="none")
    )

    # Hand-calculable distances with scaling='none' (raw units). All values are
    # exactly representable in binary floating point, so the 'at threshold'
    # comparison is exact: train a=1.0 vs test a=1.25 -> distance 0.25 == 0.25.
    boundary_rows = [
        {"a": "1.0", "b": "5.0", "split": "train"},  # row-000001
        {"a": "3.0", "b": "7.0", "split": "train"},  # row-000002
        {"a": "1.125", "b": "5.0", "split": "test"},  # row-000003 inside (0.125)
        {"a": "1.25", "b": "5.0", "split": "test"},  # row-000004 at threshold (0.25)
        {"a": "1.375", "b": "5.0", "split": "test"},  # row-000005 outside (0.375)
        {"a": "9.0", "b": "9.0", "split": "test"},  # row-000006 far
    ]
    cases.append(
        EvalCase(
            case_id="near_threshold_boundaries",
            description=(
                "Raw-unit distances with threshold 0.25: one pair inside (0.125), "
                "one exactly at the threshold (included), one outside (0.375)."
            ),
            rows=boundary_rows,
            roles=_roles(["a", "b"]),
            config=near_none,
            expectations=[
                CheckExpectation(
                    rule_id="SS-NEAR-001",
                    status="evaluated",
                    finding_count=1,
                    severity="medium",  # 2 of 4 test rows implicated = 50%
                    counts={
                        "Cross-split candidate pairs at or below the threshold": (2, 8),
                        "Analysed test rows in at least one candidate pair": (2, 4),
                        "Analysed train rows in at least one candidate pair": (1, 2),
                    },
                    metrics={"candidate_pairs": 2, "analysed_pairs": 8},
                )
            ],
            example_distances={"SS-NEAR-001": ["0.125000", "0.250000"]},
        )
    )

    # Robust scaling, single column. Combined values [0, 50, 50.04, 100]:
    # median 50.02, q25 37.5, q75 62.53, IQR 25.03. The train 50 / test 50.04
    # pair scales to ~0.0016 <= 0.05; every other pair scales to ~2 or more.
    robust_rows = [
        {"x": "0", "split": "train"},
        {"x": "50", "split": "train"},
        {"x": "50.04", "split": "test"},
        {"x": "100", "split": "test"},
    ]
    cases.append(
        EvalCase(
            case_id="near_robust_scaling",
            description=(
                "Robust (median/IQR) scaling finds exactly the near pair "
                "(train 50 vs test 50.04, scaled distance ~0.0016)."
            ),
            rows=robust_rows,
            roles=_roles(["x"]),
            config=AuditConfig(near_duplicates=NearDuplicateSettings(enabled=True, threshold=0.05)),
            expectations=[
                CheckExpectation(
                    rule_id="SS-NEAR-001",
                    status="evaluated",
                    finding_count=1,
                    severity="medium",  # 1 of 2 test rows = 50%
                    counts={
                        "Cross-split candidate pairs at or below the threshold": (1, 4),
                        "Analysed test rows in at least one candidate pair": (1, 2),
                        "Analysed train rows in at least one candidate pair": (1, 2),
                    },
                    metrics={"candidate_pairs": 1},
                )
            ],
        )
    )

    # Constant column excluded; a row missing both columns dropped; a row
    # missing one column retained and median-imputed (median of the analysed
    # a values 1, 1.1, 2, 50 -> 1.55).
    missing_rows = [
        {"a": "1.0", "c": "7", "split": "train"},
        {"a": "2.0", "c": "7", "split": "train"},
        {"a": "1.1", "c": "7", "split": "test"},
        {"a": "50", "c": "7", "split": "test"},
        {"a": "", "c": "", "split": "test"},  # 100% missing -> dropped
        {"a": "", "c": "7", "split": "test"},  # 50% missing -> kept, imputed 1.55
    ]
    cases.append(
        EvalCase(
            case_id="near_constant_and_missing",
            description=(
                "The constant column is excluded and reported; the fully-missing "
                "row is dropped; the half-missing row is median-imputed."
            ),
            rows=missing_rows,
            roles=_roles(["a", "c"]),
            config=near_none,
            expectations=[
                CheckExpectation(
                    rule_id="SS-NEAR-001",
                    status="evaluated",
                    finding_count=1,
                    severity="medium",  # 1 of 3 analysed test rows
                    counts={
                        "Cross-split candidate pairs at or below the threshold": (1, 6),
                        "Rows excluded for too many missing numeric values": (1, 6),
                    },
                    metrics={
                        "constant_columns_excluded": "c",
                        "rows_excluded_missingness": 1,
                        "imputed_cells": 1,
                    },
                )
            ],
        )
    )

    oversize_rows = [
        {"x": str(value), "split": "train" if index < 3 else "test"}
        for index, value in enumerate([1.0, 2.0, 3.0, 1.1, 40.0, 50.0])
    ]
    cases.append(
        EvalCase(
            case_id="near_skip_oversize",
            description="Oversize with policy 'skip' reports not evaluated, never truncates silently.",
            rows=oversize_rows,
            roles=_roles(["x"]),
            config=AuditConfig(
                near_duplicates=NearDuplicateSettings(
                    enabled=True, oversize_policy="skip", max_combined_rows=4
                )
            ),
            expectations=[
                CheckExpectation(
                    rule_id="SS-NEAR-001",
                    status="not_evaluated",
                    finding_count=0,
                    reason_contains="oversize policy is 'skip'",
                )
            ],
        )
    )

    # A guaranteed near pair under every seeded draw: each side has two close
    # values (1.00/1.10 vs 1.05/1.15) plus one far value, and the sample takes 2
    # of 3 per side, so whichever rows are drawn, at least one close train value
    # meets at least one close test value at raw distance <= 0.15 <= 0.25.
    oversize_close_rows = [
        {"x": str(value), "split": split}
        for split, values in (
            ("train", [1.0, 1.1, 100.0]),
            ("test", [1.05, 1.15, 200.0]),
        )
        for value in values
    ]
    cases.append(
        EvalCase(
            case_id="near_sample_oversize",
            description=(
                "Oversize with policy 'sample' runs on a seeded proportional "
                "sample and says so in the scope and limitations. Raw-unit "
                "distances guarantee at least one candidate pair in any 2-by-2 "
                "draw, because the pair total depends on which rows are sampled."
            ),
            rows=oversize_close_rows,
            roles=_roles(["x"]),
            config=AuditConfig(
                near_duplicates=NearDuplicateSettings(
                    enabled=True,
                    oversize_policy="sample",
                    max_combined_rows=4,
                    sample_seed=7,
                    scaling="none",
                    threshold=0.25,
                )
            ),
            expectations=[
                CheckExpectation(
                    rule_id="SS-NEAR-001",
                    status="evaluated",
                    finding_count=1,  # severity medium: >=0.5 of analysed test rows implicated
                    severity="medium",
                    metrics={"sampled_rows": 4, "effective_row_bound": 4},
                )
            ],
        )
    )

    text_rows = [
        {"g": "A", "split": "train"},
        {"g": "B", "split": "train"},
        {"g": "A", "split": "test"},
        {"g": "C", "split": "test"},
    ]
    cases.append(
        EvalCase(
            case_id="near_unsupported_non_numeric",
            description="No numeric feature column: unsupported, with the exclusions listed.",
            rows=text_rows,
            roles=_roles(["g"]),
            config=AuditConfig(near_duplicates=NearDuplicateSettings(enabled=True)),
            expectations=[
                CheckExpectation(
                    rule_id="SS-NEAR-001",
                    status="unsupported",
                    finding_count=0,
                    reason_contains="numeric features only",
                )
            ],
        )
    )

    # The check is opt-in: the same fixture that yields candidates above
    # reports 'disabled' under the default configuration.
    cases.append(
        EvalCase(
            case_id="near_disabled_by_default",
            description="Near-duplicate analysis disabled: status 'disabled', distinct from clean.",
            rows=boundary_rows,
            roles=_roles(["a", "b"]),
            expectations=[
                CheckExpectation(
                    rule_id="SS-NEAR-001",
                    status="disabled",
                    finding_count=0,
                    reason_contains="opt-in",
                )
            ],
        )
    )

    return cases


# --------------------------------------------------------------------------- #
# Generated-split strategy cases (random, stratified, chronological)
# --------------------------------------------------------------------------- #


def _split_strategy_cases() -> list[EvalCase]:
    """Cases that generate an assignment and audit the actual generated masks.

    Fixture rows deliberately carry no split column: the split under audit is
    the generated assignment, not anything in the file. Expected split facts
    (sizes, temporal ordering, class counts) are hand-derived from the
    documented strategy contracts in ``app.splits.strategies`` and the fixture
    arithmetic; the runner recomputes them independently from the assignment
    and fails the case on any disagreement.
    """
    cases: list[EvalCase] = []

    # -- random ---------------------------------------------------------- #
    # Three entities with 4 rows each: bigger than the 3-row test side, so no
    # entity can be pulled entirely into test -- every test row's entity is
    # necessarily still present in train, whatever rows the seeded permutation
    # picks. Entity overlap counts (1, 2 or 3) therefore vary with the seed and
    # are cross-checked against an independent recount instead of pinned.
    random_rows = [
        {"x": f"r{index + 1}", "entity": f"E{index // 4 + 1}"}
        for index in range(12)
    ]
    cases.append(
        EvalCase(
            case_id="split_random_repeated_entities",
            description=(
                "Random holdout of a 12-row fixture with three 4-row entities: "
                "assignment integrity (9/3 rows, exactly once, deterministic for "
                "seed 17), and entity overlap that must be >= 1 whatever the "
                "draw, recounted independently of SS-ENT-001."
            ),
            rows=random_rows,
            roles=_roles(["x"], entity="entity", split=""),
            split=SplitConfig(kind="random", label="Random holdout", test_fraction=0.25, seed=17),
            expectations=[
                CheckExpectation(
                    rule_id="SS-DUP-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"exact_duplicate_test_rows": 0},
                ),
                CheckExpectation(
                    rule_id="SS-ENT-001",
                    status="evaluated",
                    finding_count=1,  # every entity has >=4 rows and test has 3
                    severity="high",  # all 3 test rows sit in a shared entity -> share 1.0
                    counts={
                        # affected = whole test side; denominator = full test split
                        "Test rows belonging to an entity also present in train": (3, 3),
                    },
                ),
            ],
            expected_split_facts={"train_rows": 9, "test_rows": 3},
        )
    )

    # -- stratified ------------------------------------------------------ #
    # 6 A / 4 B, test fraction 0.5: requested test size = 5, and proportional
    # allocation is exact (6*0.5 = 3, 4*0.5 = 2), so both sides hold A=3, B=2.
    stratified_rows = [
        {"x": f"r{index + 1}", "label": "A" if index < 6 else "B"}
        for index in range(10)
    ]
    cases.append(
        EvalCase(
            case_id="split_stratified_class_preservation",
            description=(
                "Stratified holdout with classes 6 A / 4 B at fraction 0.5: "
                "5 test rows allocated exactly 3 A / 2 B, with the complement "
                "on the train side (hand-checkable because the proportions are "
                "integers)."
            ),
            rows=stratified_rows,
            roles=_roles(["x"], target="label", split=""),
            split=SplitConfig(
                kind="stratified", label="Stratified holdout", test_fraction=0.5, seed=3
            ),
            expectations=[
                CheckExpectation(
                    rule_id="SS-DUP-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"exact_duplicate_test_rows": 0},
                ),
                CheckExpectation(
                    rule_id="SS-TGT-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"distinct_target_values": 2},
                ),
            ],
            expected_split_facts={
                "train_rows": 5,
                "test_rows": 5,
                "train_class_counts": {"A": 3, "B": 2},
                "test_class_counts": {"A": 3, "B": 2},
            },
        )
    )

    # -- chronological, distinct timestamps ------------------------------ #
    # Ten distinct daily timestamps; requested test rows = round(0.3*10) = 3
    # moves the cut to sorted position 7, no tie anywhere: train Jan 1-7,
    # test Jan 8-10.
    chronological_rows = [
        {"x": f"r{index + 1}", "ts": f"2024-01-{index + 1:02d}T00:00:00Z"}
        for index in range(10)
    ]
    cases.append(
        EvalCase(
            case_id="split_chronological_distinct",
            description=(
                "Chronological holdout over ten distinct timestamps: the cut at "
                "sorted position 7 puts Jan 1-7 in train and Jan 8-10 in test; "
                "ordering and split sizes are verified from the original "
                "fixture timestamps joined to the generated assignment."
            ),
            rows=chronological_rows,
            roles=_roles(["x"], timestamp="ts", split=""),
            split=SplitConfig(
                kind="chronological", label="Chronological holdout", test_fraction=0.3
            ),
            expectations=[
                CheckExpectation(
                    rule_id="SS-DUP-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"exact_duplicate_test_rows": 0},
                ),
                CheckExpectation(
                    rule_id="SS-CHR-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"chronology_status": "ordered"},
                ),
            ],
            expected_split_facts={
                "train_rows": 7,
                "test_rows": 3,
                "ordered": True,
                "tie_groups_intact": True,
            },
        )
    )

    # -- chronological, boundary tie ------------------------------------- #
    # Jan 1-6 distinct, then Jan 7 shared by four rows. Requested cut = sorted
    # position 7 falls inside the tie; the documented policy moves the cut left
    # so the whole tie group stays together -> train Jan 1-6, test Jan 7 x4.
    tie_rows = [
        {"x": f"r{index + 1}", "ts": f"2024-01-{index + 1:02d}T00:00:00Z"}
        for index in range(6)
    ] + [
        {"x": f"r{index + 7}", "ts": "2024-01-07T00:00:00Z"}
        for index in range(4)
    ]
    cases.append(
        EvalCase(
            case_id="split_chronological_boundary_tie",
            description=(
                "Chronological holdout where the requested cut falls inside a "
                "four-row timestamp tie: the documented policy keeps the whole "
                "tie group on one side, so train gets 6 rows and test the 4 "
                "rows sharing Jan 7."
            ),
            rows=tie_rows,
            roles=_roles(["x"], timestamp="ts", split=""),
            split=SplitConfig(
                kind="chronological", label="Chronological holdout", test_fraction=0.3
            ),
            expectations=[
                CheckExpectation(
                    rule_id="SS-DUP-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"exact_duplicate_test_rows": 0},
                ),
                CheckExpectation(
                    rule_id="SS-CHR-001",
                    status="evaluated",
                    finding_count=0,
                    metrics={"chronology_status": "ordered"},
                ),
            ],
            expected_split_facts={
                "train_rows": 6,
                "test_rows": 4,
                "ordered": True,
                "tie_groups_intact": True,
            },
        )
    )

    return cases


# --------------------------------------------------------------------------- #
# Diagnostics case
# --------------------------------------------------------------------------- #


def _diagnostics_case() -> EvalCase:
    # 30 rows: 29 'no' / 1 'yes' overall (class imbalance); the test split is
    # 9 'no' / 1 'yes' while train is 20 'no' / 0 'yes' -> target ratio gap
    # |1.0 - 0.9| = 0.1. Features are unique per row and entity-free, so all
    # leakage checks must stay clean: imbalance and shift are diagnostics.
    rows = []
    for index in range(20):
        rows.append({"x": str(index), "t": "no", "split": "train"})
    for index in range(9):
        rows.append({"x": str(100 + index), "t": "no", "split": "test"})
    rows.append({"x": "200", "t": "yes", "split": "test"})
    return EvalCase(
        case_id="diag_imbalance_not_leakage",
        description=(
            "A 29:1 imbalanced target with a shifted train/test class mix produces "
            "zero findings; the imbalance shows up in diagnostics only."
        ),
        rows=rows,
        roles=_roles(["x"], target="t"),
        expectations=[
            CheckExpectation(rule_id="SS-DUP-001", status="evaluated", finding_count=0),
            CheckExpectation(rule_id="SS-TGT-001", status="evaluated", finding_count=0),
            CheckExpectation(
                rule_id="SS-ENT-001",
                status="not_evaluated",
                finding_count=0,
                reason_contains="No entity/group column",
            ),
            CheckExpectation(
                rule_id="SS-CHR-001",
                status="not_evaluated",
                finding_count=0,
                reason_contains="No timestamp column",
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# Demo-dataset cases (complete ground truth from the oracles)
# --------------------------------------------------------------------------- #


def _demo_cases(settings: Settings) -> list[EvalCase]:
    """Build one case per committed demo, with oracle-derived expectations."""
    from app.audit.dataset import select_existing_split
    from app.synthetic.manifest import (
        entries_by_id,
        get_demo,
        recommended_audit_config,
        recommended_roles,
    )

    entries = entries_by_id()
    cases: list[EvalCase] = []

    demo_specs: list[tuple[str, list[str]]] = [
        ("repeated_entity", ["SS-DUP-001", "SS-ENT-001", "SS-CHR-001", "SS-TGT-001"]),
        ("exact_duplicates", ["SS-DUP-001", "SS-ENT-001", "SS-CHR-001", "SS-TGT-001"]),
        ("chronology_violation", ["SS-DUP-001", "SS-CHR-001", "SS-TGT-001"]),
        ("target_copy", ["SS-DUP-001", "SS-TGT-001"]),
        ("near_duplicates", ["SS-DUP-001", "SS-NEAR-001"]),
        ("clean_control", ["SS-DUP-001", "SS-ENT-001", "SS-CHR-001", "SS-TGT-001"]),
    ]

    for demo_id, rule_ids in demo_specs:
        loaded = get_demo(demo_id).load(settings=settings)
        roles = recommended_roles(demo_id)
        frame = loaded.frame
        selection = select_existing_split(
            loaded,
            split_column=roles.split or "split",
            train_value=roles.split_train_value or "train",
            test_value=roles.split_test_value or "test",
        )
        train_mask = selection.masks.train
        test_mask = selection.masks.test

        config = recommended_audit_config(demo_id, settings=settings)
        if demo_id == "near_duplicates":
            # Show every planted pair as evidence (default cap is 10).
            config = config.model_copy(update={"max_examples": 50})

        expectations: list[CheckExpectation] = []
        missing_tokens = frozenset(config.missing_tokens)

        if "SS-DUP-001" in rule_ids:
            truth = oracles.duplicate_truth(
                frame, roles.features, train_mask, test_mask, missing_tokens=missing_tokens
            )
            if truth.shared_signatures:
                expectations.append(
                    CheckExpectation(
                        rule_id="SS-DUP-001",
                        status="evaluated",
                        finding_count=1,
                        severity=truth.severity,
                        counts={
                            "signatures present in both": (
                                truth.shared_signatures,
                                truth.test_signatures,
                            ),
                            "Test rows sharing a feature signature with a train row": (
                                truth.affected_test_rows,
                                int(test_mask.sum()),
                            ),
                            "Train rows sharing a feature signature with a test row": (
                                truth.affected_train_rows,
                                int(train_mask.sum()),
                            ),
                        },
                        metrics={
                            "exact_duplicate_test_rows": truth.affected_test_rows,
                            "exact_duplicate_shared_signatures": truth.shared_signatures,
                        },
                    )
                )
            else:
                expectations.append(
                    CheckExpectation(
                        rule_id="SS-DUP-001",
                        status="evaluated",
                        finding_count=0,
                        metrics={"exact_duplicate_test_rows": 0},
                    )
                )

        if "SS-ENT-001" in rule_ids:
            if roles.entity:
                truth = oracles.entity_truth(
                    frame,
                    roles.entity,
                    train_mask,
                    test_mask,
                    high_share_threshold=config.entity_overlap_high_test_share,
                    missing_tokens=missing_tokens,
                )
                if truth.shared_groups:
                    expectations.append(
                        CheckExpectation(
                            rule_id="SS-ENT-001",
                            status="evaluated",
                            finding_count=1,
                            severity=truth.severity,
                            counts={
                                "Entity values present in both splits": (
                                    truth.shared_groups,
                                    truth.test_distinct_groups,
                                ),
                                "Test rows belonging to an entity also present in train": (
                                    truth.affected_test_rows,
                                    int(test_mask.sum()),
                                ),
                            },
                            metrics={"shared_groups": truth.shared_groups},
                        )
                    )
                else:
                    expectations.append(
                        CheckExpectation(
                            rule_id="SS-ENT-001",
                            status="evaluated",
                            finding_count=0,
                            metrics={"shared_groups": 0},
                        )
                    )
            else:
                expectations.append(
                    CheckExpectation(
                        rule_id="SS-ENT-001",
                        status="not_evaluated",
                        finding_count=0,
                        reason_contains="No entity/group column",
                    )
                )

        if "SS-CHR-001" in rule_ids:
            if roles.timestamp:
                truth = oracles.chronology_truth(
                    frame,
                    roles.timestamp,
                    train_mask,
                    test_mask,
                    high_share_threshold=config.chronology_high_train_share,
                )
                if truth.status == "violation":
                    expectations.append(
                        CheckExpectation(
                            rule_id="SS-CHR-001",
                            status="evaluated",
                            finding_count=1,
                            severity=truth.severity,
                            counts={
                                "Train rows newer than the earliest test timestamp": (
                                    truth.affected_train_rows,
                                    truth.train_valid_rows,
                                ),
                            },
                            metrics={
                                "chronology_status": "violation",
                                "train_rows_after_earliest_test": truth.affected_train_rows,
                            },
                        )
                    )
                else:
                    expectations.append(
                        CheckExpectation(
                            rule_id="SS-CHR-001",
                            status="evaluated",
                            finding_count=0,
                            metrics={"chronology_status": truth.status},
                        )
                    )
            else:
                expectations.append(
                    CheckExpectation(
                        rule_id="SS-CHR-001",
                        status="not_evaluated",
                        finding_count=0,
                        reason_contains="No timestamp column",
                    )
                )

        if "SS-TGT-001" in rule_ids:
            if roles.target:
                truth = oracles.target_copy_truth(
                    frame,
                    roles.features,
                    roles.target,
                    min_coverage=config.target_copy_min_coverage,
                    high_coverage=config.target_copy_high_coverage,
                    baseline_margin=config.target_copy_baseline_margin,
                    min_comparable_rows=config.target_copy_min_comparable_rows,
                    categorical_max_unique=settings.diagnostics.categorical_max_unique,
                    missing_tokens=missing_tokens,
                )
                if truth.status == "insufficient_data":
                    expectations.append(
                        CheckExpectation(
                            rule_id="SS-TGT-001",
                            status="insufficient_data",
                            finding_count=0,
                            reason_contains="distinct non-missing",
                        )
                    )
                else:
                    expectations.append(
                        CheckExpectation(
                            rule_id="SS-TGT-001",
                            status="evaluated",
                            finding_count=len(truth.matches),
                            severity=truth.matches[0].severity if len(truth.matches) == 1 else None,
                        )
                    )
            else:
                expectations.append(
                    CheckExpectation(
                        rule_id="SS-TGT-001",
                        status="not_evaluated",
                        finding_count=0,
                        reason_contains="No target column",
                    )
                )

        if "SS-NEAR-001" in rule_ids:
            if config.near_duplicates.enabled:
                truth = oracles.near_duplicate_truth(
                    frame,
                    roles.features,
                    train_mask,
                    test_mask,
                    threshold=config.near_duplicates.threshold,
                    scaling=config.near_duplicates.scaling,
                    min_numeric_ratio=config.near_duplicates.min_numeric_ratio,
                    max_missing_fraction_per_row=config.near_duplicates.max_missing_fraction_per_row,
                )
                expectations.append(
                    CheckExpectation(
                        rule_id="SS-NEAR-001",
                        status=truth.status,
                        finding_count=1 if truth.candidate_pairs else 0,
                        severity=truth.severity,
                        counts={
                            "Cross-split candidate pairs at or below the threshold": (
                                truth.candidate_pairs,
                                truth.analysed_train_rows * truth.analysed_test_rows,
                            ),
                        },
                        metrics={"candidate_pairs": truth.candidate_pairs},
                    )
                )
            else:
                expectations.append(
                    CheckExpectation(
                        rule_id="SS-NEAR-001",
                        status="disabled",
                        finding_count=0,
                        reason_contains="opt-in",
                    )
                )

        case = EvalCase(
            case_id=f"demo_{demo_id}",
            description=(
                f"Committed demo {demo_id!r} audited with its recommended roles and "
                "configuration; complete expected outcomes from the independent oracles."
            ),
            demo_id=demo_id,
            roles=roles,
            config=config,
            expectations=expectations,
        )

        if demo_id == "near_duplicates":
            planted_pairs = [
                (entry["train_row_id"], entry["test_row_id"])
                for entry in entries[demo_id].get("planted_cases", [])
                if entry.get("kind") == "near_duplicate_pair"
            ]
            case.planted_pair_row_ids = {"SS-NEAR-001": planted_pairs}

        cases.append(case)

    return cases


# --------------------------------------------------------------------------- #
# Suite assembly
# --------------------------------------------------------------------------- #


def build_cases(settings: Settings) -> list[EvalCase]:
    """The full evaluation suite, in a stable order."""
    cases: list[EvalCase] = []
    cases.extend(_dup_cases())
    cases.extend(_entity_cases())
    cases.extend(_chronology_cases())
    cases.extend(_target_copy_cases())
    cases.extend(_near_cases())
    cases.extend(_split_strategy_cases())
    cases.append(_diagnostics_case())
    cases.extend(_demo_cases(settings))
    return cases


__all__ = [
    "CaseResult",
    "CheckExpectation",
    "CheckResult",
    "EvalCase",
    "build_cases",
]
