"""Robustness experiments and sensitivity analysis (S9C-B).

Three *reproducible computational refutation experiments* on top of the
verified S9A estimators, run on the same gated cohort and adjustment set:

1. **Subsampling** — re-estimate on reproducibly drawn subsets of the cohort.
   Stability under subsampling describes sampling variability; it is never
   evidence that the estimate is unbiased.
2. **Placebo treatment** — re-estimate with the observed treatment vector
   randomly permuted (treated count preserved). The placebo distribution shows
   what the estimator produces when no treatment assignment structure exists.
   A placebo near zero does not prove the original estimate is causal.
3. **Hypothetical unmeasured confounder** — a binary confounder with stated
   associations to the observed treatment (log-odds shift γ) and outcome
   (shift κ per outcome SD) is *simulated conditional on the observed data*,
   added to the adjustment set, and the estimator is refitted across a γ×κ
   grid. This is a hypothetical scenario analysis, explicitly not a bound:
   the simulated U is generated from an assumed model, not recovered from the
   data, and what it shows is how the estimate would move if a confounder of
   exactly that structure existed and were adjusted for.

Every experiment re-runs the production estimator machinery — never a
frontend calculation — and every plotted value traces to a seeded, recorded
computation. Failures are reported per repetition, never averaged away.
"""

from __future__ import annotations

import secrets
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats

from app.audit.dataset import Dataset
from app.causal.estimation.contracts import (
    EstimationLimits,
    EstimationRequest,
)
from app.causal.estimation.estimators import (
    EstimationFailure,
    EstimatorOutput,
    estimate_aipw,
    estimate_ipw,
    estimate_regression_adjustment,
)
from app.causal.estimation.preparation import (
    NUMERIC_KIND,
    CovariateSpec,
    PreparedData,
    prepare_cohort,
)
from app.causal.estimation.service import (
    ESTIMATION_VERSION,
    _estimate_point,
    _resolved_column,
    _reproducibility,
    run_identification_gate,
)
from app.causal.registry import CausalGraphRecord
from app.core.errors import ValidationFailure

#: Version of the robustness contract, echoed in every payload.
ROBUSTNESS_SCHEMA_VERSION = "1.0.0"

ROBUSTNESS_SCOPE_NOTE = (
    "Robustness experiments re-run the verified estimator machinery on this cohort under "
    "perturbations or assumptions recorded in the payload. They describe the behaviour of "
    "the estimator on this sample; none of them proves that the causal assumptions "
    "(exchangeability, positivity, consistency, correct specification) hold."
)

SUBSAMPLING_CAVEAT = (
    "Agreement across subsamples describes sampling variability on this population. It is not "
    "evidence that the estimate is unbiased: a stable estimate can be stably wrong when a "
    "confounder is unmeasured."
)

PLACEBO_CAVEAT = (
    "Permuting the treatment destroys any assignment–outcome structure in the data, so a "
    "placebo estimate near zero shows only that the estimator produces near-zero noise under "
    "this permutation scheme. It does not verify that the original estimate is causal, and the "
    "permutation assumes exchangeable, independent assignment — it does not respect group "
    "structure or temporal ordering."
)

SENSITIVITY_CAVEAT = (
    "The simulated confounder is generated from an assumed model with the stated associations, "
    "conditioned on the observed treatment and outcome, and then adjusted for as if it had been "
    "measured. The grid shows how the estimate would move if a binary confounder of exactly "
    "that structure existed. This is a hypothetical scenario analysis, not a bound: no "
    "unmeasured confounder is recovered from the data, and real confounding can be stronger, "
    "multivariate or differently structured."
)


class RobustnessLimits:
    """Hard computational bounds for one robustness experiment."""

    MIN_REPS = 100
    MAX_REPS = 1_000
    MIN_FRACTION = 0.10
    MAX_FRACTION = 0.90
    #: The unmeasured-confounder grid is fixed at 5×5 to bound the compute.
    SENSITIVITY_GAMMA_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
    SENSITIVITY_KAPPA_VALUES = (0.0, 0.1, 0.2, 0.3, 0.4)
    MIN_PREVALENCE = 0.05
    MAX_PREVALENCE = 0.95

    @classmethod
    def as_dict(cls) -> dict[str, Any]:
        return {
            "min_reps": cls.MIN_REPS,
            "max_reps": cls.MAX_REPS,
            "min_fraction": cls.MIN_FRACTION,
            "max_fraction": cls.MAX_FRACTION,
            "sensitivity_gamma_values": list(cls.SENSITIVITY_GAMMA_VALUES),
            "sensitivity_kappa_values": list(cls.SENSITIVITY_KAPPA_VALUES),
            "min_prevalence": cls.MIN_PREVALENCE,
            "max_prevalence": cls.MAX_PREVALENCE,
        }


class SubsamplingSpec:
    def __init__(
        self,
        estimator: str = "aipw",
        reps: int = 200,
        fraction: float = 0.5,
    ) -> None:
        self.estimator = estimator
        self.reps = reps
        self.fraction = fraction


class PlaceboSpec:
    def __init__(
        self,
        estimator: str = "regression_adjustment",
        reps: int = 200,
    ) -> None:
        self.estimator = estimator
        self.reps = reps


class ConfounderSpec:
    def __init__(
        self,
        estimator: str = "regression_adjustment",
        prevalence: float = 0.3,
    ) -> None:
        self.estimator = estimator
        self.prevalence = prevalence


ExperimentSpec = SubsamplingSpec | PlaceboSpec | ConfounderSpec


def _check_estimator(name: str) -> None:
    if name not in ("regression_adjustment", "ipw", "aipw"):
        raise ValidationFailure(
            f"Unknown estimator '{name}' for the robustness experiment.",
            details={"supported": ["regression_adjustment", "ipw", "aipw"]},
        )


def _reps_bounds(value: int, kind: str) -> int:
    if not (RobustnessLimits.MIN_REPS <= value <= RobustnessLimits.MAX_REPS):
        raise ValidationFailure(
            f"{kind} repetitions must be between {RobustnessLimits.MIN_REPS} and "
            f"{RobustnessLimits.MAX_REPS}; {value} was requested.",
            details={"requested": value, **{k: v for k, v in RobustnessLimits.as_dict().items() if "reps" in k}},
        )
    return value


def _fit_named(
    estimator_name: str,
    prepared: PreparedData,
    request: EstimationRequest,
    frame: pd.DataFrame,
    treatment: np.ndarray,
    outcome: np.ndarray,
) -> EstimatorOutput:
    """One point fit of the named production estimator on the given arrays."""
    return _estimate_point(estimator_name, prepared, request, frame, treatment, outcome)


def _distribution_summary(values: list[float]) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(array)),
        "standard_deviation": float(np.std(array, ddof=1)) if array.size > 1 else None,
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "q05": float(np.quantile(array, 0.05)),
        "q50": float(np.quantile(array, 0.50)),
        "q95": float(np.quantile(array, 0.95)),
    }


def _run_repeats(
    estimator_name: str,
    prepared: PreparedData,
    request: EstimationRequest,
    reps: int,
    seed: int,
    perturb: Any,
) -> tuple[list[float], list[dict[str, Any]]]:
    """Run the estimator ``reps`` times on perturbed views; record failures honestly."""
    estimates: list[float] = []
    failures: list[dict[str, Any]] = []
    for rep in range(reps):
        rep_rng = np.random.default_rng([seed, rep])
        try:
            frame, treatment, outcome = perturb(rep_rng)
            output = _fit_named(estimator_name, prepared, request, frame, treatment, outcome)
            estimates.append(float(output.estimate))
        except EstimationFailure as error:
            failures.append({"rep": rep, "reason": error.message})
        except ValueError as error:
            failures.append(
                {"rep": rep, "reason": f"The estimator could not be fitted: {error}"}
            )
    return estimates, failures


# --------------------------------------------------------------------------- #
# Experiments
# --------------------------------------------------------------------------- #


def _subsampling(
    prepared: PreparedData,
    request: EstimationRequest,
    spec: SubsamplingSpec,
    seed: int,
) -> dict[str, Any]:
    _check_estimator(spec.estimator)
    reps = _reps_bounds(spec.reps, "Subsampling")
    fraction = float(spec.fraction)
    if not (RobustnessLimits.MIN_FRACTION <= fraction <= RobustnessLimits.MAX_FRACTION):
        raise ValidationFailure(
            f"The subsample fraction must be between {RobustnessLimits.MIN_FRACTION} and "
            f"{RobustnessLimits.MAX_FRACTION}; {fraction} was requested.",
            details={"requested": fraction},
        )
    n = prepared.rows_final
    size = int(round(fraction * n))
    if size < EstimationLimits.MIN_ROWS_TOTAL:
        raise ValidationFailure(
            f"A {fraction:.0%} subsample of this cohort is {size} rows, below the minimum of "
            f"{EstimationLimits.MIN_ROWS_TOTAL} for estimation.",
            details={"subsample_rows": size, "minimum": EstimationLimits.MIN_ROWS_TOTAL},
        )

    def draw(rng: Any) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        indices = rng.choice(n, size=size, replace=False)
        return (
            prepared.frame.iloc[indices].reset_index(drop=True),
            prepared.treatment[indices],
            prepared.outcome[indices],
        )

    estimates, failures = _run_repeats(spec.estimator, prepared, request, reps, seed, draw)
    warnings = [SUBSAMPLING_CAVEAT]
    if request.cross_fit.group_column:
        warnings.append(
            "A cross-fitting group column is set. Subsampling draws rows independently, so "
            "subsamples can contain partial entity clusters; the variation reported here "
            "understates the entity-level dependence in the data."
        )
    return {
        "experiment": "subsampling",
        "parameters": {
            "estimator": spec.estimator,
            "reps": reps,
            "fraction": fraction,
            "subsample_rows": size,
            "cohort_rows": n,
        },
        "distribution": _distribution_summary(estimates) if estimates else None,
        "estimates": estimates,
        "failures": failures,
        "warnings": warnings,
        "method_note": (
            "Each repetition draws a simple random subsample without replacement at the "
            "recorded fraction, refits the estimator from scratch (all nuisance models "
            "included), and records the estimate. Repetition r uses the deterministic "
            "generator seeded with [seed, r], so the whole series reproduces from the seed."
        ),
    }


def _placebo(
    prepared: PreparedData,
    request: EstimationRequest,
    spec: PlaceboSpec,
    seed: int,
) -> dict[str, Any]:
    _check_estimator(spec.estimator)
    reps = _reps_bounds(spec.reps, "Placebo")
    n = prepared.rows_final
    treated_count = int(prepared.treatment.sum())
    if treated_count == 0 or treated_count == n:
        raise ValidationFailure(
            "A placebo permutation requires both treatment arms to be non-empty.",
            details={"treated_rows": treated_count, "cohort_rows": n},
        )

    def draw(rng: Any) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        permuted = rng.permutation(prepared.treatment)
        return prepared.frame, permuted, prepared.outcome

    estimates, failures = _run_repeats(spec.estimator, prepared, request, reps, seed, draw)
    warnings = [PLACEBO_CAVEAT]
    if request.cross_fit.group_column:
        warnings.append(
            "A cross-fitting group column is set, but permutation reassigns treatment row by "
            "row, so rows of one entity can receive different placebo assignments. The placebo "
            "distribution is not group-valid for this configuration."
        )
    return {
        "experiment": "placebo_treatment",
        "parameters": {
            "estimator": spec.estimator,
            "reps": reps,
            "permuted_treated_rows": treated_count,
            "cohort_rows": n,
        },
        "distribution": _distribution_summary(estimates) if estimates else None,
        "estimates": estimates,
        "failures": failures,
        "warnings": warnings,
        "method_note": (
            "Each repetition draws a uniformly random permutation of the observed 0/1 "
            "treatment vector (the treated count is preserved), refits the estimator on the "
            "permuted assignment with the unchanged outcome and covariates, and records the "
            "estimate. Repetition r is seeded with [seed, r]."
        ),
    }


def _simulated_confounder_column(
    treatment: np.ndarray,
    outcome: np.ndarray,
    prevalence: float,
    gamma: float,
    kappa: float,
    rng: Any,
) -> np.ndarray:
    """One draw of the hypothetical binary confounder U.

    logit P(U=1) = logit(prevalence) + γ·T + κ·(Y − mean(Y))/sd(Y), evaluated
    on the observed data, so the simulated U is associated with both the
    observed treatment and outcome exactly as the scenario states.
    """
    outcome_z = (outcome - np.mean(outcome)) / (np.std(outcome) if np.std(outcome) > 0 else 1.0)
    logit_u = (
        np.log(prevalence / (1.0 - prevalence))
        + gamma * treatment
        + kappa * outcome_z
    )
    probability = 1.0 / (1.0 + np.exp(-logit_u))
    return (rng.random(len(treatment)) < probability).astype(float)


def _sensitivity(
    prepared: PreparedData,
    request: EstimationRequest,
    spec: ConfounderSpec,
    seed: int,
) -> dict[str, Any]:
    _check_estimator(spec.estimator)
    prevalence = float(spec.prevalence)
    if not (RobustnessLimits.MIN_PREVALENCE <= prevalence <= RobustnessLimits.MAX_PREVALENCE):
        raise ValidationFailure(
            f"The assumed confounder prevalence must be between "
            f"{RobustnessLimits.MIN_PREVALENCE} and {RobustnessLimits.MAX_PREVALENCE}.",
            details={"requested": prevalence},
        )
    gammas = RobustnessLimits.SENSITIVITY_GAMMA_VALUES
    kappas = RobustnessLimits.SENSITIVITY_KAPPA_VALUES
    outcome_sd = float(np.std(prepared.outcome))

    cells: list[list[float | None]] = []
    cell_failures: list[dict[str, Any]] = []
    for gamma_index, gamma in enumerate(gammas):
        row: list[float | None] = []
        for kappa_index, kappa in enumerate(kappas):
            rng = np.random.default_rng([seed, gamma_index, kappa_index])
            simulated = _simulated_confounder_column(
                prepared.treatment, prepared.outcome, prevalence, gamma, kappa, rng
            )
            frame = prepared.frame.copy()
            frame["__simulated_confounder__"] = simulated
            # The simulated U must actually enter the design: fit the named
            # estimator directly with the extended covariate list rather than
            # through _estimate_point, which reads prepared.covariates.
            covariates = [
                *prepared.covariates,
                CovariateSpec(column="__simulated_confounder__", kind=NUMERIC_KIND),
            ]
            truncation = (
                {
                    "lower": request.propensity_truncation.lower,
                    "upper": request.propensity_truncation.upper,
                }
                if request.propensity_truncation is not None
                else None
            )
            try:
                if spec.estimator == "regression_adjustment":
                    output = estimate_regression_adjustment(
                        frame, prepared.treatment, prepared.outcome,
                        covariates, prepared.missing_policy, prepared.outcome_task,
                    )
                elif spec.estimator == "ipw":
                    output = estimate_ipw(
                        frame, prepared.treatment, prepared.outcome,
                        covariates, prepared.missing_policy, truncation,
                    )
                else:
                    output = estimate_aipw(
                        frame, prepared.treatment, prepared.outcome,
                        covariates, prepared.missing_policy, prepared.outcome_task, request,
                    )
                row.append(float(output.estimate))
            except (EstimationFailure, ValueError) as error:
                row.append(None)
                cell_failures.append(
                    {
                        "gamma": gamma,
                        "kappa": kappa,
                        "reason": str(getattr(error, "message", error)),
                    }
                )
        cells.append(row)
    return {
        "experiment": "unmeasured_confounder_simulation",
        "parameters": {
            "estimator": spec.estimator,
            "prevalence": prevalence,
            "gamma_values": list(gammas),
            "kappa_values": list(kappas),
            "outcome_sd": outcome_sd,
        },
        "grid": cells,
        "failures": cell_failures,
        "warnings": [SENSITIVITY_CAVEAT],
        "method_note": (
            "For each (γ, κ) cell a binary confounder is simulated with "
            "logit P(U=1) = logit(prevalence) + γ·T + κ·(Y−mean(Y))/sd(Y), joined to the "
            "adjustment set as a numeric covariate, and the estimator is refitted. Cell (0, 0) "
            "is an independent noise draw of a treatment/outcome-orthogonal confounder and "
            "should sit close to the original estimate; movement across the grid describes the "
            "scenario's sensitivity, not a confidence statement."
        ),
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def run_robustness_experiment(
    dataset: Dataset,
    record: CausalGraphRecord,
    request: EstimationRequest,
    experiment: Literal["subsampling", "placebo", "unmeasured_confounder"],
    spec: ExperimentSpec,
) -> dict[str, Any]:
    """Run the gate, prepare the cohort, then run one robustness experiment."""
    if experiment not in ("subsampling", "placebo", "unmeasured_confounder"):
        raise ValidationFailure(
            f"Unknown robustness experiment '{experiment}'.",
            details={"supported": ["subsampling", "placebo", "unmeasured_confounder"]},
        )
    if isinstance(spec, SubsamplingSpec) and experiment != "subsampling":
        raise ValidationFailure("The provided specification does not match the experiment kind.")
    if isinstance(spec, PlaceboSpec) and experiment != "placebo":
        raise ValidationFailure("The provided specification does not match the experiment kind.")
    if isinstance(spec, ConfounderSpec) and experiment != "unmeasured_confounder":
        raise ValidationFailure("The provided specification does not match the experiment kind.")

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

    seed = request.uncertainty.seed
    if seed is None:
        seed = secrets.randbits(31)
        request = request.model_copy(deep=True)
        request.uncertainty.seed = seed

    estimator_name = (
        spec.estimator if isinstance(spec, (SubsamplingSpec, PlaceboSpec, ConfounderSpec)) else ""
    )
    try:
        original = _fit_named(
            estimator_name, prepared, request, prepared.frame, prepared.treatment, prepared.outcome
        )
        original_estimate: float | None = float(original.estimate)
    except (EstimationFailure, ValueError) as error:
        original_estimate = None
        original_failure = str(getattr(error, "message", error))
    else:
        original_failure = None

    if experiment == "subsampling":
        result = _subsampling(prepared, request, spec, seed)  # type: ignore[arg-type]
    elif experiment == "placebo":
        result = _placebo(prepared, request, spec, seed)  # type: ignore[arg-type]
    else:
        result = _sensitivity(prepared, request, spec, seed)  # type: ignore[arg-type]

    reproducibility = {
        **_reproducibility(dataset, record, request, seed, [estimator_name]),
        "experiment": {
            "kind": experiment,
            **result["parameters"],
        },
        "analysis_kind": "robustness",
    }

    return {
        "analysis_kind": "robustness",
        "estimation_version": ESTIMATION_VERSION,
        "robustness_schema_version": ROBUSTNESS_SCHEMA_VERSION,
        "estimand": request.estimand,
        "gate": gate,
        "analysis": {
            **prepared.to_payload(),
            "treatment_column": treatment_column,
            "outcome_column": outcome_column,
            "adjustment_columns": adjustment_columns,
        },
        "original": {
            "estimator": estimator_name,
            "estimate": original_estimate,
            "failure": original_failure,
            "note": (
                "The same estimator fitted once on the full analysis cohort, so every "
                "experiment value is comparable with it."
                if original_estimate is not None
                else "The estimator failed on the full cohort; no experiment is meaningful."
            ),
        },
        "result": result,
        "reproducibility": reproducibility,
        "scope_note": ROBUSTNESS_SCOPE_NOTE,
    }


__all__ = [
    "ROBUSTNESS_SCHEMA_VERSION",
    "ConfounderSpec",
    "PlaceboSpec",
    "RobustnessLimits",
    "SubsamplingSpec",
    "run_robustness_experiment",
]
