"""Model-based counterfactual what-if scenarios (S9C-C).

A bounded, versioned scenario service on top of the verified S9A
regression-adjustment machinery. The scenario model is the g-computation
outcome model m(t, x) refitted on the analysis cohort; a scenario fixes a
baseline covariate profile (explicit values, with numeric medians and
categorical modes as disclosed defaults) and reports the model's expected
outcome under treatment = 1 and treatment = 0 for that profile, plus the
cohort-standardised contrast on the same model.

These are **model-based conditional outcome predictions under explicit
assumptions** — never observed individual counterfactual outcomes, and never
interval-bearing results: no uncertainty is invented for a scenario. The
treatment itself is the only interventional variable; changing a baseline
covariate in the profile is a conditional-model scenario, not an intervention
on that covariate, and the payload says so. Profiles anchored to values
outside the cohort's observed support are answered with explicit
extrapolation warnings rather than silently extended.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.audit.dataset import Dataset
from app.causal.estimation.contracts import EstimationRequest
from app.causal.estimation.estimators import (
    _fit_outcome_model,
    _outcome_design,
    _potential_outcome_predictions,
)
from app.causal.estimation.preparation import (
    CATEGORICAL_KIND,
    NUMERIC_KIND,
    CovariateSpec,
    prepare_cohort,
)
from app.causal.estimation.service import (
    ESTIMATION_VERSION,
    _resolved_column,
    _reproducibility,
    run_identification_gate,
)
from app.causal.registry import CausalGraphRecord
from app.core.errors import ValidationFailure

#: Version of the what-if contract, echoed in every payload.
WHATIF_SCHEMA_VERSION = "1.0.0"

WHATIF_SCOPE_NOTE = (
    "Every number in this payload is a model-based conditional outcome prediction: the fitted "
    "outcome model's expectation for a stated covariate profile under each treatment state. It "
    "is not an observed outcome, not an individual counterfactual, and not an interval-bearing "
    "estimate. The treatment state is the only interventional variable; adjusting a baseline "
    "covariate in the profile describes a conditional scenario, not an intervention on that "
    "covariate."
)

MAX_PROFILE_FIELDS = 30


def _resolve_profile(
    prepared_frame: pd.DataFrame,
    covariates: list[CovariateSpec],
    profile: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Validate the profile against the cohort; fill disclosed defaults.

    Returns (resolved values keyed by column, per-column disclosures,
    extrapolation warnings).
    """
    by_column = {spec.column: spec for spec in covariates}
    unknown = sorted(set(profile) - set(by_column))
    if unknown:
        raise ValidationFailure(
            "The scenario profile names field(s) that are not adjustment covariates of this "
            "analysis. Only baseline covariates in the verified adjustment set can be set.",
            details={"unknown_fields": unknown, "adjustable": sorted(by_column)},
        )
    if len(profile) > MAX_PROFILE_FIELDS:
        raise ValidationFailure(
            f"The scenario profile sets {len(profile)} fields, above the bound of "
            f"{MAX_PROFILE_FIELDS}.",
            details={"max_profile_fields": MAX_PROFILE_FIELDS},
        )

    resolved: dict[str, Any] = {}
    disclosures: list[dict[str, Any]] = []
    extrapolation: list[str] = []
    for spec in covariates:
        column = spec.column
        series = prepared_frame[column]
        if spec.kind == NUMERIC_KIND:
            numeric = pd.to_numeric(series, errors="coerce").dropna()
            observed_min, observed_max = float(numeric.min()), float(numeric.max())
            if column in profile and profile[column] is not None:
                try:
                    value = float(profile[column])
                except (TypeError, ValueError) as error:
                    raise ValidationFailure(
                        f"Profile field '{column}' must be a number; "
                        f"{profile[column]!r} was given.",
                        details={"field": column},
                    ) from error
                disclosures.append({"field": column, "source": "explicit", "value": value})
                if value < observed_min or value > observed_max:
                    extrapolation.append(
                        f"'{column}' = {value:g} lies outside the cohort's observed range "
                        f"[{observed_min:g}, {observed_max:g}]; the model was never fitted on "
                        "this profile value and the prediction is an extrapolation."
                    )
            else:
                value = float(numeric.median())
                disclosures.append(
                    {"field": column, "source": "cohort_median", "value": value}
                )
            resolved[column] = value
        else:
            levels = spec.levels or []
            if column in profile and profile[column] is not None:
                value = str(profile[column])
                if levels and value not in levels:
                    raise ValidationFailure(
                        f"Profile field '{column}' was set to '{value}', which is not an "
                        "observed level of this covariate. The model cannot encode an "
                        "unobserved category.",
                        details={"field": column, "observed_levels": levels},
                    )
                disclosures.append({"field": column, "source": "explicit", "value": value})
            else:
                value = str(series.dropna().mode().iloc[0]) if len(series.dropna()) else ""
                disclosures.append(
                    {"field": column, "source": "cohort_mode", "value": value}
                )
            resolved[column] = value
    return resolved, disclosures, extrapolation


def _scenario_design(
    resolved: dict[str, Any],
    covariates: list[CovariateSpec],
    treatment_value: int,
) -> pd.DataFrame:
    row: dict[str, Any] = {column: resolved[column] for column in resolved}
    row["__splitscope_treatment__"] = treatment_value
    return pd.DataFrame([row])[
        [spec.column for spec in covariates] + ["__splitscope_treatment__"]
    ]


def _predict_arm(
    model: Any,
    resolved: dict[str, Any],
    covariates: list[CovariateSpec],
    outcome_task: str,
    treatment_value: int,
) -> float:
    design = _scenario_design(resolved, covariates, treatment_value)
    if outcome_task == "logistic":
        return float(model.predict_proba(design)[:, 1][0])
    return float(np.asarray(model.predict(design), dtype=float)[0])


def run_what_if(
    dataset: Dataset,
    record: CausalGraphRecord,
    request: EstimationRequest,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Run the identification gate, refit the scenario model, predict both arms."""
    gate = run_identification_gate(dataset, record, request)
    treatment_column = _resolved_column(record, request.treatment_node, "treatment")
    outcome_column = _resolved_column(record, request.outcome_node, "outcome")
    adjustment_columns = [
        _resolved_column(record, node_id, "adjustment") for node_id in request.adjustment_nodes
    ]
    prepared = prepare_cohort(
        dataset,
        request,
        treatment_column=treatment_column,
        outcome_column=outcome_column,
        covariate_columns=adjustment_columns,
    )
    if not isinstance(profile, dict):
        raise ValidationFailure(
            "The scenario profile must be an object mapping adjustment-covariate columns to "
            "values.",
            details={"received": type(profile).__name__},
        )

    resolved, disclosures, extrapolation = _resolve_profile(
        prepared.frame, prepared.covariates, profile
    )

    # The scenario model: exactly the verified g-computation outcome model.
    model = _fit_outcome_model(
        prepared.frame,
        prepared.treatment,
        prepared.outcome,
        prepared.covariates,
        prepared.missing_policy,
        prepared.outcome_task,
    )

    profile_treated = _predict_arm(
        model, resolved, prepared.covariates, prepared.outcome_task, 1
    )
    profile_control = _predict_arm(
        model, resolved, prepared.covariates, prepared.outcome_task, 0
    )

    # Cohort-standardised expectations from the same model: average m(1, X)
    # and m(0, X) over every analysed row.
    cohort_m1, cohort_m0 = _potential_outcome_predictions(
        model, prepared.frame, prepared.covariates, prepared.outcome_task
    )
    units = "probability_difference" if prepared.outcome_task == "logistic" else "outcome_units"

    defaults_applied = [item for item in disclosures if item["source"] != "explicit"]
    warnings = [WHATIF_SCOPE_NOTE]
    if extrapolation:
        warnings.append(
            "Extrapolation: " + " ".join(extrapolation)
            + " SplitScope does not silently extend findings beyond the observed support."
        )
    if defaults_applied:
        warnings.append(
            "Fields left unset were held at their cohort medians (numeric) or modes "
            "(categorical); every such default is listed in the scenario disclosures."
        )

    reproducibility = {
        **_reproducibility(dataset, record, request, request.uncertainty.seed or 0, ["regression_adjustment"]),
        "scenario": {
            "model": "g_computation_outcome_model",
            "profile_fields_explicit": len(profile),
            "profile_defaults": len(defaults_applied),
        },
        "analysis_kind": "what_if",
    }

    return {
        "analysis_kind": "what_if",
        "estimation_version": ESTIMATION_VERSION,
        "what_if_schema_version": WHATIF_SCHEMA_VERSION,
        "estimand": request.estimand,
        "gate": gate,
        "analysis": {
            **prepared.to_payload(),
            "treatment_column": treatment_column,
            "outcome_column": outcome_column,
            "adjustment_columns": adjustment_columns,
        },
        "model_specification": {
            "kind": "regression_adjustment_outcome_model",
            "outcome_task": prepared.outcome_task,
            "units": units,
            "uncertainty": (
                "None is reported. A scenario prediction is a conditional model expectation, "
                "and this service does not attach an interval to it. Use the estimation "
                "studio's bootstrap interval for the cohort-level effect."
            ),
            "covariates": [spec.column for spec in prepared.covariates],
        },
        "profile_scenario": {
            "profile": resolved,
            "disclosures": disclosures,
            "treated_prediction": profile_treated,
            "control_prediction": profile_control,
            "contrast": profile_treated - profile_control,
        },
        "cohort_scenario": {
            "treated_mean": float(np.mean(cohort_m1)),
            "control_mean": float(np.mean(cohort_m0)),
            "contrast": float(np.mean(cohort_m1) - np.mean(cohort_m0)),
            "note": (
                "The same model averaged over the whole analysis cohort. This is the "
                "g-computation ATE the estimation studio reports; it is shown here so the "
                "profile scenario can be compared with the cohort-average scenario."
            ),
        },
        "warnings": warnings,
        "reproducibility": reproducibility,
        "scope_note": WHATIF_SCOPE_NOTE,
    }


__all__ = [
    "WHATIF_SCHEMA_VERSION",
    "run_what_if",
]
