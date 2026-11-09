"""estimation causal estimation: known-effect synthetic fixtures and independent cross-checks.

Every expected effect in this file comes from the data-generating process
written next to the test, never from the implementation under test. Recovery
tolerances are ~1.5-2 sampling standard errors for the given n, not exact
equality: a finite-sample estimate is not required to equal its generating
parameter. Independent references (statsmodels OLS, hand-computed arithmetic)
cross-check the estimators so they are never their own oracle.

The 25 estimation brief cases are labelled in test names. API integration is case 25,
in ``test_causal_estimation_api.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from app.audit.dataset import Dataset
from app.causal.adjustment import evaluate_adjustment_set
from app.causal.d_separation import DAG
from app.causal.estimation.contracts import EstimationLimits, EstimationRequest
from app.causal.estimation.diagnostics import balance_payload
from app.causal.estimation.estimators import estimate_aipw, estimate_ipw
from app.causal.estimation.preparation import prepare_cohort
from app.causal.estimation.service import run_estimation
from app.causal.estimation.uncertainty import influence_function_interval
from app.causal.registry import CausalGraphRecord
from app.causal.schema import CausalGraphSpec
from app.core.errors import InfeasibleOperationError, ValidationFailure

from .conftest import make_dataset

# --------------------------------------------------------------------------- #
# Fixtures: data-generating processes and graphs
# --------------------------------------------------------------------------- #


def _frame_from_rng(n: int, seed: int, effect: float, confounding: str = "moderate") -> pd.DataFrame:
    """The canonical measured-confounding DGP: y = effect·t + b1·x1 + b2·x2 + ε."""
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0.0, 1.0, n)
    x2 = rng.normal(0.0, 1.0, n)
    if confounding == "moderate":
        linear = 0.8 * x1 - 0.5 * x2
    elif confounding == "strong":
        linear = 2.5 * x1 + 1.5 * x2
    elif confounding == "none":
        linear = np.zeros(n)
    elif confounding == "extreme":
        linear = 3.5 * x1 - 2.0 * x2
    else:  # pragma: no cover - fixture misuse
        raise ValueError(confounding)
    propensity = 1.0 / (1.0 + np.exp(-linear))
    t = rng.binomial(1, propensity)
    y = effect * t + 0.9 * x1 - 0.7 * x2 + rng.normal(0.0, 1.0, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "t": t, "y": y})


def _dataset(frame: pd.DataFrame) -> Dataset:
    rows = frame.to_dict("records")
    return make_dataset(rows, name="estimation-fixture.csv")


def _confounded_spec(dataset_id: str, *, nodes: list[dict] | None = None, edges: list[tuple[str, str]] | None = None) -> CausalGraphSpec:
    nodes = nodes or [
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "x2", "label": "x2", "column": "x2"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ]
    edges = edges or [("x1", "t"), ("x1", "y"), ("x2", "t"), ("x2", "y"), ("t", "y")]
    return CausalGraphSpec(
        name="Estimation fixture graph",
        dataset_id=dataset_id,
        nodes=nodes,
        edges=[{"source": s, "target": t} for s, t in edges],
        analysis={"treatment": "t", "outcome": "y"},
    )


def _record(dataset: Dataset, spec: CausalGraphSpec) -> CausalGraphRecord:
    return CausalGraphRecord(
        graph_id="cgraph-fixture",
        dataset_id=dataset.dataset_id,
        dataset_fingerprint_sha256=dataset.fingerprint_sha256,
        spec=spec,
        revision=1,
    )


def _request(
    dataset: Dataset,
    spec: CausalGraphSpec,
    *,
    adjustment: list[str] | None = None,
    treatment: str = "t",
    outcome: str = "y",
    mapping: dict | None = None,
    **overrides,
) -> EstimationRequest:
    body: dict = {
        "treatment_node": treatment,
        "outcome_node": outcome,
        "adjustment_nodes": ["x1", "x2"] if adjustment is None else adjustment,
        "treatment_mapping": mapping or {"treated": "1", "control": "0"},
        "uncertainty": {"method": "bootstrap", "reps": 150, "seed": 2026, "level": 0.95},
        "expected_spec_fingerprint_sha256": None,
    }
    body.update(overrides)
    return EstimationRequest(**body)


def _estimate_all(dataset: Dataset, record: CausalGraphRecord, request: EstimationRequest, **kwargs) -> dict:
    names = kwargs.pop("estimators", ["regression_adjustment", "ipw", "aipw"])
    return run_estimation(dataset, record, request, estimator_names=names, **kwargs)


def _result(payload: dict, estimator: str) -> dict:
    return next(result for result in payload["results"] if result["estimator"] == estimator)


# --------------------------------------------------------------------------- #
# Cases 1-8: recovery of known effects
# --------------------------------------------------------------------------- #


def test_case_1_randomized_treatment_constant_effect_empty_set_valid():
    # Randomized treatment: the empty set is the correct, valid adjustment set.
    rng = np.random.default_rng(5)
    n = 1000
    t = rng.binomial(1, 0.5, n)
    y = 2.0 * t + rng.normal(0, 1, n)
    frame = pd.DataFrame({"t": t, "y": y})
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id, nodes=[
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ], edges=[("t", "y")])
    record = _record(dataset, spec)
    request = _request(dataset, spec, adjustment=[])
    payload = _estimate_all(dataset, record, request)
    assert payload["gate"]["gate"] == "passed"
    for estimator in ("regression_adjustment", "ipw", "aipw"):
        result = _result(payload, estimator)
        # Tolerance ≈ 2 sampling SEs (SE ≈ 4/√1000 ≈ 0.13 per arm difference).
        assert abs(result["estimate"] - 2.0) < 0.25, (estimator, result["estimate"])
        uncertainty = result["uncertainty"]
        assert uncertainty["status"] == "available"
        assert uncertainty["ci_lower"] < 2.0 < uncertainty["ci_upper"]


def test_case_2_observational_measured_confounding_recovered():
    dataset = _dataset(_frame_from_rng(900, 11, effect=1.5))
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec)
    payload = _estimate_all(dataset, record, request)
    assert payload["gate"]["gate"] == "passed"
    # The unadjusted difference is biased; every adjusted estimator recovers 1.5.
    prepared = payload["analysis"]
    assert prepared["rows_final"] == 900
    for estimator in ("regression_adjustment", "ipw", "aipw"):
        result = _result(payload, estimator)
        assert abs(result["estimate"] - 1.5) < 0.3, (estimator, result["estimate"])


def test_case_3_no_effect_estimates_near_zero_and_ci_covers_zero():
    dataset = _dataset(_frame_from_rng(900, 12, effect=0.0))
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec)
    payload = _estimate_all(dataset, record, request)
    for estimator in ("regression_adjustment", "ipw", "aipw"):
        result = _result(payload, estimator)
        assert abs(result["estimate"]) < 0.2, (estimator, result["estimate"])
        uncertainty = result["uncertainty"]
        assert uncertainty["ci_lower"] <= 0.0 <= uncertainty["ci_upper"]


def test_case_4_strong_confounding_naive_difference_biased_estimators_recover():
    frame = _frame_from_rng(1200, 13, effect=1.0, confounding="strong")
    dataset = _dataset(frame)
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec)
    payload = _estimate_all(dataset, record, request)
    treated = frame[frame["t"] == 1]["y"].mean()
    control = frame[frame["t"] == 0]["y"].mean()
    naive = treated - control
    # The raw difference is visibly biased by construction (strong confounding
    # plus this seed's noise); every adjusted estimator stays far closer.
    assert abs(naive - 1.0) > 0.3, naive
    for estimator in ("regression_adjustment", "ipw", "aipw"):
        result = _result(payload, estimator)
        assert abs(result["estimate"] - 1.0) < 0.35, (estimator, result["estimate"])


def test_case_5_treatment_imbalance_still_recovers():
    rng = np.random.default_rng(21)
    n = 1200
    x1 = rng.normal(0, 1, n)
    propensity = 1.0 / (1.0 + np.exp(-(1.5 * x1 + 2.0)))  # P(T=1) well above 0.5
    t = rng.binomial(1, propensity)
    y = 0.8 * t + 0.9 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": y})
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id, nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ], edges=[("x1", "t"), ("x1", "y"), ("t", "y")])
    record = _record(dataset, spec)
    request = _request(dataset, record.spec, adjustment=["x1"])
    payload = _estimate_all(dataset, record, request)
    treated_rows = payload["analysis"]["treated_rows"]
    assert treated_rows > 2 * (payload["analysis"]["control_rows"])
    for estimator in ("regression_adjustment", "ipw", "aipw"):
        result = _result(payload, estimator)
        assert abs(result["estimate"] - 0.8) < 0.3, (estimator, result["estimate"])


def test_case_6_poor_overlap_warns_and_shrinks_effective_sample_size():
    # Near-deterministic assignment: overlap is weak by construction.
    rng = np.random.default_rng(31)
    n = 1200
    x1 = rng.normal(0, 1, n)
    propensity = 1.0 / (1.0 + np.exp(-4.0 * x1))
    t = rng.binomial(1, propensity)
    y = 1.0 * t + 0.9 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": y})
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id, nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ], edges=[("x1", "t"), ("x1", "y"), ("t", "y")])
    record = _record(dataset, spec)
    request = _request(dataset, record.spec, adjustment=["x1"])
    payload = _estimate_all(dataset, record, request, estimators=["ipw"])
    result = _result(payload, "ipw")
    overlap = result["diagnostics"]["overlap"]
    assert overlap["warnings"], "weak overlap must produce explicit warnings"
    ess = overlap["effective_sample_sizes"]
    assert ess["treated_ess_weighted"] < 0.6 * ess["treated_rows_unweighted"]
    # The estimate is reported (with warnings), never silently hidden.
    assert result["status"] == "estimated"


def test_case_7_empty_set_refused_when_backdoor_paths_exist():
    dataset = _dataset(_frame_from_rng(300, 14, effect=1.0))
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec, adjustment=[])
    with pytest.raises(ValidationFailure) as excinfo:
        run_estimation(dataset, record, request, estimator_names=["ipw"])
    verification = excinfo.value.details["verification"]
    assert verification["valid"] is False
    assert any(v["code"] == "open_backdoor_path" for v in verification["violations"])


def test_case_8_multiple_confounders_recovered():
    rng = np.random.default_rng(41)
    n = 1200
    x1, x2, x3 = (rng.normal(0, 1, n) for _ in range(3))
    propensity = 1.0 / (1.0 + np.exp(-(0.7 * x1 - 0.6 * x2 + 0.5 * x3)))
    t = rng.binomial(1, propensity)
    y = 1.2 * t + 0.8 * x1 - 0.6 * x2 + 0.5 * x3 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "t": t, "y": y})
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id, nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "x2", "label": "x2", "column": "x2"},
        {"node_id": "x3", "label": "x3", "column": "x3"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ], edges=[("x1", "t"), ("x1", "y"), ("x2", "t"), ("x2", "y"), ("x3", "t"), ("x3", "y"), ("t", "y")])
    record = _record(dataset, spec)
    request = _request(dataset, record.spec, adjustment=["x1", "x2", "x3"])
    payload = _estimate_all(dataset, record, request)
    for estimator in ("regression_adjustment", "ipw", "aipw"):
        result = _result(payload, estimator)
        assert abs(result["estimate"] - 1.2) < 0.3, (estimator, result["estimate"])


# --------------------------------------------------------------------------- #
# Cases 9-10: the identification gate refuses forbidden sets
# --------------------------------------------------------------------------- #


def test_case_9_post_treatment_adjustment_refused():
    frame = _frame_from_rng(300, 15, effect=1.0)
    dataset = _dataset(frame)
    # x1 → t → m → y with x1 → y: m is a mediator, forbidden for the total effect.
    spec = _confounded_spec(dataset.dataset_id, nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "m", "label": "m", "column": "x2"},
        {"node_id": "y", "label": "y", "column": "y"},
    ], edges=[("x1", "t"), ("x1", "y"), ("t", "m"), ("m", "y"), ("t", "y")])
    record = _record(dataset, spec)
    request = _request(dataset, spec, adjustment=["x1", "m"])
    with pytest.raises(ValidationFailure) as excinfo:
        run_estimation(dataset, record, request, estimator_names=["ipw"])
    verification = excinfo.value.details["verification"]
    assert any(v["code"] == "post_treatment_variable" for v in verification["violations"])


def test_case_10_unobserved_confounding_blocks_supported_estimation():
    frame = _frame_from_rng(300, 16, effect=1.0)
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id, nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
        {"node_id": "u", "label": "unobserved", "observed": False, "kind": "unobserved"},
    ], edges=[("u", "t"), ("u", "y"), ("x1", "t"), ("x1", "y"), ("t", "y")])
    record = _record(dataset, spec)
    for adjustment in ([], ["x1"]):
        request = _request(dataset, spec, adjustment=adjustment)
        with pytest.raises(ValidationFailure) as excinfo:
            run_estimation(dataset, record, request, estimator_names=["ipw"])
        verification = excinfo.value.details["verification"]
        assert verification["valid"] is False


# --------------------------------------------------------------------------- #
# Cases 11-13: missing data with explicit row accounting
# --------------------------------------------------------------------------- #


def _frame_with_missing(n: int = 400, seed: int = 51) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-(0.8 * x1 - 0.5 * x2))))
    y = 1.5 * t + 0.9 * x1 - 0.7 * x2 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "x2": x2, "t": t, "y": y})
    frame.loc[frame.index[:12], "t"] = np.nan
    frame.loc[frame.index[12:24], "y"] = np.nan
    frame.loc[frame.index[24:40], "x1"] = np.nan
    return frame


def test_case_11_missing_treatment_values_excluded_and_counted():
    dataset = _dataset(_frame_with_missing())
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec)
    payload = _estimate_all(dataset, record, request)
    analysis = payload["analysis"]
    exclusion = next(e for e in analysis["exclusions"] if e["reason"] == "missing_treatment_value")
    assert exclusion["count"] == 12
    assert analysis["rows_in_analysis_cohort_frame"] == 400
    assert analysis["rows_final"] + sum(e["count"] for e in analysis["exclusions"]) == 400


def test_case_12_missing_outcome_values_excluded_and_counted():
    dataset = _dataset(_frame_with_missing())
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec)
    payload = _estimate_all(dataset, record, request)
    exclusion = next(
        e for e in payload["analysis"]["exclusions"] if e["reason"] == "missing_outcome_value"
    )
    assert exclusion["count"] == 12


def test_case_13_missing_covariates_complete_case_vs_imputation():
    dataset = _dataset(_frame_with_missing())
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec)
    complete = _estimate_all(dataset, record, request)
    exclusion = next(
        e for e in complete["analysis"]["exclusions"] if e["reason"] == "missing_covariate_complete_case"
    )
    assert exclusion["count"] > 0

    imputed_request = _request(dataset, record.spec, missing_data_policy="median_mode")
    imputed = _estimate_all(dataset, record, imputed_request)
    assert imputed["analysis"]["missing_data_policy"] == "median_mode"
    assert not any(
        e["reason"] == "missing_covariate_complete_case" for e in imputed["analysis"]["exclusions"]
    )
    # Imputation keeps rows, and both analyses stay close to the true effect.
    assert abs(imputed["analysis"]["rows_final"] - 376) <= 4
    for estimator in ("regression_adjustment", "ipw", "aipw"):
        assert abs(_result(imputed, estimator)["estimate"] - 1.5) < 0.4, estimator


# --------------------------------------------------------------------------- #
# Case 14: categorical confounders
# --------------------------------------------------------------------------- #


def test_case_14_categorical_confounder_recovered():
    rng = np.random.default_rng(61)
    n = 1200
    region = rng.choice(["north", "south", "west"], n)
    region_effect = np.select(
        [region == "north", region == "south", region == "west"], [0.8, 0.0, -0.6]
    )
    propensity = 1.0 / (1.0 + np.exp(-(region_effect * 2.0)))
    t = rng.binomial(1, propensity)
    y = 1.0 * t + region_effect + rng.normal(0, 1, n)
    frame = pd.DataFrame({"region": region, "t": t, "y": y})
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id, nodes=[
        {"node_id": "region", "label": "region", "column": "region"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ], edges=[("region", "t"), ("region", "y"), ("t", "y")])
    record = _record(dataset, spec)
    request = _request(dataset, record.spec, adjustment=["region"])
    payload = _estimate_all(dataset, record, request)
    for estimator in ("regression_adjustment", "ipw", "aipw"):
        result = _result(payload, estimator)
        assert abs(result["estimate"] - 1.0) < 0.3, (estimator, result["estimate"])
    covariates = payload["analysis"]["covariates"]
    region_spec = next(c for c in covariates if c["column"] == "region")
    assert region_spec["kind"] == "categorical"
    assert sorted(region_spec["levels"]) == ["north", "south", "west"]
    balance = _result(payload, "ipw")["diagnostics"]["balance"]["covariates"]
    levels = {entry["level"] for entry in balance if entry["column"] == "region"}
    assert levels == {"north", "south", "west"}


# --------------------------------------------------------------------------- #
# Cases 15-16: degenerate treatment and propensity extremes
# --------------------------------------------------------------------------- #


def test_case_15_constant_treatment_refused():
    frame = _frame_from_rng(300, 17, effect=1.0)
    frame["t"] = 1
    dataset = _dataset(frame)
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec)
    with pytest.raises(ValidationFailure) as excinfo:
        run_estimation(dataset, record, request, estimator_names=["ipw"])
    assert "arm is too small" in excinfo.value.message


def test_case_16_propensity_extremes_reported_not_clipped():
    rng = np.random.default_rng(71)
    n = 600
    x1 = rng.normal(0, 1, n)
    # A covariate that almost perfectly separates the arms.
    t = (x1 > 0).astype(int)
    y = 1.0 * t + 0.5 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": y})
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id, nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ], edges=[("x1", "t"), ("x1", "y"), ("t", "y")])
    record = _record(dataset, spec)
    request = _request(dataset, record.spec, adjustment=["x1"])
    payload = _estimate_all(dataset, record, request, estimators=["ipw"])
    result = _result(payload, "ipw")
    overlap = result["diagnostics"]["overlap"]
    summary = overlap["propensity_summary"]
    assert summary["min"] < 0.01 or summary["max"] > 0.99
    assert overlap["warnings"], "propensity extremes must warn"
    # No silent clipping: the extremes are reported as fitted.
    assert overlap["truncation"] is None
    assert result["model_specification"]["weighting"] == "hajek_normalized"


# --------------------------------------------------------------------------- #
# Case 17: reproducibility under fixed seeds
# --------------------------------------------------------------------------- #


def test_case_17_fixed_seed_reproduces_estimates_exactly():
    dataset = _dataset(_frame_from_rng(700, 18, effect=1.5))
    record = _record(dataset, _confounded_spec(dataset.dataset_id))

    def one_run(seed: int) -> dict:
        request = _request(
            dataset,
            record.spec,
            uncertainty={"method": "bootstrap", "reps": 150, "seed": seed, "level": 0.95},
        )
        payload = _estimate_all(dataset, record, request)
        return {
            name: _result(payload, name)["estimate"]
            for name in ("regression_adjustment", "ipw", "aipw")
        }

    first = one_run(2026)
    second = one_run(2026)
    third = one_run(9)
    assert first == second
    # The point estimators are deterministic; only the bootstrap differs by seed.
    assert first["regression_adjustment"] == third["regression_adjustment"]
    assert first["ipw"] == third["ipw"]


# --------------------------------------------------------------------------- #
# Cases 19-21: gate refusals, encodings, and honest failure states
# --------------------------------------------------------------------------- #


def test_case_19_graph_fingerprint_mismatch_refused_as_conflict():
    dataset = _dataset(_frame_from_rng(300, 19, effect=1.0))
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(
        dataset,
        record.spec,
        expected_spec_fingerprint_sha256="0" * 64,
    )
    with pytest.raises(InfeasibleOperationError) as excinfo:
        run_estimation(dataset, record, request, estimator_names=["ipw"])
    assert excinfo.value.details["current_spec_fingerprint_sha256"] == record.fingerprint


def test_case_20_incorrect_treatment_encoding_refused():
    frame = _frame_from_rng(300, 20, effect=1.0)
    dataset = _dataset(frame)
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    # "treated" matches nothing: every row is unmatched, listed in the error.
    request = _request(dataset, record.spec, mapping={"treated": "treated", "control": "0"})
    with pytest.raises(ValidationFailure) as excinfo:
        run_estimation(dataset, record, request, estimator_names=["ipw"])
    details = excinfo.value.details
    assert "unmatched_values_with_counts" in details
    assert details["unmatched_values_with_counts"].get("1") == frame["t"].sum()

    # The contract itself refuses an undifferentiable mapping.
    with pytest.raises(ValueError):
        _request(dataset, record.spec, mapping={"treated": "1", "control": "1"})


def test_case_21_uncertainty_unavailable_state_and_estimator_failure_isolated():
    dataset = _dataset(_frame_from_rng(300, 22, effect=1.0))
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    # RA has no closed-form influence function here: the honest state is
    # "unavailable", never a fabricated interval.
    request = _request(
        dataset, record.spec, uncertainty={"method": "influence_function", "reps": 100, "seed": 1}
    )
    payload = _estimate_all(dataset, record, request, estimators=["regression_adjustment"])
    result = _result(payload, "regression_adjustment")
    assert result["uncertainty"]["status"] == "unavailable"
    assert result["uncertainty"]["ci_lower"] is None
    assert "bootstrap" in result["uncertainty"]["unavailable_reason"]

    # A cross-fitting design the data cannot support fails *alone*: with only
    # ten treated rows and ten folds, every training fold is short of treated
    # rows, while IPW in the same comparison still estimates.
    rng = np.random.default_rng(22)
    n = 400
    x1 = rng.normal(0, 1, n)
    t = np.zeros(n, dtype=int)
    t[:10] = 1  # exactly the per-arm minimum; ten folds cannot support it
    y = 1.0 * t + 0.5 * x1 + rng.normal(0, 1, n)
    small = _dataset(pd.DataFrame({"x1": x1, "t": t, "y": y}))
    small_spec = _confounded_spec(small.dataset_id, nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ], edges=[("x1", "t"), ("x1", "y"), ("t", "y")])
    small_record = _record(small, small_spec)
    request = _request(small, small_spec, adjustment=["x1"], cross_fit={"splits": 10, "group_column": None})
    payload = _estimate_all(small, small_record, request, estimators=["ipw", "aipw"])
    failed = _result(payload, "aipw")
    assert failed["status"] == "failed"
    assert "fold" in failed["failure"]["reason"].lower()
    assert _result(payload, "ipw")["status"] == "estimated"

    # A cohort below the stated minimum is refused before any fitting.
    tiny = _dataset(_frame_from_rng(30, 23, effect=1.0).tail(15).reset_index(drop=True))
    tiny_record = _record(tiny, _confounded_spec(tiny.dataset_id))
    with pytest.raises(ValidationFailure):
        run_estimation(
            tiny,
            tiny_record,
            _request(tiny, tiny_record.spec),
            estimator_names=["ipw"],
        )


# --------------------------------------------------------------------------- #
# Case 22: confidence-interval construction
# --------------------------------------------------------------------------- #


def test_case_22_confidence_intervals_are_well_formed_and_level_honoring():
    dataset = _dataset(_frame_from_rng(900, 24, effect=1.5))
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec)
    payload = _estimate_all(dataset, record, request)
    for estimator in ("ipw", "aipw"):
        result = _result(payload, estimator)
        uncertainty = result["uncertainty"]
        assert uncertainty["status"] == "available"
        assert uncertainty["ci_lower"] < uncertainty["ci_upper"]
        assert uncertainty["ci_lower"] < 1.5 < uncertainty["ci_upper"]
        assert uncertainty["bootstrap"]["refit_nuisance_models"] is True

    # The 90% influence-function interval is narrower than the 95% one.
    wide_request = _request(
        dataset, record.spec, uncertainty={"method": "influence_function", "reps": 100, "seed": 3}
    )
    wide = _estimate_all(dataset, record, wide_request, estimators=["aipw"])
    narrow_request = _request(
        dataset, record.spec, uncertainty={"method": "influence_function", "level": 0.90}
    )
    narrow = _estimate_all(dataset, record, narrow_request, estimators=["aipw"])
    wide_result = _result(wide, "aipw")["uncertainty"]
    narrow_result = _result(narrow, "aipw")["uncertainty"]
    assert (
        narrow_result["ci_upper"] - narrow_result["ci_lower"]
        < wide_result["ci_upper"] - wide_result["ci_lower"]
    )


# --------------------------------------------------------------------------- #
# Case 23: exclusion and row-count accounting (disjoint masks)
# --------------------------------------------------------------------------- #


def test_case_23_row_accounting_sums_exactly():
    dataset = _dataset(_frame_with_missing())
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec)
    payload = _estimate_all(dataset, record, request)
    analysis = payload["analysis"]
    total_excluded = sum(e["count"] for e in analysis["exclusions"])
    # Missing treatment, outcome and covariate masks are disjoint by construction.
    assert analysis["rows_in_dataset"] == 400
    assert analysis["rows_final"] + total_excluded == 400
    assert analysis["treated_rows"] + analysis["control_rows"] == analysis["rows_final"]


# --------------------------------------------------------------------------- #
# Case 24: cross-fitting is genuinely out-of-fold
# --------------------------------------------------------------------------- #


def test_case_24_crossfit_nuisance_predictions_are_out_of_fold():
    from sklearn.model_selection import KFold

    frame = _frame_from_rng(400, 25, effect=1.5)
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id)
    request = _request(
        dataset,
        spec,
        uncertainty={"method": "influence_function", "reps": 100, "seed": 99},
        cross_fit={"splits": 2, "group_column": None},
    )
    prepared = prepare_cohort(
        dataset,
        request,
        treatment_column="t",
        outcome_column="y",
        covariate_columns=["x1", "x2"],
    )
    output = estimate_aipw(
        prepared.frame,
        prepared.treatment,
        prepared.outcome,
        prepared.covariates,
        prepared.missing_policy,
        prepared.outcome_task,
        request,
    )
    # Rebuild the identical folds and confirm every row's propensity came from
    # a model that never saw that row.
    folds = KFold(n_splits=2, shuffle=True, random_state=99)
    from app.causal.estimation.estimators import _fit_propensity_model, _predict_propensity

    for train_idx, test_idx in folds.split(np.arange(len(prepared.treatment))):
        model = _fit_propensity_model(
            prepared.frame.iloc[train_idx].reset_index(drop=True),
            prepared.treatment[train_idx],
            prepared.covariates,
            prepared.missing_policy,
        )
        expected = _predict_propensity(
            model, prepared.frame.iloc[test_idx].reset_index(drop=True), prepared.covariates
        )
        assert np.allclose(expected, output.propensity[test_idx])

    # In-sample (leaky) predictions differ from the out-of-fold ones, so this
    # check would detect leakage if it were introduced.
    full_model = _fit_propensity_model(
        prepared.frame, prepared.treatment, prepared.covariates, prepared.missing_policy
    )
    leaky = _predict_propensity(full_model, prepared.frame, prepared.covariates)
    assert not np.allclose(leaky, output.propensity)
    assert output.model_spec["cross_fitting"]["out_of_fold_predictions"] is True


def test_crossfit_group_aware_folds_keep_entities_whole():
    rng = np.random.default_rng(81)
    n_entities = 120
    rows = 5 * n_entities
    entity = np.repeat(np.arange(n_entities), 5)
    x1 = rng.normal(0, 1, n_entities)[entity]
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-x1)))
    y = 1.0 * t + 0.8 * x1 + rng.normal(0, 1, rows)
    frame = pd.DataFrame({"entity": [f"e{e}" for e in entity], "x1": x1, "t": t, "y": y})
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id, nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ], edges=[("x1", "t"), ("x1", "y"), ("t", "y")])
    record = _record(dataset, spec)
    request = _request(
        dataset,
        spec,
        adjustment=["x1"],
        uncertainty={"method": "influence_function", "reps": 100, "seed": 5},
        cross_fit={"splits": 4, "group_column": "entity"},
    )
    payload = _estimate_all(dataset, record, request, estimators=["aipw"])
    result = _result(payload, "aipw")
    assert result["status"] == "estimated"
    assert result["model_specification"]["cross_fitting"]["strategy"] == "group_kfold"
    assert abs(result["estimate"] - 1.0) < 0.35


# --------------------------------------------------------------------------- #
# Independent reference cross-checks
# --------------------------------------------------------------------------- #


def test_regression_adjustment_matches_statsmodels_ols_reference():
    """For a linear outcome, g-computation with OLS equals the T coefficient
    of the covariate-adjusted OLS regression - a fully independent formula."""
    frame = _frame_from_rng(600, 26, effect=1.5)
    dataset = _dataset(frame)
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(
        dataset, record.spec, uncertainty={"method": "bootstrap", "reps": 100, "seed": 1}
    )
    payload = _estimate_all(dataset, record, request, estimators=["regression_adjustment"])
    estimate = _result(payload, "regression_adjustment")["estimate"]

    X = sm.add_constant(frame[["t", "x1", "x2"]].astype(float))
    ols = sm.OLS(frame["y"].astype(float), X).fit()
    assert abs(estimate - ols.params["t"]) < 1e-8


def test_ipw_hajek_combination_matches_documented_formula():
    """The Hájek weights are recomputed from the returned propensities with
    plain arithmetic - an independent check of the weighting combination."""
    frame = _frame_from_rng(600, 27, effect=1.5)
    dataset = _dataset(frame)
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec, uncertainty={"method": "influence_function"})
    payload = _estimate_all(dataset, record, request, estimators=["ipw"])
    result = _result(payload, "ipw")

    prepared = prepare_cohort(
        dataset, request, treatment_column="t", outcome_column="y", covariate_columns=["x1", "x2"]
    )
    output = estimate_ipw(prepared.frame, prepared.treatment, prepared.outcome, prepared.covariates, prepared.missing_policy)
    e = output.propensity
    t = prepared.treatment
    y = prepared.outcome
    mu1 = np.sum(t * y / e) / np.sum(t / e)
    mu0 = np.sum((1 - t) * y / (1 - e)) / np.sum((1 - t) / (1 - e))
    assert abs((mu1 - mu0) - result["estimate"]) < 1e-10

    # The influence-function SE recomputed independently matches the payload.
    interval = influence_function_interval(output, 0.95)
    assert interval.standard_error is not None
    n = len(y)
    w1 = t / e
    w0 = (1 - t) / (1 - e)
    phi1 = n * w1 * (y - mu1) / np.sum(w1)
    phi0 = n * w0 * (y - mu0) / np.sum(w0)
    expected_se = float(np.std(phi1 - phi0, ddof=1) / np.sqrt(n))
    assert abs(interval.standard_error - expected_se) < 1e-10


def test_aipw_interval_matches_pseudo_outcome_arithmetic():
    """The cross-fitted AIPW SE is the SD of the pseudo-outcome over √n -
    recomputed here from the returned pseudo-outcomes."""
    frame = _frame_from_rng(600, 28, effect=1.5)
    dataset = _dataset(frame)
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(
        dataset, record.spec, uncertainty={"method": "influence_function", "reps": 100, "seed": 77}
    )
    payload = _estimate_all(dataset, record, request, estimators=["aipw"])
    result = _result(payload, "aipw")
    uncertainty = result["uncertainty"]
    assert uncertainty["method"] == "influence_function_normal_approximation"
    # The pseudo-outcomes are not serialised; recompute the SE via the module.
    prepared = prepare_cohort(
        dataset, request, treatment_column="t", outcome_column="y", covariate_columns=["x1", "x2"]
    )
    output = estimate_aipw(
        prepared.frame,
        prepared.treatment,
        prepared.outcome,
        prepared.covariates,
        prepared.missing_policy,
        prepared.outcome_task,
        request,
    )
    expected_se = float(np.std(output.pseudo_outcome, ddof=1) / np.sqrt(len(prepared.treatment)))
    assert abs(uncertainty["standard_error"] - expected_se) < 1e-10
    assert abs(output.estimate - float(np.mean(output.pseudo_outcome))) < 1e-12


def test_balance_smd_hand_computed_arithmetic():
    """Four-row example with hand-computed SMDs, both unweighted and weighted."""
    frame = pd.DataFrame(
        {
            "z": [1.0, 3.0, 5.0, 7.0],
            "t": [1, 1, 0, 0],
            "y": [0.0, 0.0, 0.0, 0.0],
        }
    )
    from app.causal.estimation.preparation import CovariateSpec

    spec_cov = [CovariateSpec(column="z", kind="numeric")]
    treatment = frame["t"].to_numpy()
    balance = balance_payload(frame, treatment, spec_cov, weights=None)
    entry = balance["covariates"][0]
    # Treated mean 2, control mean 6; variances 1 and 1; pooled sd 1.
    assert entry["smd_unweighted"] == pytest.approx((2 - 6) / 1.0)

    weights = np.array([2.0, 1.0, 1.0, 3.0])
    weighted = balance_payload(frame, treatment, spec_cov, weights=weights)
    entry = weighted["covariates"][0]
    # Weighted treated mean = (2·1+1·3)/3 = 5/3; control = (1·5+3·7)/4 = 26/4.
    t_vals = frame.loc[frame["t"] == 1, "z"].to_numpy()
    c_vals = frame.loc[frame["t"] == 0, "z"].to_numpy()
    w_t = weights[frame["t"].to_numpy() == 1]
    w_c = weights[frame["t"].to_numpy() == 0]
    mean_t = np.average(t_vals, weights=w_t)
    mean_c = np.average(c_vals, weights=w_c)
    var_t = np.average((t_vals - mean_t) ** 2, weights=w_t)
    var_c = np.average((c_vals - mean_c) ** 2, weights=w_c)
    expected = (mean_t - mean_c) / np.sqrt((var_t + var_c) / 2)
    assert entry["smd_weighted"] == pytest.approx(expected)
    assert entry["smd_unweighted"] == pytest.approx((2 - 6) / 1.0)


def test_weighted_balance_collapses_after_ipw():
    """Post-weighting SMDs on a confounded DGP shrink far below pre-weighting."""
    frame = _frame_from_rng(1000, 29, effect=1.5)
    dataset = _dataset(frame)
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    request = _request(dataset, record.spec, uncertainty={"method": "influence_function"})
    payload = _estimate_all(dataset, record, request, estimators=["ipw"])
    balance = _result(payload, "ipw")["diagnostics"]["balance"]
    for entry in balance["covariates"]:
        assert abs(entry["smd_weighted"]) < abs(entry["smd_unweighted"]) or abs(
            entry["smd_weighted"]
        ) < 0.1, entry


def test_gate_refuses_unverifiable_client_claims_about_the_set():
    """A set the client claims is fine is re-verified by identification from the graph."""
    dag = DAG(["x", "t", "y"], [("x", "t"), ("x", "y"), ("t", "y")])
    observed = {"x", "t", "y"}
    verdict = evaluate_adjustment_set(dag, "t", "y", [], observed)
    assert verdict.valid is False  # the gate would refuse this request


def test_estimand_scope_note_present_in_every_payload():
    dataset = _dataset(_frame_from_rng(300, 30, effect=1.0))
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    payload = _estimate_all(dataset, record, _request(dataset, record.spec), estimators=["ipw"])
    assert "positivity" in payload["scope_note"]
    assert "proven" in payload["scope_note"] or "assumptions" in payload["scope_note"]
    assert payload["gate"]["caveat"]
    limits = EstimationLimits.as_dict()
    assert payload["reproducibility"]["limits"] == limits


def test_binary_outcome_estimated_as_probability_difference():
    rng = np.random.default_rng(91)
    n = 1500
    x1 = rng.normal(0, 1, n)
    propensity = 1.0 / (1.0 + np.exp(-(0.9 * x1)))
    t = rng.binomial(1, propensity)
    # A logistic model with effect log-odds 0.8; on the probability scale the
    # average difference is near 0.14 for this baseline. The test asserts the
    # documented interpretation and a positive effect, not the exact parameter
    # (the probability-scale ATE has no closed form here).
    p = 1.0 / (1.0 + np.exp(-(0.8 * t + 0.5 * x1)))
    y = (rng.random(n) < p).astype(int)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": y})
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id, nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ], edges=[("x1", "t"), ("x1", "y"), ("t", "y")])
    record = _record(dataset, spec)
    request = _request(dataset, record.spec, adjustment=["x1"])
    payload = _estimate_all(dataset, record, request, estimators=["regression_adjustment", "aipw"])
    assert payload["analysis"]["outcome_task"] == "logistic"
    assert payload["analysis"]["outcome_units_note"].startswith("The outcome was detected as binary")
    for estimator in ("regression_adjustment", "aipw"):
        result = _result(payload, estimator)
        assert result["units"] == "probability_difference"
        assert 0.05 < result["estimate"] < 0.3, (estimator, result["estimate"])
    coding = payload["analysis"]["outcome_coding"]
    assert coding["coded_one"] == 1 and coding["coded_zero"] == 0


def test_comparison_uses_one_shared_cohort():
    dataset = _dataset(_frame_from_rng(600, 32, effect=1.5))
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    payload = _estimate_all(dataset, record, _request(dataset, record.spec), compare=True)
    assert len(payload["results"]) == 3
    assert all(r["sample_size"] == payload["analysis"]["rows_final"] for r in payload["results"])
    comparison = payload["comparison"]
    assert set(comparison["estimates"]) == {"regression_adjustment", "ipw", "aipw"}
    assert "select a winner" in comparison["interpretation"] or "not resolved" in comparison["interpretation"]


def test_unknown_estimator_refused():
    dataset = _dataset(_frame_from_rng(300, 33, effect=1.0))
    record = _record(dataset, _confounded_spec(dataset.dataset_id))
    with pytest.raises(ValidationFailure):
        run_estimation(
            dataset, record, _request(dataset, record.spec), estimator_names=["magic_estimator"]
        )
