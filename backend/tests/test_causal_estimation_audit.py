"""estimation independent numerical audit harness.

This module re-implements the estimators from their mathematical definitions
using numpy and statsmodels only - it never calls the production estimator
helpers to produce a reference value. Production output is compared against
these references on controlled data-generating processes with known answers.

Where the reference must make the same modelling choices (which nuisance
model, which folds), the reference uses a *different implementation* of the
same choice (statsmodels IRLS/GLM and OLS vs scikit-learn pipelines) so
agreement is evidence about the shared mathematics, not about shared code.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from app.audit.dataset import Dataset
from app.causal.estimation.contracts import EstimationRequest
from app.causal.estimation.service import run_estimation
from app.causal.registry import CausalGraphRecord
from app.causal.schema import CausalGraphSpec

from .conftest import make_dataset

# --------------------------------------------------------------------------- #
# Independent reference implementations (numpy / statsmodels only)
# --------------------------------------------------------------------------- #


def ref_gcomp_ols(t: np.ndarray, y: np.ndarray, covariates: dict[str, np.ndarray]) -> float:
    """G-computation with OLS via explicit design matrices and lstsq.

    Fits m(t, x) = b0 + b_t*t + x'b_x, then averages m(1, X) - m(0, X) over
    the empirical population - the definition, not a shortcut (the result
    equals b_t for this model family, which is itself a check).
    """
    n = len(t)
    x_matrix = np.column_stack(list(covariates.values())) if covariates else np.zeros((n, 0))
    design = np.column_stack([np.ones(n), t, x_matrix])
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    b0, b_t, b_x = coefficients[0], coefficients[1], coefficients[2:]
    m1 = b0 + b_t + x_matrix @ b_x
    m0 = b0 + 0.0 + x_matrix @ b_x
    return float(np.mean(m1 - m0))


def ref_hajek(e: np.ndarray, t: np.ndarray, y: np.ndarray) -> float:
    """Hájek IPW with a propensity supplied by the caller."""
    w1 = t / e
    w0 = (1 - t) / (1 - e)
    return float(np.sum(w1 * y) / np.sum(w1) - np.sum(w0 * y) / np.sum(w0))


def ref_aipw_crossfit(
    t: np.ndarray,
    y: np.ndarray,
    covariates: dict[str, np.ndarray],
    *,
    splits: int,
    seed: int,
) -> tuple[float, float]:
    """Cross-fitted AIPW with statsmodels nuisances - independent pipeline.

    Same fold construction (shuffled KFold, same seed) but completely
    different fitting code: GLM Binomial IRLS for the propensity, OLS for
    treatment-specific outcome models.
    """
    from sklearn.model_selection import KFold

    n = len(t)
    x_matrix = np.column_stack(list(covariates.values()))
    x_with_const = np.column_stack([np.ones(n), x_matrix])
    e_hat = np.full(n, np.nan)
    m1_hat = np.full(n, np.nan)
    m0_hat = np.full(n, np.nan)
    for train_idx, test_idx in KFold(n_splits=splits, shuffle=True, random_state=seed).split(
        np.arange(n)
    ):
        glm = sm.GLM(
            t[train_idx], x_with_const[train_idx], family=sm.families.Binomial()
        ).fit()
        e_hat[test_idx] = glm.predict(x_with_const[test_idx])
        treated = train_idx[t[train_idx] == 1]
        control = train_idx[t[train_idx] == 0]
        m1 = sm.OLS(y[treated], x_with_const[treated]).fit()
        m0 = sm.OLS(y[control], x_with_const[control]).fit()
        m1_hat[test_idx] = m1.predict(x_with_const[test_idx])
        m0_hat[test_idx] = m0.predict(x_with_const[test_idx])
    psi = (
        m1_hat
        - m0_hat
        + t * (y - m1_hat) / e_hat
        - (1 - t) * (y - m0_hat) / (1 - e_hat)
    )
    return float(np.mean(psi)), float(np.std(psi, ddof=1) / np.sqrt(n))


# --------------------------------------------------------------------------- #
# Shared fixture plumbing (independent of the original test file's helpers)
# --------------------------------------------------------------------------- #


def _dataset(frame: pd.DataFrame) -> Dataset:
    return make_dataset(frame.to_dict("records"), name="audit-fixture.csv")


def _record(dataset: Dataset, columns: list[str]) -> CausalGraphRecord:
    covariate_nodes = [{"node_id": c, "label": c, "column": c} for c in columns if c not in ("t", "y")]
    edges = []
    for c in columns:
        if c not in ("t", "y"):
            edges += [{"source": c, "target": "t"}, {"source": c, "target": "y"}]
    edges.append({"source": "t", "target": "y"})
    spec = CausalGraphSpec(
        name="Audit graph",
        dataset_id=dataset.dataset_id,
        nodes=[*covariate_nodes, {"node_id": "t", "label": "t", "column": "t"},
               {"node_id": "y", "label": "y", "column": "y"}],
        edges=edges,
        analysis={"treatment": "t", "outcome": "y"},
    )
    return CausalGraphRecord(
        graph_id="cgraph-audit",
        dataset_id=dataset.dataset_id,
        dataset_fingerprint_sha256=dataset.fingerprint_sha256,
        spec=spec,
        revision=0,
    )


def _request(columns: list[str], **overrides) -> EstimationRequest:
    body: dict = {
        "treatment_node": "t",
        "outcome_node": "y",
        "adjustment_nodes": [c for c in columns if c not in ("t", "y")],
        "treatment_mapping": {"treated": "1", "control": "0"},
        "uncertainty": {"method": "influence_function", "reps": 100, "seed": 5},
    }
    body.update(overrides)
    return EstimationRequest(**body)


def _production_estimates(dataset: Dataset, record: CausalGraphRecord, request: EstimationRequest) -> dict:
    payload = run_estimation(
        dataset, record, request, estimator_names=["regression_adjustment", "ipw", "aipw"]
    )
    return {
        result["estimator"]: result
        for result in payload["results"]
        if result["status"] == "estimated"
    }


# --------------------------------------------------------------------------- #
# A1-A2: randomized treatment, known / zero ATE
# --------------------------------------------------------------------------- #


def test_a1_randomized_known_ate_all_references_agree():
    rng = np.random.default_rng(101)
    n = 900
    t = rng.binomial(1, 0.5, n)
    covariates = {"x1": rng.normal(0, 1, n)}  # measured, but not a confounder here
    y = 1.75 * t + 0.5 * covariates["x1"] + rng.normal(0, 1, n)
    frame = pd.DataFrame({**covariates, "t": t, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, [*covariates.keys(), "t", "y"])

    production = _production_estimates(dataset, record, _request([*covariates.keys(), "t", "y"]))
    # Independent references.
    assert abs(ref_gcomp_ols(t, y, covariates) - 1.75) < 0.25
    assert abs(ref_hajek(np.full(n, 0.5), t, y) - 1.75) < 0.25  # true e = 0.5
    assert abs(production["regression_adjustment"]["estimate"] - ref_gcomp_ols(t, y, covariates)) < 1e-8
    # Production estimates e; on a randomized design it must land on 0.5.
    assert abs(production["ipw"]["estimate"] - ref_hajek(np.full(n, 0.5), t, y)) < 0.1
    for estimator in production.values():
        assert abs(estimator["estimate"] - 1.75) < 0.25


def test_a2_randomized_zero_ate():
    rng = np.random.default_rng(102)
    n = 900
    t = rng.binomial(1, 0.5, n)
    x1 = rng.normal(0, 1, n)
    y = 0.0 * t + 0.6 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    production = _production_estimates(dataset, record, _request(["x1", "t", "y"]))
    for estimator in production.values():
        assert abs(estimator["estimate"]) < 0.2
        uncertainty = estimator["uncertainty"]
        if uncertainty["status"] == "available":
            assert uncertainty["ci_lower"] <= 0.0 <= uncertainty["ci_upper"]
        else:
            assert uncertainty["status"] == "unavailable"
            assert uncertainty["ci_lower"] is None


# --------------------------------------------------------------------------- #
# A3-A5: confounded / multi-confounder / categorical DGPs vs the references
# --------------------------------------------------------------------------- #


def test_a3_confounded_ate_matches_independent_aipw_pipeline():
    rng = np.random.default_rng(103)
    n = 1000
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-(0.8 * x1 - 0.5 * x2))))
    y = 1.2 * t + 0.9 * x1 - 0.7 * x2 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "x2": x2, "t": t, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "x2", "t", "y"])
    request = _request(["x1", "x2", "t", "y"], cross_fit={"splits": 5, "group_column": None})
    production = _production_estimates(dataset, record, request)

    # Production AIPW vs the fully independent statsmodels cross-fit pipeline:
    # different libraries, same mathematics. Tolerance ~1 joint SE.
    ref_ate, ref_se = ref_aipw_crossfit(t, y, {"x1": x1, "x2": x2}, splits=5, seed=5)
    production_aipw = production["aipw"]["estimate"]
    assert abs(production_aipw - ref_ate) < 0.15, (production_aipw, ref_ate)
    # Different nuisance-fitting code must still agree on the SE magnitude.
    production_se = production["aipw"]["uncertainty"]["standard_error"]
    assert 0.5 * ref_se < production_se < 2.0 * ref_se, (production_se, ref_se)
    assert abs(production_aipw - 1.2) < 0.3
    assert abs(production["regression_adjustment"]["estimate"] - ref_gcomp_ols(t, y, {"x1": x1, "x2": x2})) < 1e-8


def test_a4_multiple_confounders_recovered():
    rng = np.random.default_rng(104)
    n = 1200
    covariates = {f"x{i}": rng.normal(0, 1, n) for i in (1, 2, 3)}
    linear = 0.7 * covariates["x1"] - 0.6 * covariates["x2"] + 0.5 * covariates["x3"]
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-linear)))
    y = 0.9 * t + 0.8 * covariates["x1"] - 0.6 * covariates["x2"] + 0.5 * covariates["x3"] + rng.normal(0, 1, n)
    frame = pd.DataFrame({**covariates, "t": t, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, [*covariates.keys(), "t", "y"])
    production = _production_estimates(dataset, record, _request([*covariates.keys(), "t", "y"]))
    for estimator in production.values():
        assert abs(estimator["estimate"] - 0.9) < 0.3


def test_a5_categorical_confounder_matches_independent_encoding():
    rng = np.random.default_rng(105)
    n = 1200
    region = rng.choice(["north", "south", "west"], n)
    effect = np.select([region == "north", region == "south", region == "west"], [0.8, 0.0, -0.6])
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-2.0 * effect)))
    y = 1.0 * t + effect + rng.normal(0, 1, n)
    # The reference encodes the same way the contract documents: level
    # indicators with one reference level dropped.
    d_north = (region == "north").astype(float)
    d_south = (region == "south").astype(float)
    covariates = {"d_north": d_north, "d_south": d_south}
    frame = pd.DataFrame({"region": region, "t": t, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, ["region", "t", "y"])
    production = _production_estimates(dataset, record, _request(["region", "t", "y"]))
    for estimator in production.values():
        assert abs(estimator["estimate"] - 1.0) < 0.3, estimator["estimator"]
    # The one-hot g-computation on the same encoding is an independent check.
    assert abs(ref_gcomp_ols(t, y, covariates) - 1.0) < 0.3


# --------------------------------------------------------------------------- #
# A6: small deterministic example - exact arithmetic, all three estimators
# --------------------------------------------------------------------------- #


def test_a6_small_deterministic_example_exact():
    """24 rows, perfectly balanced randomized t, y = 2t + v where the noise v
    has exactly zero mean in each arm by construction (continuous, so the
    outcome is not misread as binary - a binary outcome would legitimately be
    reported as a probability difference, not 2.0).

    With e = 0.5 (intercept-only propensity on an exactly balanced design),
    the arm outcome means are 2 and 0, so RA, Hajek IPW and AIPW all equal
    2.0 up to the propensity solver's float convergence. Hand-derived.
    """
    n = 24
    t = np.array([i % 2 for i in range(n)])  # exactly 12/12
    w = 0.7 * np.sin(np.arange(n)) + 0.013 * np.arange(n)
    v = np.where(t == 1, w - np.mean(w[t == 1]), w - np.mean(w[t == 0]))
    y = 2.0 * t + v
    assert len(np.unique(y)) > 2  # genuinely continuous
    frame = pd.DataFrame({"t": t, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, ["t", "y"])
    production = _production_estimates(dataset, record, _request(["t", "y"]))
    for estimator in production.values():
        assert estimator["estimate"] == pytest.approx(2.0, abs=1e-5), estimator["estimator"]
        uncertainty = estimator["uncertainty"]
        if uncertainty["status"] == "available":
            assert uncertainty["ci_lower"] < 2.0 < uncertainty["ci_upper"]


# --------------------------------------------------------------------------- #
# A7-A8: severe imbalance and near-positivity violation
# --------------------------------------------------------------------------- #


def test_a7_severe_imbalance_still_defined_and_honest():
    rng = np.random.default_rng(107)
    n = 1200
    x1 = rng.normal(0, 1, n)
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-(1.2 * x1 + 2.2))))  # ~89% treated
    y = 0.8 * t + 0.9 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    production = _production_estimates(dataset, record, _request(["x1", "t", "y"]))
    for estimator in production.values():
        assert np.isfinite(estimator["estimate"])
        assert abs(estimator["estimate"] - 0.8) < 0.35, estimator["estimator"]


def test_a8_near_positivity_violation_warns_and_stays_finite():
    rng = np.random.default_rng(108)
    n = 1200
    x1 = rng.normal(0, 1, n)
    t = (x1 > 0.0).astype(int)  # near-perfect separation
    y = 1.0 * t + 0.5 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    production = _production_estimates(dataset, record, _request(["x1", "t", "y"]))
    ipw = production["ipw"]
    overlap = ipw["diagnostics"]["overlap"]
    assert overlap["warnings"], "near-separation must warn"
    summary = overlap["propensity_summary"]
    assert summary["min"] < 0.01 or summary["max"] > 0.99
    assert np.isfinite(ipw["estimate"])


# --------------------------------------------------------------------------- #
# A9-A10: constant outcome, missing outcome/covariates
# --------------------------------------------------------------------------- #


def test_a9_constant_outcome_zero_everywhere_no_nan():
    rng = np.random.default_rng(109)
    n = 400
    x1 = rng.normal(0, 1, n)
    t = rng.binomial(1, 0.5, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": np.full(n, 3.5)})
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    production = _production_estimates(dataset, record, _request(["x1", "t", "y"]))
    for estimator in production.values():
        assert estimator["estimate"] == pytest.approx(0.0, abs=1e-12)
        uncertainty = estimator["uncertainty"]
        if uncertainty["status"] == "available":
            assert uncertainty["standard_error"] == pytest.approx(0.0, abs=1e-12)
            assert np.isfinite(uncertainty["ci_lower"]) and np.isfinite(uncertainty["ci_upper"])
        else:
            # RA has no influence function here: the honest unavailable state.
            assert uncertainty["ci_lower"] is None and uncertainty["ci_upper"] is None


def test_a10_missing_outcome_and_covariate_rows_excluded_with_recovery():
    rng = np.random.default_rng(110)
    n = 600
    x1 = rng.normal(0, 1, n)
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-0.8 * x1)))
    y = 1.3 * t + 0.9 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": y})
    frame.loc[frame.index[:9], "y"] = np.nan
    frame.loc[frame.index[9:21], "x1"] = np.nan
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    request = _request(["x1", "t", "y"])
    payload = run_estimation(dataset, record, request, estimator_names=["ipw"])
    analysis = payload["analysis"]
    reasons = {e["reason"]: e["count"] for e in analysis["exclusions"]}
    assert reasons.get("missing_outcome_value") == 9
    assert reasons.get("missing_covariate_complete_case") == 12
    assert analysis["rows_final"] + sum(reasons.values()) == n
    result = payload["results"][0]
    assert result["status"] == "estimated"
    assert abs(result["estimate"] - 1.3) < 0.35


# --------------------------------------------------------------------------- #
# A11-A13: no valid adjustment set / post-treatment / unobserved
# --------------------------------------------------------------------------- #


def test_a11_strong_association_without_valid_set_is_refused():
    # x is a common cause; the client offers only the empty set.
    rng = np.random.default_rng(111)
    n = 300
    x1 = rng.normal(0, 1, n)
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-1.5 * x1)))
    y = 2.0 * t + 1.5 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    from app.core.errors import ValidationFailure

    with pytest.raises(ValidationFailure):
        run_estimation(
            dataset, record, _request(["x1", "t", "y"], adjustment_nodes=[]), estimator_names=["ipw"]
        )


def test_a12_post_treatment_adjustment_refused():
    rng = np.random.default_rng(112)
    n = 300
    x1 = rng.normal(0, 1, n)
    t = rng.binomial(1, 0.5, n)
    m = 0.9 * t + rng.normal(0, 1, n)
    y = 1.0 * t + 0.8 * m + 0.5 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "m": m, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "m", "y"])
    # Graph: x1 -> t, x1 -> y, t -> m, m -> y, t -> y. m is a mediator.
    record.spec = CausalGraphSpec(
        name="Mediator graph",
        dataset_id=dataset.dataset_id,
        nodes=[
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "m", "label": "m", "column": "m"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        edges=[
            {"source": "x1", "target": "t"},
            {"source": "x1", "target": "y"},
            {"source": "t", "target": "m"},
            {"source": "m", "target": "y"},
            {"source": "t", "target": "y"},
        ],
        analysis={"treatment": "t", "outcome": "y"},
    )
    from app.core.errors import ValidationFailure

    with pytest.raises(ValidationFailure) as excinfo:
        run_estimation(
            dataset,
            record,
            _request(["x1", "t", "m", "y"], adjustment_nodes=["x1", "m"]),
            estimator_names=["ipw"],
        )
    violations = excinfo.value.details["verification"]["violations"]
    assert any(v["code"] == "post_treatment_variable" for v in violations)


def test_a13_unobserved_confounder_blocks_estimation():
    rng = np.random.default_rng(113)
    n = 300
    x1 = rng.normal(0, 1, n)
    u = rng.normal(0, 1, n)
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-(0.9 * x1 + 1.1 * u))))
    y = 1.0 * t + 0.7 * x1 + 1.4 * u + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "t": t, "y": y})  # u is never a column
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    record.spec = CausalGraphSpec(
        name="Unobserved confounder graph",
        dataset_id=dataset.dataset_id,
        nodes=[
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
            {"node_id": "u", "label": "u", "observed": False, "kind": "unobserved"},
        ],
        edges=[
            {"source": "x1", "target": "t"},
            {"source": "x1", "target": "y"},
            {"source": "u", "target": "t"},
            {"source": "u", "target": "y"},
            {"source": "t", "target": "y"},
        ],
        analysis={"treatment": "t", "outcome": "y"},
    )
    from app.core.errors import ValidationFailure

    with pytest.raises(ValidationFailure):
        run_estimation(dataset, record, _request(["x1", "t", "y"]), estimator_names=["ipw"])


# --------------------------------------------------------------------------- #
# A14-A15: bootstrap and cross-fitted AIPW reproducibility
# --------------------------------------------------------------------------- #


def _confounded_frame(seed: int, n: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-(0.8 * x1 - 0.5 * x2))))
    y = 1.4 * t + 0.9 * x1 - 0.7 * x2 + rng.normal(0, 1, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "t": t, "y": y})


def test_a14_bootstrap_reproducible_and_refitting():
    frame = _confounded_frame(114)
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "x2", "t", "y"])

    def boot_run(seed: int) -> dict:
        request = _request(
            ["x1", "x2", "t", "y"],
            uncertainty={"method": "bootstrap", "reps": 120, "seed": seed},
        )
        payload = run_estimation(dataset, record, request, estimator_names=["ipw"])
        uncertainty = payload["results"][0]["uncertainty"]
        return {
            "ci": (uncertainty["ci_lower"], uncertainty["ci_upper"]),
            "failed": uncertainty["bootstrap"]["reps_failed"],
            "refit": uncertainty["bootstrap"]["refit_nuisance_models"],
        }

    first = boot_run(2026)
    second = boot_run(2026)
    third = boot_run(7)
    assert first == second
    assert first["ci"] != third["ci"]
    assert first["refit"] is True
    assert first["failed"] == 0


def test_a15_crossfit_aipw_reproducible():
    frame = _confounded_frame(115)
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "x2", "t", "y"])

    def aipw_run(seed: int) -> tuple[float, float]:
        request = _request(
            ["x1", "x2", "t", "y"],
            uncertainty={"method": "influence_function", "reps": 100, "seed": seed},
        )
        payload = run_estimation(dataset, record, request, estimator_names=["aipw"])
        result = payload["results"][0]
        return result["estimate"], result["uncertainty"]["standard_error"]

    assert aipw_run(42) == aipw_run(42)


# --------------------------------------------------------------------------- #
# Independent uncertainty arithmetic
# --------------------------------------------------------------------------- #


def test_z_critical_matches_scipy_and_level_is_applied():
    from scipy import stats as scipy_stats

    from app.causal.estimation.uncertainty import _z_critical

    assert _z_critical(0.95) == pytest.approx(float(scipy_stats.norm.ppf(0.975)))
    assert _z_critical(0.90) < _z_critical(0.95)
    # A 90% interval from the same influence values is exactly z-ratio narrower.
    rng = np.random.default_rng(116)
    influence = rng.normal(0, 2.0, 500)
    from app.causal.estimation.estimators import EstimatorOutput

    output = EstimatorOutput(
        estimator="aipw",
        estimate=float(np.mean(influence)),
        mu1=None,
        mu0=None,
        influence=influence,
        propensity=None,
        pseudo_outcome=None,
        model_spec={},
    )
    wide = influence_function_interval(output, 0.95)
    narrow = influence_function_interval(output, 0.90)
    ratio = (narrow.ci_upper - narrow.ci_lower) / (wide.ci_upper - wide.ci_lower)
    assert ratio == pytest.approx(_z_critical(0.90) / _z_critical(0.95), rel=1e-12)


from app.causal.estimation.uncertainty import influence_function_interval
