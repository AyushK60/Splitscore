"""Estimation service: the identification identification gate plus orchestration.

The gate is mandatory and never advisory. Before any number is computed the
service verifies, in order:

1. the stored graph's scientific fingerprint matches the client's expected
   fingerprint when one was supplied (a stale client is refused with 409, not
   silently estimated against);
2. the stored graph still validates against the dataset in memory;
3. the treatment/outcome/adjustment nodes exist, are declared observed, and
   are anchored to real dataset columns;
4. the requested adjustment set satisfies the classical backdoor criterion -
   verified by identification's own exact engine, never trusted from the client;
5. the treatment column admits exactly the two requested values and the
   outcome column parses numerically (enforced during preparation).

A failed gate produces no estimate. Estimation results are addressed to the
graph fingerprint and dataset fingerprint so a stored run can always be
re-checked for staleness later; a layout-only graph edit does not change the
fingerprint and therefore does not stale a result, while any structural edit
does.
"""

from __future__ import annotations

import platform
import secrets
from typing import Any

import numpy as np
import pandas as pd

from app.audit.dataset import Dataset
from app.causal.adjustment import evaluate_adjustment_set
from app.causal.estimation.contracts import (
    ESTIMATION_SCHEMA_VERSION,
    ESTIMATOR_NAMES,
    EstimationLimits,
    EstimationRequest,
    estimation_scope_note,
    payload_defaults_applied,
)
from app.causal.estimation.diagnostics import balance_payload, overlap_payload
from app.causal.estimation.estimators import (
    MISSING_CATEGORY,
    EstimationFailure,
    EstimatorOutput,
    estimate_aipw,
    estimate_ipw,
    estimate_regression_adjustment,
)
from app.causal.estimation.preparation import NUMERIC_KIND, PreparedData, prepare_cohort
from app.causal.estimation.uncertainty import (
    bootstrap_interval,
    influence_function_interval,
)
from app.causal.identification import build_dag, observed_node_ids
from app.causal.registry import CausalGraphRecord
from app.causal.validation import validate_spec
from app.core.errors import InfeasibleOperationError, ValidationFailure

#: Version of the estimation service contract, echoed in every payload.
ESTIMATION_VERSION = "1.0.0"

GATE_CAVEAT = (
    "The adjustment set was verified against the drawn graph only. Exchangeability, consistency, "
    "positivity and correct model specification remain assumptions the estimate depends on; none "
    "is proven by this run or its diagnostics."
)


# --------------------------------------------------------------------------- #
# Identification gate
# --------------------------------------------------------------------------- #


def _resolved_column(record: CausalGraphRecord, node_id: str, role: str) -> str:
    """Resolve one graph node to its anchored dataset column, strictly."""
    node = next((n for n in record.spec.nodes if n.node_id == node_id), None)
    if node is None:
        raise ValidationFailure(
            f"The {role} node '{node_id}' is not a node of this graph.",
            details={"node_id": node_id},
        )
    if node.is_unobserved:
        raise ValidationFailure(
            f"The {role} node '{node_id}' is declared unobserved; estimation cannot use it.",
            details={"node_id": node_id},
        )
    if not node.column:
        raise ValidationFailure(
            f"The {role} node '{node_id}' is not anchored to a dataset column, so no data "
            "could be read for it.",
            details={
                "node_id": node_id,
                "fix": "Anchor the node to a column in the Causal Lab, or choose a node "
                "backed by a measured column.",
            },
        )
    return node.column


def run_identification_gate(
    dataset: Dataset,
    record: CausalGraphRecord,
    request: EstimationRequest,
) -> dict[str, Any]:
    """Verify every precondition for estimation. Raises; returns the gate payload."""
    if (
        request.expected_spec_fingerprint_sha256
        and request.expected_spec_fingerprint_sha256 != record.fingerprint
    ):
        raise InfeasibleOperationError(
            "The graph's scientific fingerprint does not match the fingerprint this request "
            "was prepared against; the graph changed since the client last saw it.",
            details={
                "expected_spec_fingerprint_sha256": request.expected_spec_fingerprint_sha256,
                "current_spec_fingerprint_sha256": record.fingerprint,
                "fix": "Reload the graph (a layout drag never changes the fingerprint; a "
                "structural edit does) and resubmit.",
            },
        )

    result = validate_spec(
        record.spec,
        dataset_columns=list(dataset.columns),
        stored_dataset_fingerprint=record.dataset_fingerprint_sha256,
        current_dataset_fingerprint=dataset.fingerprint_sha256,
    )
    if not result.ok:
        raise ValidationFailure(
            "The stored causal graph no longer validates against the dataset in memory; "
            "estimation was refused.",
            details={**result.to_payload(), "fix": "Re-validate the graph in the Causal Lab."},
        )

    if request.treatment_node == request.outcome_node:
        raise ValidationFailure(
            "The treatment and outcome must be distinct nodes.",
            details={"treatment_node": request.treatment_node, "outcome_node": request.outcome_node},
        )

    treatment_column = _resolved_column(record, request.treatment_node, "treatment")
    outcome_column = _resolved_column(record, request.outcome_node, "outcome")
    adjustment_nodes: list[str] = []
    adjustment_columns: list[str] = []
    for node_id in request.adjustment_nodes:
        if node_id in (request.treatment_node, request.outcome_node):
            raise ValidationFailure(
                f"Adjustment node '{node_id}' is the treatment or outcome node; the backdoor "
                "criterion excludes both.",
                details={"node_id": node_id},
            )
        column = _resolved_column(record, node_id, "adjustment")
        if column in adjustment_columns:
            raise ValidationFailure(
                "Two adjustment nodes resolve to the same dataset column.",
                details={"column": column},
            )
        adjustment_nodes.append(node_id)
        adjustment_columns.append(column)

    # The identification verdict itself: the requested set must satisfy the classical
    # backdoor criterion on the stored graph. The client's claim is never used.
    dag = build_dag(record.spec)
    observed = observed_node_ids(record.spec)
    verdict = evaluate_adjustment_set(
        dag,
        request.treatment_node,
        request.outcome_node,
        list(request.adjustment_nodes),
        observed,
    )
    if not verdict.valid:
        raise ValidationFailure(
            "The requested adjustment set does not satisfy the classical backdoor criterion "
            "on the stored graph; estimation was refused.",
            details={
                "verification": verdict.to_payload(),
                "fix": "Use the Causal Lab's adjustment search to find a verified set, or "
                "edit the request. A forbidden post-treatment or unobserved variable can "
                "never enter the estimator.",
            },
        )

    missing_columns = [
        column
        for column in [treatment_column, outcome_column, *adjustment_columns]
        if column not in dataset.columns
    ]
    if missing_columns:
        raise ValidationFailure(
            "The graph anchors to columns that are not present in the dataset in memory.",
            details={"missing_columns": missing_columns},
        )

    return {
        "gate": "passed",
        "adjustment_set_verification": verdict.to_payload(),
        "treatment_node": request.treatment_node,
        "outcome_node": request.outcome_node,
        "adjustment_nodes": list(request.adjustment_nodes),
        "caveat": GATE_CAVEAT,
    }


# --------------------------------------------------------------------------- #
# Estimation orchestration
# --------------------------------------------------------------------------- #


def _estimate_point(
    estimator_name: str,
    prepared: PreparedData,
    request: EstimationRequest,
    frame: pd.DataFrame,
    treatment: np.ndarray,
    outcome: np.ndarray,
) -> EstimatorOutput:
    if estimator_name == "regression_adjustment":
        return estimate_regression_adjustment(
            frame, treatment, outcome, prepared.covariates, prepared.missing_policy, prepared.outcome_task
        )
    if estimator_name == "ipw":
        truncation = (
            {
                "lower": request.propensity_truncation.lower,
                "upper": request.propensity_truncation.upper,
            }
            if request.propensity_truncation is not None
            else None
        )
        return estimate_ipw(frame, treatment, outcome, prepared.covariates, prepared.missing_policy, truncation)
    if estimator_name == "aipw":
        return estimate_aipw(
            frame, treatment, outcome, prepared.covariates, prepared.missing_policy, prepared.outcome_task, request
        )
    raise ValidationFailure(
        f"Unknown estimator '{estimator_name}'.",
        details={"supported": list(ESTIMATOR_NAMES)},
    )


def _resampled_view(prepared: PreparedData, indices: np.ndarray):
    return (
        prepared.frame.iloc[indices].reset_index(drop=True),
        prepared.treatment[indices],
        prepared.outcome[indices],
    )


def _bootstrap_fn(
    estimator_name: str,
    prepared: PreparedData,
    request: EstimationRequest,
) -> Any:
    """A callable that re-runs the *whole* estimation procedure on a resample."""

    def run(indices: np.ndarray) -> float:
        frame, treatment, outcome = _resampled_view(prepared, indices)
        output = _estimate_point(estimator_name, prepared, request, frame, treatment, outcome)
        return output.estimate

    return run


def _units(outcome_task: str) -> str:
    return "probability_difference" if outcome_task == "logistic" else "outcome_units"


def _uncertainty_for(
    estimator_name: str,
    output: EstimatorOutput,
    prepared: PreparedData,
    request: EstimationRequest,
) -> Any:
    spec = request.uncertainty
    if spec.method == "influence_function":
        return influence_function_interval(output, spec.level)
    seed = spec.seed if spec.seed is not None else 0
    return bootstrap_interval(
        _bootstrap_fn(estimator_name, prepared, request),
        prepared.rows_final,
        level=spec.level,
        reps=spec.reps,
        seed=seed,
    )


def _diagnostic_frame(prepared: PreparedData) -> pd.DataFrame:
    """The frame balance diagnostics are computed on.

    Under ``median_mode`` the fitted pipelines impute inside their folds, but
    the prepared frame still carries raw NaNs - balance SMDs on raw NaNs would
    all report null even though the estimators used imputed values. This
    mirror-imputation (column medians for numeric, the explicit missing level
    for categorical) reproduces what the models saw, and the payload records
    that it was applied. Under ``complete_case`` the frame has no missing
    values and the frame is returned untouched.
    """
    if prepared.missing_policy != "median_mode":
        return prepared.frame
    frame = prepared.frame.copy()
    for spec in prepared.covariates:
        series = frame[spec.column]
        if spec.kind == NUMERIC_KIND:
            frame[spec.column] = series.fillna(series.median())
        else:
            frame[spec.column] = series.fillna(MISSING_CATEGORY)
    return frame


def _estimator_payload(
    estimator_name: str,
    output: EstimatorOutput,
    prepared: PreparedData,
    request: EstimationRequest,
    propensity: np.ndarray | None,
) -> dict[str, Any]:
    weights = None
    if propensity is not None:
        eps = np.finfo(float).eps
        weights = prepared.treatment / np.maximum(propensity, eps) + (1.0 - prepared.treatment) / np.maximum(
            1.0 - propensity, eps
        )
    diagnostic_frame = _diagnostic_frame(prepared)
    balance = balance_payload(diagnostic_frame, prepared.treatment, prepared.covariates, weights)
    if prepared.missing_policy == "median_mode":
        balance["diagnostic_imputation"] = (
            "Balance diagnostics are computed on median/mode-imputed covariate values, "
            "mirroring what the fitted models see; the missingness summary reports the "
            "raw missing counts."
        )
    overlap = (
        overlap_payload(
            propensity,
            prepared.treatment,
            prepared.outcome,
            weights,
            output.truncation,
        )
        if propensity is not None
        else None
    )
    uncertainty = _uncertainty_for(estimator_name, output, prepared, request)
    warnings = list(output.warnings)
    if output.influence is None and request.uncertainty.method == "influence_function":
        warnings.append(
            "Regression adjustment has no closed-form influence function in this implementation; "
            "request the refitting bootstrap for an interval."
        )
    return {
        **output.to_payload(),
        "estimate": output.estimate,
        "units": _units(prepared.outcome_task),
        "treated_mean": output.mu1,
        "control_mean": output.mu0,
        "sample_size": prepared.rows_final,
        "uncertainty": uncertainty.to_payload(),
        "diagnostics": {"balance": balance, "overlap": overlap},
        "warnings": warnings,
    }


def _versions() -> dict[str, str]:
    import sklearn
    import statsmodels

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "statsmodels": statsmodels.__version__,
    }


def _reproducibility(
    dataset: Dataset,
    record: CausalGraphRecord,
    request: EstimationRequest,
    seed: int,
    estimator_names: list[str],
) -> dict[str, Any]:
    return {
        "dataset_id": dataset.dataset_id,
        "dataset_fingerprint_sha256": dataset.fingerprint_sha256,
        "graph_id": record.graph_id,
        "graph_revision": record.revision,
        "graph_spec_fingerprint_sha256": record.fingerprint,
        "estimation_version": ESTIMATION_VERSION,
        "estimation_schema_version": ESTIMATION_SCHEMA_VERSION,
        "estimators": list(estimator_names),
        "treatment_node": request.treatment_node,
        "outcome_node": request.outcome_node,
        "adjustment_nodes": list(request.adjustment_nodes),
        "treatment_mapping": request.treatment_mapping.model_dump(),
        "cohort": request.cohort.model_dump(),
        "missing_data_policy": request.missing_data_policy,
        "cross_fitting": request.cross_fit.model_dump(),
        "uncertainty": {**request.uncertainty.model_dump(), "resolved_seed": seed},
        "propensity_truncation": (
            request.propensity_truncation.model_dump() if request.propensity_truncation else None
        ),
        "software_versions": _versions(),
        "limits": EstimationLimits.as_dict(),
    }


def run_estimation(
    dataset: Dataset,
    record: CausalGraphRecord,
    request: EstimationRequest,
    *,
    estimator_names: list[str],
    compare: bool = False,
) -> dict[str, Any]:
    """Run the gate, prepare the cohort, and estimate under one shared analysis."""
    for name in estimator_names:
        if name not in ESTIMATOR_NAMES:
            raise ValidationFailure(
                f"Unknown estimator '{name}'.",
                details={"supported": list(ESTIMATOR_NAMES)},
            )
    gate = run_identification_gate(dataset, record, request)
    treatment_column = _resolved_column(record, request.treatment_node, "treatment")
    outcome_column = _resolved_column(record, request.outcome_node, "outcome")
    adjustment_columns = [_resolved_column(record, node_id, "adjustment") for node_id in request.adjustment_nodes]

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
        # Thread the resolved seed back into the request so cross-fitting folds
        # and the bootstrap share one recorded source of randomness.
        request = request.model_copy(deep=True)
        request.uncertainty.seed = seed

    results = []
    for name in estimator_names:
        try:
            output = _estimate_point(
                name, prepared, request, prepared.frame, prepared.treatment, prepared.outcome
            )
        except EstimationFailure as error:
            results.append(
                {
                    "estimator": name,
                    "status": "failed",
                    "failure": {"reason": error.message, "details": error.details},
                }
            )
            continue
        except ValueError as error:
            # Degenerate numeric data can still surface as a library-level
            # ValueError after the structured guards above (scikit-learn
            # raises ValueError for unsolvable fits). A data-driven failure
            # is reported per-estimator; it is never a 500.
            results.append(
                {
                    "estimator": name,
                    "status": "failed",
                    "failure": {
                        "reason": (
                            "The estimator could not be fitted on this data: "
                            f"{error}"
                        ),
                        "details": {"library_error": type(error).__name__},
                    },
                }
            )
            continue
        propensity = output.propensity
        results.append(
            {
                "status": "estimated",
                **_estimator_payload(name, output, prepared, request, propensity),
            }
        )

    payload: dict[str, Any] = {
        "estimation_version": ESTIMATION_VERSION,
        "estimation_schema_version": ESTIMATION_SCHEMA_VERSION,
        "estimand": request.estimand,
        "gate": gate,
        "analysis": {
            **prepared.to_payload(),
            "treatment_column": treatment_column,
            "outcome_column": outcome_column,
            "adjustment_columns": adjustment_columns,
            "outcome_units_note": (
                "The outcome was detected as binary; every estimate is a difference in "
                "probabilities for the coded-1 outcome value."
                if prepared.outcome_task == "logistic"
                else "The outcome was treated as continuous; estimates are in the outcome's units."
            ),
        },
        "results": results,
        "defaults_applied": payload_defaults_applied(request),
        "reproducibility": _reproducibility(dataset, record, request, seed, estimator_names),
        "scope_note": estimation_scope_note(),
    }
    if compare:
        payload["comparison"] = _comparison_summary(results)
    return payload


def _comparison_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Structured comparison across estimators on one identical analysis."""
    estimates = {
        result["estimator"]: result["estimate"]
        for result in results
        if result.get("status") == "estimated"
    }
    summary: dict[str, Any] = {
        "shared_analysis": (
            "All results below were computed on the same prepared cohort, treatment mapping, "
            "adjustment set and estimand; they differ only in the estimator."
        ),
        "estimates": estimates,
    }
    if len(estimates) >= 2:
        values = list(estimates.values())
        summary["max_pairwise_difference"] = float(max(values) - min(values))
        summary["interpretation"] = (
            "Material disagreement between estimators that share a cohort and adjustment set "
            "is a model-specification or instability signal (nuisance misspecification, weak "
            "overlap, small-sample noise). It is reported, not resolved: SplitScope does not "
            "select a winner and does not combine estimators into a single score."
        )
    else:
        summary["interpretation"] = (
            "Fewer than two estimators produced an estimate, so no comparison is reported."
        )
    return summary


# --------------------------------------------------------------------------- #
# Staleness for stored runs
# --------------------------------------------------------------------------- #


def mark_staleness(payload: dict[str, Any], dataset: Dataset, record: CausalGraphRecord) -> dict[str, Any]:
    """Re-check a stored run against the current dataset and graph fingerprints.

    A run is stale when either fingerprint changed. Node layout, labels and
    prose never change the scientific fingerprint, so rearranging the canvas
    does not invalidate a causal estimate - exactly the graph rule.
    """
    repro = payload.get("reproducibility", {})
    stale = (
        repro.get("dataset_fingerprint_sha256") != dataset.fingerprint_sha256
        or repro.get("graph_spec_fingerprint_sha256") != record.fingerprint
    )
    annotated = dict(payload)
    annotated["stale"] = stale
    if stale:
        annotated["staleness_reason"] = (
            "The dataset or the graph's scientific content changed after this result was "
            "computed. The numbers describe the earlier data/graph pair."
        )
    return annotated


__all__ = [
    "ESTIMATION_VERSION",
    "GATE_CAVEAT",
    "mark_staleness",
    "run_estimation",
    "run_identification_gate",
]
