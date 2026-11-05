"""Versioned contracts and hard bounds for causal effect estimation (S9A).

The estimation request is deliberately explicit about everything that defines
the estimand: the graph and its expected fingerprint, the treatment and
outcome nodes with their two observed treatment values, the adjustment set
(S9A never picks one silently), the analysis cohort, the missing-data policy,
the cross-fitting design and the uncertainty construction. Anything the client
leaves unset is reported back as a default that was applied, mirroring the S6
Model Lab conventions.

Bounds are enforced before any model is fitted, with a typed, actionable
error — never a silent subsample. The bounds exist because nuisance fitting,
bootstrap resampling and categorical one-hot expansion are the places an
unbounded request could exhaust the bounded in-memory design.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Version of the estimation contract, echoed in every payload.
ESTIMATION_SCHEMA_VERSION = "1.0.0"

ESTIMATOR_NAMES = ("regression_adjustment", "ipw", "aipw")

ESTIMAND_NAMES = ("ate",)

#: Hard bounds (mirroring the S6 Model Lab style: enforced up front, reported
#: in the payload, never silently worked around).
class EstimationLimits:
    """Hard computational bounds for one estimation run."""

    #: Maximum analysed rows. Estimation on this stage targets the dataset
    #: upload bound (10 000 rows); the bound is re-checked on the *cohort*
    #: after exclusions so an oversized request is refused, not truncated.
    MAX_ROWS = 10_000
    #: Below this total the ATE is numerically meaningless.
    MIN_ROWS_TOTAL = 20
    #: Each treatment arm needs enough rows for nuisance fitting and for the
    #: weighted means to be defined at all.
    MIN_ROWS_PER_ARM = 10
    MAX_COVARIATES = 30
    #: A categorical covariate with more levels than this is refused (the
    #: one-hot expansion would dominate the design matrix).
    MAX_CATEGORICAL_LEVELS = 12
    #: Total encoded design columns (numeric + one-hot indicators) per fit.
    MAX_ENCODED_FEATURES = 300
    MAX_BOOTSTRAP_REPS = 2_000
    MIN_BOOTSTRAP_REPS = 100
    MIN_CROSSFIT_SPLITS = 2
    MAX_CROSSFIT_SPLITS = 10
    #: Propensity truncation, if the client explicitly requests it, must sit
    #: strictly inside these bounds.
    MIN_TRUNCATION_LEVEL = 0.01
    MAX_TRUNCATION_LEVEL = 0.49

    @classmethod
    def as_dict(cls) -> dict[str, int]:
        return {
            "max_rows": cls.MAX_ROWS,
            "min_rows_total": cls.MIN_ROWS_TOTAL,
            "min_rows_per_arm": cls.MIN_ROWS_PER_ARM,
            "max_covariates": cls.MAX_COVARIATES,
            "max_categorical_levels": cls.MAX_CATEGORICAL_LEVELS,
            "max_encoded_features": cls.MAX_ENCODED_FEATURES,
            "max_bootstrap_reps": cls.MAX_BOOTSTRAP_REPS,
            "min_bootstrap_reps": cls.MIN_BOOTSTRAP_REPS,
            "min_crossfit_splits": cls.MIN_CROSSFIT_SPLITS,
            "max_crossfit_splits": cls.MAX_CROSSFIT_SPLITS,
        }


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TreatmentMapping(_StrictModel):
    """Explicit two-value treatment mapping. Never inferred from labels."""

    treated: str = Field(min_length=1, max_length=100)
    control: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _values_must_differ(self) -> TreatmentMapping:
        if self.treated.strip() == self.control.strip():
            raise ValueError(
                "The treated and control values are identical; a treatment mapping must "
                "distinguish two different observed values."
            )
        return self


class CohortSelection(_StrictModel):
    """Explicit analysis cohort.

    The default (no fields set) is every dataset row that survives data
    preparation, reported as such. When a train/test assignment is named, the
    causal estimand is computed on exactly one partition — a predictive
    holdout is never silently combined with its fit partition, because model
    evaluation and causal estimation answer different questions.
    """

    split_assignment_id: str | None = Field(default=None, max_length=80)
    partition: Literal["train", "test"] | None = None


class CrossFitSpec(_StrictModel):
    """Cross-fitting design for AIPW nuisance fitting."""

    splits: int = Field(default=5, ge=2, le=10)
    #: Optional column of repeated-entity or grouping identifiers. When set,
    #: folds are formed with group-aware splitting so all rows of one entity
    #: stay on the same side of every split.
    group_column: str | None = Field(default=None, max_length=200)


class UncertaintySpec(_StrictModel):
    """How the interval around the point estimate is constructed."""

    #: ``influence_function`` is available for AIPW (cross-fitted) and IPW;
    #: ``bootstrap`` refits every nuisance model on each resample.
    method: Literal["influence_function", "bootstrap"] = "bootstrap"
    level: float = Field(default=0.95, gt=0.5, lt=0.999)
    reps: int = Field(default=500, ge=100, le=2_000)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class PropensityTruncation(_StrictModel):
    """Optional, fully explicit propensity truncation.

    Off by default: truncation biases the estimand in exchange for variance
    control, so SplitScope never applies it silently. When requested, the
    thresholds, the number of affected rows and the direction of the effect on
    the estimator are reported.
    """

    lower: float = Field(ge=0.01, le=0.49)
    upper: float = Field(ge=0.51, le=0.99)


class EstimationRequest(_StrictModel):
    """One fully specified causal effect estimation run."""

    estimand: Literal["ate"] = "ate"
    treatment_node: str = Field(min_length=1, max_length=80)
    outcome_node: str = Field(min_length=1, max_length=80)
    adjustment_nodes: list[str] = Field(default_factory=list, max_length=30)
    treatment_mapping: TreatmentMapping
    cohort: CohortSelection = Field(default_factory=CohortSelection)
    missing_data_policy: Literal["complete_case", "median_mode"] = "complete_case"
    cross_fit: CrossFitSpec = Field(default_factory=CrossFitSpec)
    uncertainty: UncertaintySpec = Field(default_factory=UncertaintySpec)
    propensity_truncation: PropensityTruncation | None = None
    #: Optional client-side staleness guard. When set and different from the
    #: stored graph's scientific fingerprint, the run is refused (409) instead
    #: of estimating against a graph the client has not seen.
    expected_spec_fingerprint_sha256: str | None = Field(
        default=None, min_length=64, max_length=64
    )


def estimation_scope_note() -> str:
    """The scientific scope note carried in every estimation payload."""
    return (
        "The estimate is an average treatment effect computed from this dataset under the "
        "assumed graph and the named adjustment set. Graphical identification, exchangeability "
        "(no unmeasured confounding), consistency, positivity and correct model specification "
        "are assumptions this computation relies on — none of them is proven by it. Diagnostics "
        "describe the data; they do not verify the causal assumptions."
    )


def payload_defaults_applied(request: EstimationRequest) -> list[dict[str, Any]]:
    """Explicit record of every default the client did not set."""
    defaults: list[dict[str, Any]] = []
    if request.cohort.split_assignment_id is None:
        defaults.append(
            {
                "field": "cohort.split_assignment_id",
                "value": None,
                "meaning": "No train/test partition named: the cohort is every dataset row "
                "that survives data preparation.",
            }
        )
    defaults.append(
        {
            "field": "missing_data_policy",
            "value": request.missing_data_policy,
            "meaning": (
                "Rows with missing values in required columns are excluded and reported."
                if request.missing_data_policy == "complete_case"
                else "Missing numeric values are median-imputed and categorical values take an "
                "explicit missing level, fitted per training fold. Imputation does not remove "
                "missing-data bias."
            ),
        }
    )
    if request.uncertainty.seed is None:
        defaults.append(
            {
                "field": "uncertainty.seed",
                "value": "generated_by_server",
                "meaning": "A seed was drawn for this run and recorded in the payload.",
            }
        )
    if request.propensity_truncation is None:
        defaults.append(
            {
                "field": "propensity_truncation",
                "value": None,
                "meaning": "Propensity scores are used untruncated.",
            }
        )
    return defaults


__all__ = [
    "ESTIMAND_NAMES",
    "ESTIMATION_SCHEMA_VERSION",
    "ESTIMATOR_NAMES",
    "CohortSelection",
    "CrossFitSpec",
    "EstimationLimits",
    "EstimationRequest",
    "PropensityTruncation",
    "TreatmentMapping",
    "UncertaintySpec",
    "estimation_scope_note",
    "payload_defaults_applied",
]
