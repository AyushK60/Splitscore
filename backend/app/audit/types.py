"""Typed interfaces shared by the audit engine, the split engine, the API and
the report writers.

This module is intentionally free of FastAPI and pandas dependencies: the audit
engine depends only on Pydantic models plus plain Python containers, so it can
be unit-tested in isolation and reused outside the web app.

Design notes
------------
Findings are *evidence records*, not scores. A finding carries its own counts
with explicit denominators, a bounded set of example rows, and its own
limitations, so a reader can disagree with the conclusion while still reading
the evidence. There is deliberately no combined "trust score" anywhere in this
module.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.version import APP_VERSION, AUDIT_SCHEMA_VERSION

Severity = Literal["high", "medium", "low", "info"]
SplitLabel = Literal["train", "test"]
CheckStatus = Literal[
    "disabled",  # the user turned this check off
    "not_evaluated",  # a required column role was not provided
    "unsupported",  # the dataset/feature set is out of scope for this version
    "insufficient_data",  # a documented minimum (rows, coverage) was not met
    "error",  # the rule raised; isolated so other rules still run
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Dataset metadata
# --------------------------------------------------------------------------- #


class ColumnTypeInfo(_Model):
    """Inferred, advisory type information for one column.

    Inference never changes stored values; it only drives suggestions and the
    numeric/categorical decisions documented in each rule.
    """

    name: str
    numeric_parse_ratio: float = Field(
        description="Fraction of non-missing values that parse as finite numbers."
    )
    datetime_parse_ratio: float = Field(
        description="Fraction of non-missing values that parse as timestamps."
    )
    distinct_values: int = Field(description="Distinct non-missing values observed.")
    missing_count: int
    missing_ratio: float
    looks_numeric: bool
    looks_datetime: bool
    looks_identifier: bool = Field(
        description="Every observed value is distinct, suggesting an identifier."
    )
    example_values: list[str] = Field(
        description="Up to three observed values, for display only.", default_factory=list
    )


class DatasetSummary(_Model):
    """Everything a reader needs to identify the audited input."""

    dataset_id: str
    name: str
    source: Literal["upload", "demo"]
    is_synthetic: bool
    fingerprint_sha256: str = Field(
        description="SHA-256 of the uploaded bytes. A reproducibility identifier, "
        "not an anonymisation mechanism."
    )
    row_count: int
    column_count: int
    columns: list[str]
    created_at_utc: str
    demo_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ColumnRoles(_Model):
    """The user's explicit role assignment.

    ``features`` must be disjoint from ``target``, ``split``, ``entity``,
    ``timestamp`` and ``metadata_excluded``; this is enforced by
    :func:`app.audit.roles.validate_roles` and re-checked before every rule.
    """

    features: list[str]
    target: str | None = None
    entity: str | None = None
    timestamp: str | None = None
    split: str | None = None
    split_train_value: str | None = None
    split_test_value: str | None = None
    metadata_excluded: list[str] = Field(default_factory=list)

    def all_assigned(self) -> list[str]:
        assigned = list(self.features)
        for value in (
            self.target,
            self.entity,
            self.timestamp,
            self.split,
        ):
            if value is not None:
                assigned.append(value)
        return assigned


class RoleIssue(_Model):
    """One problem found while validating roles or the split definition."""

    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    column: str | None = None
    hint: str | None = None


class RoleValidationResult(_Model):
    roles: ColumnRoles
    ok: bool
    issues: list[RoleIssue]
    resolved: ResolvedRoles | None = None


class ResolvedRoles(_Model):
    """Roles after validation: the exact column sets each rule will use."""

    feature_columns: list[str]
    target_column: str | None
    entity_column: str | None
    timestamp_column: str | None
    split_column: str | None
    train_value: str | None
    test_value: str | None
    metadata_excluded: list[str]
    unused_columns: list[str] = Field(
        description="Columns present in the file that have no role and are not used "
        "in any comparison."
    )


# --------------------------------------------------------------------------- #
# Split configuration and summaries
# --------------------------------------------------------------------------- #


class SplitConfig(_Model):
    """A requested split strategy.

    ``kind='existing'`` uses the split column already present in the dataset.
    The other kinds generate assignments, which are stored separately and never
    mutate the uploaded dataset.
    """

    kind: Literal["existing", "random", "stratified", "group", "chronological"]
    label: str
    test_fraction: float = 0.25
    seed: int = 12345
    strategy_id: str | None = None


class SplitSummary(_Model):
    """What a split actually achieved, as opposed to what was requested."""

    strategy_id: str
    label: str
    kind: Literal["existing", "random", "stratified", "group", "chronological"]
    requested_test_fraction: float | None = None
    achieved_test_fraction: float = 0.0
    train_rows: int
    test_rows: int
    seed: int | None = None
    split_column: str | None = None
    train_value: str | None = None
    test_value: str | None = None
    proportion_note: str | None = Field(
        default=None,
        description="Explains why the achieved fraction differs from the requested one.",
    )
    notes: list[str] = Field(default_factory=list)
    assignment_id: str | None = Field(
        default=None,
        description="Identifier of the stored assignment for CSV export.",
    )


class SplitAssignment(_Model):
    """A concrete train/test assignment keyed by stable internal row ID."""

    assignment_id: str
    summary: SplitSummary
    train_row_ids: list[str]
    test_row_ids: list[str]


class RunHistoryEntry(_Model):
    """Minimal identity of one prior audit run in this session.

    The validation-reuse check uses these records — and only these records —
    because reuse is a property of the session's evaluation history, not of the
    dataset bytes. No entry, no reuse claim in either direction.
    """

    run_id: str
    kind: Literal["audit", "comparison"]
    dataset_id: str
    split_kind: str | None = None
    split_column: str | None = None
    train_value: str | None = None
    test_value: str | None = None
    train_rows: int = 0
    test_rows: int = 0
    findings_total: int = 0


# --------------------------------------------------------------------------- #
# Audit configuration, evidence and findings
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# S5 integrity declarations (user-declared, never inferred)
# --------------------------------------------------------------------------- #


AvailabilityLevel = Literal[
    "before_prediction",  # known strictly before the prediction/decision point
    "at_prediction",  # known at the prediction/decision point
    "after_prediction",  # only known afterwards (future-only information)
    "unknown",  # the user cannot say
]


class PreprocessingStep(_Model):
    """One declared preprocessing step and where it was fitted.

    This is a *declaration*, not an observation: SplitScope does not execute or
    instrument preprocessing, so the fit boundary is only as trustworthy as the
    declaration it comes from.
    """

    name: str = Field(description="Human-readable step name, e.g. 'standard scaler'.")
    kind: str = Field(description="Step kind, e.g. 'scaler', 'imputer', 'encoder', 'selector'.")
    columns: list[str] = Field(default_factory=list)
    fit_context: Literal["train_only", "full_dataset", "unknown", "not_recorded"] = "not_recorded"


class PreprocessingDeclaration(_Model):
    """The user's declared preprocessing pipeline and fit boundaries."""

    steps: list[PreprocessingStep] = Field(default_factory=list)
    note: str | None = None


class NearDuplicateSettings(_Model):
    """Configuration for the opt-in near-duplicate candidate analysis."""

    enabled: bool = False
    threshold: float = Field(
        default=0.05,
        description="Maximum normalised Chebyshev (L-infinity) distance between two "
        "rows for them to be reported as near-duplicate candidates. Distances are "
        "computed after documented diagnostic scaling, so the number is in "
        "'robust-scaled units', not raw measurement units.",
    )
    scaling: Literal["robust", "none"] = Field(
        default="robust",
        description="'robust' divides each column by its interquartile range after "
        "median centring. Diagnostic only; never exported as a modelling pipeline.",
    )
    scale_constant_columns: bool = Field(
        default=False,
        description="Reserved. Constant columns currently contribute zero distance by "
        "definition and are always reported as excluded rather than scaled.",
    )
    min_numeric_ratio: float = Field(
        default=0.8,
        description="A column is treated as numeric when at least this fraction of its "
        "non-missing values parse as finite numbers.",
    )
    max_missing_fraction_per_row: float = Field(
        default=0.5,
        description="Rows missing more than this fraction of the included columns are "
        "excluded from the analysis, with the excluded count reported.",
    )
    oversize_policy: Literal["sample", "skip"] = Field(
        default="sample",
        description="What to do when the combined row count exceeds the configured "
        "bound. 'sample' takes a seeded, disclosed sample; 'skip' reports the check as "
        "not evaluated.",
    )
    max_combined_rows: int = Field(
        default=500,
        description="Combined train + test rows that may enter the distance computation. "
        "The effective bound is the smaller of this value and the server-enforced limit.",
    )
    sample_seed: int = Field(
        default=7,
        description="Seed for the proportional sample taken when the combined row count "
        "exceeds the bound. Fixing the seed makes the sampled analysis reproducible.",
    )


class AuditConfig(_Model):
    """All audit settings that affect results, echoed into every report."""

    enable_exact_duplicates: bool = True
    enable_entity_overlap: bool = True
    enable_chronology: bool = True
    enable_target_copy: bool = True

    near_duplicates: NearDuplicateSettings = Field(default_factory=NearDuplicateSettings)

    strip_whitespace: bool = Field(
        default=True,
        description="Strip leading/trailing whitespace from every value before "
        "comparison. Applied to the comparison view only; stored values are unchanged.",
    )
    normalize_numeric_strings: bool = Field(
        default=False,
        description="Opt-in: canonicalise numeric-looking strings so that '1', '1.0' "
        "and '01' compare equal. Off by default because it can merge genuinely "
        "distinct string codes such as zero-padded identifiers.",
    )
    missing_tokens: list[str] = Field(
        default_factory=list,
        description="Literal strings treated as missing *in addition to* the empty "
        "string. Empty by default, so 'NA' is a literal value, not a missing value.",
    )

    #: Chronology is only a violation for an intended future-prediction evaluation.
    chronology_intent: Literal["future_prediction", "not_applicable"] = "future_prediction"

    # -- S5 integrity declarations ------------------------------------------- #
    #: Declared prediction-time availability per feature column. Absent columns
    #: are simply undeclared; nothing is inferred from column names.
    feature_availability: dict[str, AvailabilityLevel] = Field(
        default_factory=dict,
        description="User-declared knowledge availability per feature. SplitScope never "
        "infers this from a column name; undeclared features are reported as undeclared.",
    )
    #: Declared dependency edges for derived features (feature -> its inputs).
    derived_feature_dependencies: dict[str, list[str]] = Field(default_factory=dict)
    #: Declared prediction horizon in days for the temporal-horizon check.
    temporal_horizon_days: float | None = Field(
        default=None,
        description="Declared prediction horizon: how long after the training cutoff the "
        "evaluation is meant to predict. Without a declaration the horizon check reports "
        "NOT EVALUATED rather than guessing.",
    )
    temporal_horizon_note: str | None = Field(
        default=None,
        description="Free-text context for the horizon declaration (event-time "
        "interpretation, label delay, and so on).",
    )
    #: Declared preprocessing pipeline and fit boundaries (may stay None).
    preprocessing: PreprocessingDeclaration | None = None

    # -- severity / evidence thresholds, all reported in the audit settings -- #
    entity_overlap_high_test_share: float = 0.10
    chronology_high_train_share: float = 0.02
    target_copy_min_coverage: float = 0.90
    target_copy_high_coverage: float = 0.99
    target_copy_baseline_margin: float = Field(
        default=0.05,
        description="Coverage must exceed the majority-class rate of the target by this "
        "margin before a non-perfect match is treated as more than a majority-class "
        "artefact.",
    )
    target_copy_min_comparable_rows: int = 10
    max_examples: int = Field(default=10, ge=1, le=50)
    max_example_rows_per_example: int = Field(default=4, ge=1, le=10)

    def effective_near_duplicate_limit(self) -> int:
        return max(1, min(self.near_duplicates.max_combined_rows, 20000))


class Count(_Model):
    """A count with an explicit denominator and unit.

    Denominators are stated because "12 affected rows" means very different
    things in a 40-row test set and a 4000-row test set.
    """

    label: str
    affected: int
    denominator: int
    unit: Literal["rows", "groups", "signatures", "columns", "pairs", "values"]
    scope: str = Field(
        default="full split",
        description="The population the count was taken over, e.g. 'analysed sample' "
        "when sampling was used.",
    )
    note: str | None = None

    @property
    def ratio(self) -> float | None:
        if self.denominator <= 0:
            return None
        return self.affected / self.denominator


class EvidenceExample(_Model):
    """One bounded, human-checkable piece of evidence."""

    label: str
    row_ids: list[str] = Field(default_factory=list)
    details: dict[str, str] = Field(
        default_factory=dict,
        description="Display-only key/value detail. All values are strings so that no "
        "downstream consumer re-interprets them.",
    )


class Finding(_Model):
    """A supported leakage risk with its evidence and its own caveats."""

    rule_id: str
    title: str
    severity: Severity
    severity_rationale: str
    description: str
    evidence_summary: str
    counts: list[Count]
    examples: list[EvidenceExample]
    example_total: int = Field(
        description="Total number of example groups available, before bounding."
    )
    examples_truncated: bool
    recommended_action: str
    limitations: list[str]
    assumptions: list[str]


class NotEvaluatedCheck(_Model):
    """A check that produced no finding *because it did not run*.

    Kept strictly separate from "ran and found nothing", which is the only
    honest meaning of a clean result.
    """

    rule_id: str
    title: str
    status: CheckStatus
    reason: str
    details: dict[str, str] = Field(default_factory=dict)


class RuleMetric(_Model):
    """Supporting numbers produced by a rule for the UI and the report."""

    key: str
    label: str
    value: float | int | str
    unit: str | None = None


class RuleOutcome(_Model):
    """The result of running one rule."""

    rule_id: str
    title: str
    status: Literal[
        "evaluated",
        "disabled",
        "not_evaluated",
        "unsupported",
        "insufficient_data",
        "error",
    ]
    duration_ms: float
    findings: list[Finding] = Field(default_factory=list)
    metrics: list[RuleMetric] = Field(default_factory=list)
    not_evaluated: NotEvaluatedCheck | None = None


# --------------------------------------------------------------------------- #
# Supporting diagnostics (explicitly NOT findings)
# --------------------------------------------------------------------------- #


class SplitCounts(_Model):
    train_rows: int
    test_rows: int
    total_rows: int


class ColumnMissingness(_Model):
    column: str
    train_missing: int
    train_missing_ratio: float
    test_missing: int
    test_missing_ratio: float
    missing_ratio_gap: float


class CategoryShare(_Model):
    category: str
    train_count: int
    train_ratio: float
    test_count: int
    test_ratio: float
    ratio_gap: float
    is_other_bucket: bool = False


class DistributionSummary(_Model):
    column: str
    kind: Literal["categorical", "continuous", "not_available"]
    categories: list[CategoryShare] = Field(default_factory=list)
    train_missing: int = 0
    test_missing: int = 0
    max_abs_ratio_gap: float | None = None
    train_stats: dict[str, float] = Field(default_factory=dict)
    test_stats: dict[str, float] = Field(default_factory=dict)
    histogram_edges: list[float] = Field(default_factory=list)
    train_histogram: list[int] = Field(default_factory=list)
    test_histogram: list[int] = Field(default_factory=list)
    note: str | None = None


class Diagnostics(_Model):
    """Supporting distribution diagnostics.

    These are deliberately *not* findings: distribution shift and class
    imbalance are not leakage, and presenting them as such would overstate what
    the tool supports.
    """

    counts: SplitCounts
    missingness: list[ColumnMissingness]
    missingness_note: str
    target: DistributionSummary | None = None
    disclaimer: str


# --------------------------------------------------------------------------- #
# Audit results and split comparison
# --------------------------------------------------------------------------- #


class EvaluationSummary(_Model):
    evaluated_rule_ids: list[str]
    not_evaluated: list[NotEvaluatedCheck]
    findings_total: int
    findings_by_severity: dict[str, int]
    headline: str


# --------------------------------------------------------------------------- #
# S5 category risk scorecard
# --------------------------------------------------------------------------- #


ScorecardStatus = Literal[
    "finding_present",  # at least one rule in the category reported a finding
    "evaluated_no_finding",  # every rule that could run ran, and none found anything
    "error",  # a rule in this category raised
    "not_applicable",  # the checks exist but were disabled for this audit
    "not_checked",  # nothing ran: not evaluated, unsupported or lacking inputs
]


class ScorecardRule(_Model):
    """One rule's outcome inside a scorecard category."""

    rule_id: str
    title: str
    status: Literal[
        "evaluated", "disabled", "not_evaluated", "unsupported", "insufficient_data", "error"
    ]
    finding_count: int = 0
    max_severity: Severity | None = None
    not_evaluated_reason: str | None = None


class ScorecardCategory(_Model):
    """One risk category of the scorecard.

    There is deliberately no numeric score: a category is either carrying
    findings, clean under the checks that ran, not applicable, or not checked.
    Absence of findings is never presented as proof of safety.
    """

    key: str
    label: str
    status: ScorecardStatus
    finding_count: int
    max_severity: Severity | None = None
    #: Best-effort affected-row figure: the largest rows-unit count of each
    #: finding in the category, summed. Denominators stay in the findings.
    affected_rows: int | None = None
    rules: list[ScorecardRule] = Field(default_factory=list)


class RiskScorecard(_Model):
    """Category-based view of one audit run, derived only from its outcomes."""

    categories: list[ScorecardCategory]
    note: str = Field(
        description="What this scorecard does and does not claim.",
    )


class AuditResult(_Model):
    schema_version: str = AUDIT_SCHEMA_VERSION
    app_version: str = APP_VERSION
    generated_at_utc: str
    duration_ms: float
    audit_config: AuditConfig
    roles: ColumnRoles
    resolved_roles: ResolvedRoles
    dataset: DatasetSummary
    split: SplitSummary
    evaluation: EvaluationSummary
    findings: list[Finding]
    rule_outcomes: list[RuleOutcome]
    diagnostics: Diagnostics
    audit_limits: dict[str, Any]
    limitations: list[str]
    assumptions: list[str]
    risk_scorecard: RiskScorecard | None = None


class ComparisonRow(_Model):
    """One row of the split comparison table."""

    strategy_id: str
    label: str
    kind: str
    supported: bool
    unsupported_reason: str | None = None
    requested_test_fraction: float | None = None
    achieved_test_fraction: float | None = None
    train_rows: int = 0
    test_rows: int = 0
    proportion_note: str | None = None
    exact_duplicate_test_rows: int | None = None
    exact_duplicate_test_share: float | None = None
    entity_shared_groups: int | None = None
    entity_overlap_test_share: float | None = None
    chronology_status: str | None = None
    target_summary: str | None = None
    target_max_abs_ratio_gap: float | None = None
    finding_counts: dict[str, int] = Field(default_factory=dict)
    not_evaluated: list[NotEvaluatedCheck] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ComparisonResult(_Model):
    schema_version: str = AUDIT_SCHEMA_VERSION
    app_version: str = APP_VERSION
    generated_at_utc: str
    duration_ms: float
    dataset: DatasetSummary
    roles: ColumnRoles
    resolved_roles: ResolvedRoles
    audit_config: AuditConfig
    strategies: list[SplitConfig]
    rows: list[ComparisonRow]
    per_strategy_findings: dict[str, list[Finding]]
    selection_note: str
    limitations: list[str]
    plans: list["PlanComparison"] = Field(default_factory=list)


class PlanFoldFacts(_Model):
    """What one fold of an evaluation plan actually achieved and revealed."""

    fold_index: int
    repeat: int
    train_rows: int
    test_rows: int
    exact_duplicate_test_rows: int | None = None
    entity_shared_groups: int | None = None
    entity_overlap_test_share: float | None = None
    chronology_status: str | None = None
    findings_by_rule: dict[str, int] = Field(default_factory=dict)
    findings_total: int = 0
    duration_ms: float = 0.0


class PlanComparison(_Model):
    """An audited evaluation plan: per-fold facts plus honest aggregates."""

    plan_id: str
    kind: str
    label: str
    n_folds: int
    repeats: int
    gap: int
    seed: int | None = None
    supported: bool = True
    unsupported_reason: str | None = None
    notes: list[str] = Field(default_factory=list)
    folds: list[PlanFoldFacts] = Field(default_factory=list)
    #: Aggregates over folds: worst severity, folds with findings, mean/max
    #: entity overlap share, folds with chronology violations. No ranking.
    aggregate: dict[str, Any] = Field(default_factory=dict)


class ReportEnvelope(_Model):
    """Wrapper used by the downloadable JSON report."""

    report_kind: Literal["audit", "comparison"]
    report: dict[str, Any]


RoleValidationResult.model_rebuild()
ComparisonResult.model_rebuild()
