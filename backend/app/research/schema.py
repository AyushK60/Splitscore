"""Typed study metadata, variable roles and their conflict matrix.

Two ideas hold this module together.

**Declared is not computed.** Every field on the Study Card is something a
researcher asserted. SplitScope never fills one in because a column looks like
it might be a target, and it never turns "unknown" into "not required". The
field list below is the only definition of what a card contains; the API, the
completion indicator and the export all read from it, so they cannot drift.

**Roles are a claim about meaning, not about type.** ``predictor`` says a column
would be available as a feature; ``future_only`` says its value is only known
after the outcome. Assigning both is not a preference, it is a contradiction, so
the conflict matrix blocks it rather than silently ranking one above the other.
Compatible combinations (a confounder is also a predictor) are allowed, because
refusing them would force users to lie about their design.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

STUDY_SCHEMA_VERSION = "1.0"
MANIFEST_SCHEMA_VERSION = "1.0"

#: Roles a column can carry. The first group is the original V1 vocabulary;
#: the second is the research vocabulary study introduces for study design.
ColumnRole = Literal[
    "entity",
    "timestamp",
    "split",
    "target",
    "predictor",
    "treatment",
    "confounder",
    "mediator",
    "effect_modifier",
    "instrument",
    "sensitive",
    "future_only",
    "excluded",
]

RESEARCH_ROLES: tuple[ColumnRole, ...] = (
    "entity",
    "timestamp",
    "split",
    "target",
    "predictor",
    "treatment",
    "confounder",
    "mediator",
    "effect_modifier",
    "instrument",
    "sensitive",
    "future_only",
    "excluded",
)

ROLE_LABELS: dict[str, str] = {
    "entity": "Entity / group identifier",
    "timestamp": "Timestamp",
    "split": "Split assignment",
    "target": "Outcome / target",
    "predictor": "Predictor",
    "treatment": "Treatment / exposure",
    "confounder": "Confounder",
    "mediator": "Mediator",
    "effect_modifier": "Effect modifier",
    "instrument": "Instrument",
    "sensitive": "Protected / sensitive attribute",
    "future_only": "Future-only variable",
    "excluded": "Excluded from analysis",
}

#: Roles that make a column a modelling covariate.
COVARIATE_ROLES = {"predictor", "confounder", "mediator", "effect_modifier", "instrument"}

#: Roles that are singular: at most one column may carry each.
SINGULAR_ROLES = ("target", "entity", "timestamp", "split")

#: Hard contradictions. Each pair is stored once, ordered, and reported as an
#: error that blocks saving the mapping.
INCOMPATIBLE_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("target", "predictor", "The outcome cannot also be a predictor in the same model."),
    ("target", "confounder", "A confounder explains the outcome; it cannot be the outcome."),
    ("target", "treatment", "The exposure and the outcome are different variables."),
    ("target", "mediator", "A mediator lies on the path to the outcome, so it cannot be the outcome."),
    ("target", "instrument", "An instrument affects the exposure, not the outcome directly."),
    ("target", "effect_modifier", "An effect modifier changes an effect on the outcome."),
    ("split", "predictor", "The split label is bookkeeping; using it as a feature is leakage."),
    ("split", "confounder", "The split label cannot be a study confounder."),
    ("split", "treatment", "The split label cannot be a treatment."),
    ("entity", "predictor", "An identifier is not a measurement; use it as the entity column."),
    ("entity", "confounder", "An identifier cannot be a confounder."),
    ("entity", "treatment", "An identifier cannot be a treatment."),
    ("timestamp", "predictor", "A timestamp column is handled as time metadata, not a feature."),
    ("excluded", "predictor", "An excluded column cannot also be a predictor."),
    ("excluded", "target", "An excluded column cannot also be the outcome."),
    ("excluded", "entity", "An excluded column cannot also be the entity."),
    ("excluded", "timestamp", "An excluded column cannot also be the timestamp."),
    ("excluded", "split", "An excluded column cannot also be the split column."),
    ("excluded", "confounder", "An excluded column cannot also be a confounder."),
    ("excluded", "treatment", "An excluded column cannot also be a treatment."),
    ("excluded", "mediator", "An excluded column cannot also be a mediator."),
    ("excluded", "instrument", "An excluded column cannot also be an instrument."),
    ("excluded", "effect_modifier", "An excluded column cannot also be an effect modifier."),
    ("excluded", "sensitive", "An excluded column cannot also be a declared sensitive attribute."),
    ("excluded", "future_only", "An excluded column cannot also be a future-only variable."),
    ("future_only", "predictor", "A value that is only known after the outcome cannot be a predictor."),
    ("future_only", "confounder", "A post-outcome value cannot be adjusted for as a confounder."),
    ("future_only", "treatment", "A post-outcome value cannot be the exposure."),
    ("future_only", "instrument", "A post-outcome value cannot serve as an instrument."),
    ("future_only", "mediator", "A post-outcome value cannot be a mediator."),
)

#: Combinations that are allowed but change how results should be read.
SOFT_CONFLICTS: tuple[tuple[str, str, str], ...] = (
    (
        "mediator",
        "confounder",
        "A column cannot be both a mediator and a confounder for the same exposure/outcome pair; "
        "adjusting for it would block part of the effect.",
    ),
    (
        "instrument",
        "confounder",
        "An instrument and a confounder play opposite roles; check the graph before adjusting.",
    ),
    (
        "treatment",
        "confounder",
        "The same column is marked as exposure and as a confounder.",
    ),
    (
        "sensitive",
        "predictor",
        "A protected attribute is being used as a predictor; record the justification and the "
        "fairness analysis you intend to run.",
    ),
)

MAX_ROLE_COLUMNS = 200


class StudyDesign(StrEnum):
    CROSS_SECTIONAL = "cross_sectional"
    LONGITUDINAL = "longitudinal"
    EXPERIMENTAL = "experimental"
    QUASI_EXPERIMENTAL = "quasi_experimental"
    OBSERVATIONAL = "observational"
    OTHER = "other"
    UNKNOWN = "unknown"


class TargetTask(StrEnum):
    PREDICTION = "prediction"
    DESCRIPTIVE = "descriptive"
    CAUSAL = "causal"
    EXPLORATION = "exploration"
    UNKNOWN = "unknown"


class ConsentStatus(StrEnum):
    OBTAINED = "obtained"
    WAIVER_GRANTED = "waiver_granted"
    NOT_REQUIRED = "not_required"
    REFUSED = "refused"
    UNKNOWN = "unknown"


class PredictorAvailability(StrEnum):
    AT_PREDICTION_TIME = "at_prediction_time"
    AFTER_OUTCOME = "after_outcome"
    MIXED = "mixed"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


PrivacyFlag = Literal[
    "contains_direct_identifiers",
    "contains_sensitive_attributes",
    "restricted_use",
]


class StudyCardDraft(BaseModel):
    """User-declared study metadata. Missing is represented by ``None``."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    objective: str | None = Field(default=None, max_length=2000)
    domain: str | None = Field(default=None, max_length=120)
    design: StudyDesign | None = None
    unit_of_analysis: str | None = Field(default=None, max_length=200)
    population: str | None = Field(default=None, max_length=2000)
    sampling: str | None = Field(default=None, max_length=2000)
    collection_period: str | None = Field(default=None, max_length=120)
    data_owner: str | None = Field(default=None, max_length=200)
    rights_note: str | None = Field(default=None, max_length=2000)
    consent_status: ConsentStatus | None = None
    primary_outcome: str | None = Field(default=None, max_length=200)
    target_task: TargetTask | None = None
    predictor_availability: PredictorAvailability | None = None
    missing_data_convention: str | None = Field(default=None, max_length=2000)
    inclusion_rules: str | None = Field(default=None, max_length=2000)
    exclusion_rules: str | None = Field(default=None, max_length=2000)
    limitations: str | None = Field(default=None, max_length=4000)
    privacy_flags: list[PrivacyFlag] = Field(default_factory=list, max_length=3)

    @field_validator("*", mode="before")
    @classmethod
    def _strip_blank(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class FieldSpec(BaseModel):
    name: str
    label: str
    section: str
    required: bool
    help: str
    kind: Literal["text", "longtext", "select"]


STUDY_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="title",
        label="Study title",
        section="Purpose",
        required=True,
        help="A short name for this study. It appears on exports.",
        kind="text",
    ),
    FieldSpec(
        name="objective",
        label="Research question",
        section="Purpose",
        required=True,
        help="What you intend to learn, in one or two sentences.",
        kind="longtext",
    ),
    FieldSpec(
        name="domain",
        label="Domain",
        section="Purpose",
        required=False,
        help="Field of study, for example clinical, education or marketing.",
        kind="text",
    ),
    FieldSpec(
        name="target_task",
        label="Target task",
        section="Purpose",
        required=True,
        help="Prediction, description, causal estimation or exploration.",
        kind="select",
    ),
    FieldSpec(
        name="primary_outcome",
        label="Primary outcome",
        section="Purpose",
        required=False,
        help="The variable the question is about. Naming it does not assign its role.",
        kind="text",
    ),
    FieldSpec(
        name="design",
        label="Study design",
        section="Design",
        required=True,
        help="How the data were produced - as declared by you, not detected.",
        kind="select",
    ),
    FieldSpec(
        name="unit_of_analysis",
        label="Unit of analysis",
        section="Design",
        required=True,
        help="What one row represents: a patient, a session, a neighbourhood…",
        kind="text",
    ),
    FieldSpec(
        name="population",
        label="Population",
        section="Design",
        required=False,
        help="Who or what the rows describe, and any eligibility boundaries.",
        kind="longtext",
    ),
    FieldSpec(
        name="sampling",
        label="Sampling approach",
        section="Design",
        required=False,
        help="How the sample was drawn. Leave blank if you do not know.",
        kind="longtext",
    ),
    FieldSpec(
        name="collection_period",
        label="Collection period",
        section="Design",
        required=False,
        help="When the data were collected, as free text.",
        kind="text",
    ),
    FieldSpec(
        name="inclusion_rules",
        label="Inclusion rules",
        section="Design",
        required=False,
        help="Conditions a record had to meet to enter the dataset.",
        kind="longtext",
    ),
    FieldSpec(
        name="exclusion_rules",
        label="Exclusion rules",
        section="Design",
        required=False,
        help="Conditions that removed records. State them even if none applied.",
        kind="longtext",
    ),
    FieldSpec(
        name="predictor_availability",
        label="Predictor timing",
        section="Design",
        required=False,
        help="Whether the predictors would be known at prediction time.",
        kind="select",
    ),
    FieldSpec(
        name="missing_data_convention",
        label="Missing-data convention",
        section="Measurement",
        required=False,
        help="How blanks should be read in your file (for example: not measured).",
        kind="longtext",
    ),
    FieldSpec(
        name="data_owner",
        label="Data owner / source",
        section="Rights",
        required=False,
        help="Who provided the data. Declared, not verified by SplitScope.",
        kind="text",
    ),
    FieldSpec(
        name="rights_note",
        label="Use permission note",
        section="Rights",
        required=False,
        help="What you are permitted to do with this data.",
        kind="longtext",
    ),
    FieldSpec(
        name="consent_status",
        label="Consent / authorisation",
        section="Rights",
        required=False,
        help="Only record a status you can substantiate. SplitScope does not verify it.",
        kind="select",
    ),
    FieldSpec(
        name="limitations",
        label="Known limitations",
        section="Rights",
        required=False,
        help="Design weaknesses a reader should know before interpreting results.",
        kind="longtext",
    ),
)

REQUIRED_FIELDS: tuple[str, ...] = tuple(spec.name for spec in STUDY_FIELDS if spec.required)

FIELD_LABELS: dict[str, str] = {spec.name: spec.label for spec in STUDY_FIELDS}

SELECT_OPTIONS: dict[str, list[dict[str, str]]] = {
    "design": [
        {"value": "cross_sectional", "label": "Cross-sectional"},
        {"value": "longitudinal", "label": "Longitudinal"},
        {"value": "experimental", "label": "Experimental"},
        {"value": "quasi_experimental", "label": "Quasi-experimental"},
        {"value": "observational", "label": "Observational"},
        {"value": "other", "label": "Other"},
        {"value": "unknown", "label": "Not stated"},
    ],
    "target_task": [
        {"value": "prediction", "label": "Prediction"},
        {"value": "descriptive", "label": "Description"},
        {"value": "causal", "label": "Causal estimation"},
        {"value": "exploration", "label": "Exploration"},
        {"value": "unknown", "label": "Not stated"},
    ],
    "consent_status": [
        {"value": "obtained", "label": "Consent obtained"},
        {"value": "waiver_granted", "label": "Waiver granted"},
        {"value": "not_required", "label": "Not required"},
        {"value": "refused", "label": "Refused / not available"},
        {"value": "unknown", "label": "Not stated"},
    ],
    "predictor_availability": [
        {"value": "at_prediction_time", "label": "Known at prediction time"},
        {"value": "after_outcome", "label": "Only known after the outcome"},
        {"value": "mixed", "label": "Mixed across columns"},
        {"value": "not_applicable", "label": "Not applicable"},
        {"value": "unknown", "label": "Not stated"},
    ],
}


def declared_fields(draft: StudyCardDraft) -> dict[str, bool]:
    """Which study fields carry a user-declared value."""
    data = draft.model_dump()
    return {
        spec.name: bool(data.get(spec.name)) or (spec.name == "privacy_flags" and bool(data["privacy_flags"]))
        for spec in STUDY_FIELDS
    }


def completion(draft: StudyCardDraft) -> dict[str, object]:
    """Required-field completion. Deliberately not a validity score."""
    data = draft.model_dump()
    satisfied = [name for name in REQUIRED_FIELDS if data.get(name)]
    missing = [name for name in REQUIRED_FIELDS if not data.get(name)]
    return {
        "required": len(REQUIRED_FIELDS),
        "declared": len(satisfied),
        "ratio": round(len(satisfied) / len(REQUIRED_FIELDS), 3),
        "missing": missing,
        "note": (
            "Counts only fields this product requires to describe a study. It is not a measure "
            "of scientific quality or ethical approval."
        ),
    }


def study_issues(draft: StudyCardDraft) -> list[dict[str, str]]:
    """Validation messages for the card itself (not for the dataset)."""
    issues: list[dict[str, str]] = []
    for name in REQUIRED_FIELDS:
        if not getattr(draft, name):
            issues.append(
                {
                    "code": f"missing_{name}",
                    "severity": "warning",
                    "field": name,
                    "message": f"{FIELD_LABELS[name]} has not been declared.",
                }
            )
    if draft.predictor_availability is PredictorAvailability.AT_PREDICTION_TIME and any(
        role == "future_only" for role in []
    ):  # pragma: no cover - placeholder kept explicit for readers
        pass
    if draft.rights_note and draft.consent_status is None:
        issues.append(
            {
                "code": "consent_not_stated",
                "severity": "info",
                "field": "consent_status",
                "message": "A use-permission note exists but no consent status was declared.",
            }
        )
    return issues


def normalise_assignments(
    assignments: dict[str, list[str]], columns: list[str]
) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    """Clean a role map, keeping only known roles and reporting unknown columns.

    Order is preserved from the dataset so the derived feature list is stable
    between requests (a set would reorder it).
    """
    issues: list[dict[str, str]] = []
    known = set(columns)
    cleaned: dict[str, list[str]] = {}
    for column, roles in assignments.items():
        if column not in known:
            issues.append(
                {
                    "code": "unknown_column",
                    "severity": "error",
                    "column": column,
                    "message": f"Column {column!r} is not part of this dataset.",
                }
            )
            continue
        seen: list[str] = []
        for role in roles:
            if role not in RESEARCH_ROLES:
                issues.append(
                    {
                        "code": "unknown_role",
                        "severity": "error",
                        "column": column,
                        "message": f"{role!r} is not a recognised research role.",
                    }
                )
                continue
            if role not in seen:
                seen.append(role)
        if seen:
            cleaned[column] = seen
    return cleaned, issues


def role_conflicts(assignment: dict[str, list[str]]) -> list[dict[str, str]]:
    """Apply the conflict matrix to one column's roles."""
    issues: list[dict[str, str]] = []
    roles = set(assignment["roles"])
    column = assignment["column"]

    for left, right, reason in INCOMPATIBLE_PAIRS:
        if left in roles and right in roles:
            issues.append(
                {
                    "code": "role_conflict",
                    "severity": "error",
                    "column": column,
                    "message": f"{ROLE_LABELS[left]} and {ROLE_LABELS[right].lower()} cannot both apply.",
                    "hint": reason,
                }
            )
    for left, right, reason in SOFT_CONFLICTS:
        if left in roles and right in roles:
            issues.append(
                {
                    "code": "role_tension",
                    "severity": "warning",
                    "column": column,
                    "message": f"{ROLE_LABELS[left]} and {ROLE_LABELS[right].lower()} are both assigned.",
                    "hint": reason,
                }
            )
    return issues


def build_role_map(
    columns: list[str],
    assignments: dict[str, list[str]],
    *,
    split_train_value: str | None,
    split_test_value: str | None,
) -> dict[str, object]:
    """Validate a research role map and derive the V1 column roles from it.

    The derived roles are the single source of truth handed to the audit engine,
    so the research workspace and the audit cannot disagree about what a column
    means. V1 validation still runs on the derived roles, and its issues are
    returned alongside the research-level ones.
    """
    cleaned, issues = normalise_assignments(assignments, columns)
    if not cleaned:
        issues.append(
            {
                "code": "no_roles",
                "severity": "error",
                "column": None,
                "message": "No column has a research role yet.",
                "hint": "Assign at least a target or an entity before auditing.",
            }
        )

    for role in SINGULAR_ROLES:
        carriers = [column for column, roles in cleaned.items() if role in roles]
        if len(carriers) > 1:
            issues.append(
                {
                    "code": f"multiple_{role}",
                    "severity": "error",
                    "column": carriers[0],
                    "message": (
                        f"{len(carriers)} columns are marked as {ROLE_LABELS[role].lower()}: "
                        f"{', '.join(carriers[:5])}. Exactly one is allowed."
                    ),
                }
            )

    ordered = [column for column in columns if column in cleaned]
    for column in ordered:
        issues.extend(role_conflicts({"column": column, "roles": cleaned[column]}))

    features = [
        column
        for column in ordered
        if "predictor" in cleaned[column]
        and not {"target", "split", "entity", "timestamp", "excluded"} & set(cleaned[column])
    ]

    def first(role: str) -> str | None:
        for column in ordered:
            if role in cleaned[column]:
                return column
        return None

    target = first("target")
    entity = first("entity")
    timestamp = first("timestamp")
    split = first("split")
    excluded = [column for column in ordered if "excluded" in cleaned[column]]

    derived = {
        "features": features,
        "target": target,
        "entity": entity,
        "timestamp": timestamp,
        "split": split,
        "split_train_value": split_train_value if split else None,
        "split_test_value": split_test_value if split else None,
        "metadata_excluded": excluded,
    }

    errors = [issue for issue in issues if issue["severity"] == "error"]
    return {
        "ok": not errors,
        "assignments": cleaned,
        "derived_roles": derived,
        "issues": issues,
        "errors": len(errors),
        "warnings": len([issue for issue in issues if issue["severity"] == "warning"]),
        "note": (
            "Derived roles are what the audit engine receives. A role describes what you claim a "
            "column means; SplitScope never infers a role from a column name."
        ),
    }


__all__ = [
    "COVARIATE_ROLES",
    "FIELD_LABELS",
    "INCOMPATIBLE_PAIRS",
    "MANIFEST_SCHEMA_VERSION",
    "REQUIRED_FIELDS",
    "RESEARCH_ROLES",
    "ROLE_LABELS",
    "SELECT_OPTIONS",
    "SOFT_CONFLICTS",
    "STUDY_FIELDS",
    "STUDY_SCHEMA_VERSION",
    "ConsentStatus",
    "FieldSpec",
    "PredictorAvailability",
    "StudyCardDraft",
    "StudyDesign",
    "TargetTask",
    "build_role_map",
    "completion",
    "declared_fields",
    "normalise_assignments",
    "role_conflicts",
    "study_issues",
]
