"""S9C independent scientific audit harness.

This module re-derives every headline S9C quantity with **independently
implemented** machinery and compares it against the production payload. It
deliberately does not import the production estimators to produce its
expectations:

* AIPW is re-implemented here with its own cross-fitting loop over
  scikit-learn primitives, written from the estimating equation.
* IPW/Hájek expectations are computed in closed form from an intercept-only
  propensity design (a randomised experiment), where the estimator has an
  exact algebraic answer: arm-mean differences with the influence-function SE.
* The sensitivity grid is re-fit with statsmodels OLS g-computation, an
  entirely separate fitting path from the production sklearn pipeline.
* What-if profile predictions are compared with hand-derived OLS predictions
  from a noise-free linear DGP where the fitted model is known exactly.
* Subsampling traceability: the first repetition is re-drawn here from the
  recorded seed and re-estimated with the independent AIPW implementation.

Tolerances are ~3 sampling standard errors for stochastic comparisons and
1e-6..1e-8 for algebraically exact ones. Nothing here silences a mismatch:
a failure means the production number and the independent number disagree.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as scipy_stats
import statsmodels.api as sm

from app.audit.dataset import Dataset
from app.causal.estimation.contracts import EstimationRequest
from app.causal.estimation.robustness import (
    ConfounderSpec,
    PlaceboSpec,
    RobustnessLimits,
    SubsamplingSpec,
    run_robustness_experiment,
)
from app.causal.estimation.service import run_estimation
from app.causal.estimation.subgroups import SubgroupSpec, run_subgroup_estimation
from app.causal.estimation.whatif import run_what_if
from app.causal.registry import CausalGraphRecord
from app.causal.schema import CausalGraphSpec
from app.core.errors import ValidationFailure

from .conftest import make_dataset

SEED = 910_231


# --------------------------------------------------------------------------- #
# Independent estimation machinery (never imported from production code)
# --------------------------------------------------------------------------- #


def _independent_crossfit_aipw(
    frame: pd.DataFrame,
    treatment: np.ndarray,
    outcome: np.ndarray,
    covariate_columns: list[str],
    splits: int,
    seed: int,
) -> dict[str, float]:
    """A from-scratch cross-fitted AIPW written directly from the equation.

    Uses sklearn primitives only; the fold construction, nuisance fitting and
    pseudo-outcome assembly are re-derived here, not shared with production.
    """
    from sklearn.linear_model import LinearRegression, LogisticRegression

    x = frame[covariate_columns].to_numpy(dtype=float)
    n = len(treatment)
    kfold = _independent_kfold(n, splits, seed)
    e_hat = np.full(n, np.nan)
    m1_hat = np.full(n, np.nan)
    m0_hat = np.full(n, np.nan)
    for train_idx, test_idx in kfold:
        ps = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
        ps.fit(x[train_idx], treatment[train_idx])
        e_hat[test_idx] = ps.predict_proba(x[test_idx])[:, 1]
        treated = train_idx[treatment[train_idx] == 1]
        control = train_idx[treatment[train_idx] == 0]
        m1 = LinearRegression().fit(x[treated], outcome[treated])
        m0 = LinearRegression().fit(x[control], outcome[control])
        m1_hat[test_idx] = m1.predict(x[test_idx])
        m0_hat[test_idx] = m0.predict(x[test_idx])
    psi = (
        m1_hat
        - m0_hat
        + treatment * (outcome - m1_hat) / e_hat
        - (1 - treatment) * (outcome - m0_hat) / (1 - e_hat)
    )
    return {
        "ate": float(np.mean(psi)),
        "se": float(np.std(psi, ddof=1) / np.sqrt(n)),
        "psi": psi,
    }


def _independent_kfold(n: int, splits: int, seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """Deterministic shuffled k-fold written independently of production."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    folds = np.array_split(order, splits)
    result = []
    for fold in folds:
        test_idx = fold
        train_idx = np.setdiff1d(order, fold)
        result.append((train_idx, test_idx))
    return result


def _independent_hajek_ipw(treatment: np.ndarray, outcome: np.ndarray) -> dict[str, float]:
    """Exact Hájek IPW for an intercept-only propensity (randomised design).

    With e(x) constant at the treated fraction p, w1 = T/p and w0 = (1-T)/(1-p),
    the Hájek ratio estimators collapse to the per-arm means, and the
    influence-function SE is sd(phi1 - phi0)/sqrt(n) with
    phi_k = n * w_k * (Y - mu_k) / sum(w_k) — all recomputed here.
    """
    p = float(treatment.mean())
    w1 = treatment / p
    w0 = (1 - treatment) / (1 - p)
    mu1 = float(np.sum(w1 * outcome) / np.sum(w1))
    mu0 = float(np.sum(w0 * outcome) / np.sum(w0))
    n = len(treatment)
    phi1 = n * w1 * (outcome - mu1) / np.sum(w1)
    phi0 = n * w0 * (outcome - mu0) / np.sum(w0)
    influence = phi1 - phi0
    return {
        "ate": mu1 - mu0,
        "se": float(np.std(influence, ddof=1) / np.sqrt(n)),
        "mu1": mu1,
        "mu0": mu0,
    }


def _independent_ols_gcomputation(
    frame: pd.DataFrame,
    treatment: np.ndarray,
    outcome: np.ndarray,
    covariate_columns: list[str],
) -> float:
    """statsmodels OLS g-computation ATE — a completely separate fitting path."""
    design = pd.DataFrame(frame[list(covariate_columns)]).copy()
    design["t"] = treatment
    design = sm.add_constant(design, has_constant="add")
    model = sm.OLS(outcome, design).fit()
    design_1 = design.copy()
    design_1["t"] = 1.0
    design_0 = design.copy()
    design_0["t"] = 0.0
    return float(np.mean(model.predict(design_1) - model.predict(design_0)))


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _randomised_frame(
    n: int = 800,
    effect: float = 1.5,
    seed: int = SEED,
    treat_share: float = 0.5,
) -> pd.DataFrame:
    """Randomised experiment: t ⊥ x, y = effect·t + x·b + noise. No confounding."""
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0.0, 1.0, n)
    x2 = rng.normal(0.0, 1.0, n)
    t = rng.binomial(1, treat_share, n)
    y = effect * t + 0.8 * x1 - 0.6 * x2 + rng.normal(0.0, 1.0, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "t": t, "y": y})


def _confounded_frame(
    n: int = 900,
    effect: float = 1.2,
    seed: int = SEED + 1,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0.0, 1.0, n)
    x2 = rng.normal(0.0, 1.0, n)
    propensity = 1.0 / (1.0 + np.exp(-(-0.4 + 0.8 * x1 - 0.5 * x2)))
    t = rng.binomial(1, propensity)
    y = effect * t + 0.9 * x1 - 0.7 * x2 + rng.normal(0.0, 1.0, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "t": t, "y": y})


def _dataset(frame: pd.DataFrame) -> Dataset:
    return make_dataset(frame.to_dict("records"), name="s9c-audit.csv")


def _randomised_spec(dataset_id: str) -> CausalGraphSpec:
    return CausalGraphSpec(
        name="Audit randomised graph",
        dataset_id=dataset_id,
        nodes=[
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "x2", "label": "x2", "column": "x2"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        edges=[{"source": "x1", "target": "y"}, {"source": "x2", "target": "y"},
               {"source": "t", "target": "y"}],
        analysis={"treatment": "t", "outcome": "y"},
    )


def _confounded_spec(dataset_id: str) -> CausalGraphSpec:
    return CausalGraphSpec(
        name="Audit confounded graph",
        dataset_id=dataset_id,
        nodes=[
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "x2", "label": "x2", "column": "x2"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        edges=[
            {"source": "x1", "target": "t"}, {"source": "x1", "target": "y"},
            {"source": "x2", "target": "t"}, {"source": "x2", "target": "y"},
            {"source": "t", "target": "y"},
        ],
        analysis={"treatment": "t", "outcome": "y"},
    )


def _record(dataset: Dataset, spec: CausalGraphSpec) -> CausalGraphRecord:
    return CausalGraphRecord(
        graph_id="cgraph-s9c-audit",
        dataset_id=dataset.dataset_id,
        dataset_fingerprint_sha256=dataset.fingerprint_sha256,
        spec=spec,
        revision=1,
    )


def _request(adjustment: list[str], seed: int = SEED) -> EstimationRequest:
    return EstimationRequest(
        treatment_node="t",
        outcome_node="y",
        adjustment_nodes=adjustment,
        treatment_mapping={"treated": "1", "control": "0"},
        cross_fit={"splits": 5},
        uncertainty={"method": "influence_function", "reps": 100, "seed": seed, "level": 0.95},
        expected_spec_fingerprint_sha256=None,
    )


# --------------------------------------------------------------------------- #
# 1. Subgroup engine vs an independent cross-fitted AIPW
# --------------------------------------------------------------------------- #


def test_audit_1_subgroup_estimates_match_independent_aipw_implementation():
    """Known heterogeneous effects, confounded treatment, valid adjustment.

    The production subgroup payload is compared against an AIPW re-implemented
    here from the estimating equation. Both are finite-sample estimators of the
    same truth, so agreement is judged at ~3 combined standard errors.
    """
    frame = _confounded_frame()
    frame["g"] = np.where(frame["x1"] > 0.0, "A", "B")
    dataset = _dataset(frame)
    spec = CausalGraphSpec(
        name="Audit subgroup graph",
        dataset_id=dataset.dataset_id,
        nodes=[
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "x2", "label": "x2", "column": "x2"},
            {"node_id": "g", "label": "g", "column": "g"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        edges=[
            {"source": "x1", "target": "t"}, {"source": "x1", "target": "y"},
            {"source": "x2", "target": "t"}, {"source": "x2", "target": "y"},
            {"source": "g", "target": "t"}, {"source": "g", "target": "y"},
            {"source": "t", "target": "y"},
        ],
        analysis={"treatment": "t", "outcome": "y"},
    )
    record = _record(dataset, spec)
    request = _request(["x1", "x2", "g"])
    payload = run_subgroup_estimation(dataset, record, request, SubgroupSpec("g"))

    independent = _independent_crossfit_aipw(
        frame, frame["t"].to_numpy(float), frame["y"].to_numpy(float),
        ["x1", "x2"], splits=5, seed=SEED,
    )
    # The production payload must agree with the independent implementation
    # within 3 independent standard errors (different folds, same estimand).
    combined_se = independent["se"]
    assert payload["overall"]["estimate"] == pytest.approx(independent["ate"], abs=3 * combined_se)
    assert payload["overall"]["standard_error"] == pytest.approx(independent["se"], rel=0.35)

    # Independent within-group means of the independent psi vs production groups.
    psi = independent["psi"]
    for label, mask in (("A", (frame["g"] == "A").to_numpy()), ("B", (frame["g"] == "B").to_numpy())):
        entry = next(group for group in payload["groups"] if group["label"] == label)
        independent_group_ate = float(np.mean(psi[mask]))
        independent_group_se = float(np.std(psi[mask], ddof=1) / np.sqrt(mask.sum()))
        assert entry["status"] == "estimated"
        assert entry["estimate"] == pytest.approx(independent_group_ate, abs=3 * (combined_se + independent_group_se))
        assert entry["standard_error"] == pytest.approx(independent_group_se, rel=0.4)


def _confounded_spec_with_g(dataset_id: str) -> CausalGraphSpec:
    spec = _confounded_spec(dataset_id)
    return CausalGraphSpec(
        name=spec.name,
        dataset_id=dataset_id,
        nodes=[
            *spec.nodes,
            {"node_id": "g", "label": "g", "column": "g"},
        ],
        edges=[
            *spec.edges,
            {"source": "g", "target": "t"},
            {"source": "g", "target": "y"},
        ],
        analysis={"treatment": "t", "outcome": "y"},
    )


def test_audit_2_overall_estimate_is_exactly_the_rowweighted_mixture():
    frame = _confounded_frame()
    frame["g"] = np.where(frame["x2"] > 0.0, "High", "Low")
    dataset = _dataset(frame)
    spec = _confounded_spec_with_g(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request(["x1", "x2", "g"])
    payload = run_subgroup_estimation(dataset, record, request, SubgroupSpec("g"))
    groups = [g for g in payload["groups"] if g["status"] == "estimated"]
    n = sum(g["rows"] for g in groups)
    mixture = sum(g["rows"] * g["estimate"] for g in groups) / n
    assert mixture == pytest.approx(payload["overall"]["estimate"], abs=1e-9)


def test_audit_3_severe_imbalance_and_degenerate_groups_are_honest():
    """90/10 treatment split still estimates; a group with <10 per arm is
    unavailable, never fabricated."""
    frame = _randomised_frame(n=1000, treat_share=0.9, seed=SEED + 2)
    frame["g"] = np.where(frame["x1"] > np.quantile(frame["x1"], 0.98), "tiny", "rest")
    dataset = _dataset(frame)
    spec = CausalGraphSpec(
        name="Audit imbalance graph",
        dataset_id=dataset.dataset_id,
        nodes=[
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "x2", "label": "x2", "column": "x2"},
            {"node_id": "g", "label": "g", "column": "g"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        edges=[
            {"source": "x1", "target": "y"}, {"source": "x2", "target": "y"},
            {"source": "t", "target": "y"},
        ],
        analysis={"treatment": "t", "outcome": "y"},
    )
    record = _record(dataset, spec)
    request = _request(["x1", "x2"])
    payload = run_subgroup_estimation(dataset, record, request, SubgroupSpec("g"))
    tiny = next(g for g in payload["groups"] if g["label"] == "tiny")
    rest = next(g for g in payload["groups"] if g["label"] == "rest")
    # The 'tiny' group has ~20 rows: far below 10 per arm in expectation.
    if tiny["treated_rows"] < 10 or tiny["control_rows"] < 10:
        assert tiny["status"] == "unavailable"
        assert tiny["estimate"] is None
        assert "No estimate was fabricated" in tiny["unavailable_reason"]
    else:
        assert tiny["status"] == "estimated"
    assert rest["status"] == "estimated"
    assert rest["estimate"] == pytest.approx(1.5, abs=0.4)


def test_audit_4_numeric_binned_subgroups_recover_known_quantile_effects():
    """Effects that step across x1 quartiles are recovered per quartile bin."""
    rng = np.random.default_rng(SEED + 3)
    n = 1600
    x1 = rng.normal(0.0, 1.0, n)
    x2 = rng.normal(0.0, 1.0, n)
    t = rng.binomial(1, 0.5, n)
    q1, q2, q3 = np.quantile(x1, [0.25, 0.5, 0.75])
    effect = np.where(x1 < q1, 0.4, np.where(x1 < q2, 0.8, np.where(x1 < q3, 1.2, 1.6)))
    y = effect * t + 0.5 * x2 + rng.normal(0.0, 1.0, n)
    frame = pd.DataFrame({"x1": x1, "x2": x2, "t": t, "y": y})
    dataset = _dataset(frame)
    spec = CausalGraphSpec(
        name="Audit numeric bins graph",
        dataset_id=dataset.dataset_id,
        nodes=[
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "x2", "label": "x2", "column": "x2"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        edges=[
            {"source": "x2", "target": "y"}, {"source": "t", "target": "y"},
        ],
        analysis={"treatment": "t", "outcome": "y"},
    )
    record = _record(dataset, spec)
    request = _request(["x2"])
    payload = run_subgroup_estimation(dataset, record, request, SubgroupSpec("x1", numeric_binning="quartile"))
    estimated = [g for g in payload["groups"] if g["status"] == "estimated"]
    assert len(estimated) == 4
    expected = [0.4, 0.8, 1.2, 1.6]
    for group, truth in zip(estimated, expected, strict=True):
        assert group["estimate"] == pytest.approx(truth, abs=0.3)
    assert payload["subgroup"]["bin_edges"] is not None
    assert len(payload["subgroup"]["bin_edges"]) == 5
    assert any(note["code"] == "multiple_comparisons" for note in payload["notes"])


# --------------------------------------------------------------------------- #
# 2. Estimator-level algebra on a randomised design (exact answers)
# --------------------------------------------------------------------------- #


def test_audit_5_ipw_hajek_matches_exact_closed_form_on_randomised_design():
    """With no adjustment set, the propensity is intercept-only and Hájek IPW
    has an exact algebraic answer: per-arm mean difference with the IF SE."""
    frame = _randomised_frame(seed=SEED + 4)
    dataset = _dataset(frame)
    spec = _randomised_spec(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request([])
    payload = run_estimation(dataset, record, request, estimator_names=["ipw", "aipw"])
    ipw = next(r for r in payload["results"] if r["estimator"] == "ipw")
    expected = _independent_hajek_ipw(frame["t"].to_numpy(float), frame["y"].to_numpy(float))
    assert ipw["status"] == "estimated"
    assert ipw["estimate"] == pytest.approx(expected["ate"], abs=1e-9)
    assert ipw["treated_mean"] == pytest.approx(expected["mu1"], abs=1e-9)
    assert ipw["control_mean"] == pytest.approx(expected["mu0"], abs=1e-9)
    uncertainty = ipw["uncertainty"]
    assert uncertainty["standard_error"] == pytest.approx(expected["se"], abs=1e-9)


def test_audit_6_subgroup_engine_consumes_the_same_estimating_equation_as_the_studio():
    """The subgroup stage is documented to rebuild the stored estimation run's
    estimating equation. Under one fixed seed the cross-fitting folds are
    identical, so the subgroup payload's overall estimate must equal the
    estimation studio's AIPW ATE exactly (to numerical rounding), and the
    fold structure recorded by both must agree."""
    frame = _confounded_frame(seed=SEED + 5)
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request(["x1", "x2"])
    estimation = run_estimation(dataset, record, request, estimator_names=["aipw"])
    aipw = next(r for r in estimation["results"] if r["estimator"] == "aipw")
    assert aipw["status"] == "estimated"

    subgroup = run_subgroup_estimation(dataset, record, request, SubgroupSpec("x1", numeric_binning="median"))
    # Same seed, same folds, same estimating equation: the cohort-level AIPW
    # ATE and the subgroup payload's overall estimate coincide.
    assert subgroup["overall"]["estimate"] == pytest.approx(aipw["estimate"], abs=1e-9)
    assert subgroup["overall"]["standard_error"] == pytest.approx(aipw["uncertainty"]["standard_error"], rel=1e-9)
    assert subgroup["analysis"]["rows_final"] == estimation["analysis"]["rows_final"]
    assert (
        subgroup["reproducibility"]["cross_fitting"] == estimation["reproducibility"]["cross_fitting"]
    )


# --------------------------------------------------------------------------- #
# 3. Robustness experiments vs independent recomputation
# --------------------------------------------------------------------------- #


def test_audit_7_sensitivity_grid_cells_match_statsmodels_gcomputation():
    """Every (γ, κ) cell for regression_adjustment is re-fit with statsmodels
    OLS — a different library and pipeline than production — after
    re-simulating U from the documented generating model and the recorded seed."""
    frame = _confounded_frame(n=600, seed=SEED + 6)
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request(["x1", "x2"], seed=77_001)
    payload = run_robustness_experiment(dataset, record, request, "unmeasured_confounder", ConfounderSpec("regression_adjustment", prevalence=0.3))
    grid = payload["result"]["grid"]
    gammas = RobustnessLimits.SENSITIVITY_GAMMA_VALUES
    kappas = RobustnessLimits.SENSITIVITY_KAPPA_VALUES
    treatment = frame["t"].to_numpy(float)
    outcome = frame["y"].to_numpy(float)
    outcome_sd = float(np.std(outcome))
    prevalence = 0.3
    for gamma_index, gamma in enumerate(gammas):
        for kappa_index, kappa in enumerate(kappas):
            rng = np.random.default_rng([77_001, gamma_index, kappa_index])
            outcome_z = (outcome - np.mean(outcome)) / outcome_sd
            logit_u = np.log(prevalence / (1 - prevalence)) + gamma * treatment + kappa * outcome_z
            probability = 1.0 / (1.0 + np.exp(-logit_u))
            simulated = (rng.random(len(treatment)) < probability).astype(float)
            extended = frame[["x1", "x2"]].copy()
            extended["u"] = simulated
            independent = _independent_ols_gcomputation(
                extended.assign(u=simulated), treatment, outcome, ["x1", "x2", "u"]
            )
            produced = grid[gamma_index][kappa_index]
            assert produced is not None
            assert produced == pytest.approx(independent, abs=1e-7), (gamma, kappa, produced, independent)


def test_audit_8_placebo_permutations_preserve_the_treated_count_and_recenter():
    frame = _randomised_frame(seed=SEED + 7)
    dataset = _dataset(frame)
    spec = _randomised_spec(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request(["x1", "x2"], seed=77_002)
    payload = run_robustness_experiment(dataset, record, request, "placebo", PlaceboSpec("regression_adjustment", reps=150))
    result = payload["result"]
    assert result["parameters"]["permuted_treated_rows"] == int(frame["t"].sum())
    # Deterministic re-run from the same seed reproduces the exact series.
    rerun = run_robustness_experiment(dataset, record, request, "placebo", PlaceboSpec("regression_adjustment", reps=150))
    assert rerun["result"]["estimates"] == result["estimates"]
    # Placebo on a randomised no-structure permutation centres near zero.
    placebo_mean = float(np.mean(result["estimates"]))
    placebo_sd = float(np.std(result["estimates"], ddof=1)) or 1.0
    assert abs(placebo_mean) < 3 * placebo_sd / np.sqrt(len(result["estimates"])) * 3


def test_audit_9_subsampling_first_repetition_is_traceable_to_the_recorded_seed():
    """Re-draw repetition 0 from [seed, 0] and re-estimate with the independent
    machinery; the first recorded subsample estimate must match."""
    frame = _confounded_frame(n=600, seed=SEED + 8)
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id)
    record = _record(dataset, spec)
    seed = 77_003
    request = _request(["x1", "x2"], seed=seed)
    payload = run_robustness_experiment(
        dataset, record, request, "subsampling", SubsamplingSpec("regression_adjustment", reps=120, fraction=0.5)
    )
    estimates = payload["result"]["estimates"]
    assert len(estimates) >= 100
    rng = np.random.default_rng([seed, 0])
    n = len(frame)
    indices = rng.choice(n, size=int(round(0.5 * n)), replace=False)
    sub = frame.iloc[np.sort(indices)].reset_index(drop=True)
    independent = _independent_ols_gcomputation(sub, sub["t"].to_numpy(float), sub["y"].to_numpy(float), ["x1", "x2"])
    assert estimates[0] == pytest.approx(independent, abs=1e-7)


def test_audit_10_sensitivity_null_cell_matches_original_and_grid_reacts():
    frame = _confounded_frame(n=600, seed=SEED + 9)
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request(["x1", "x2"], seed=77_004)
    payload = run_robustness_experiment(
        dataset, record, request, "unmeasured_confounder", ConfounderSpec("regression_adjustment", prevalence=0.3)
    )
    grid = payload["result"]["grid"]
    original = payload["original"]["estimate"]
    # (0,0) cell: an outcome/treatment-orthogonal noise draw sits near the original.
    assert abs(grid[0][0] - original) < 0.15
    # The grid actually reacts to the scenario parameters (not ignored):
    # the strongest simulated confounding cell differs from the null cell.
    flat = [cell for row in grid for cell in row if cell is not None]
    assert max(flat) - min(flat) > 0.01
    assert payload["result"]["warnings"] and "not a bound" in payload["result"]["warnings"][0]


# --------------------------------------------------------------------------- #
# 4. What-if vs hand-derived OLS predictions (noise-free linear DGP)
# --------------------------------------------------------------------------- #


def test_audit_11_whatif_profile_predictions_match_hand_derived_ols():
    """Noise-free linear DGP: y = 2.0 + 1.5·t + 0.8·x. OLS recovers the
    generating coefficients exactly, so the scenario predictions are known."""
    rng = np.random.default_rng(SEED + 10)
    n = 400
    x = rng.uniform(-2.0, 2.0, n)
    t = rng.binomial(1, 0.5, n)
    y = 2.0 + 1.5 * t + 0.8 * x
    frame = pd.DataFrame({"x": x, "t": t, "y": y})
    dataset = _dataset(frame)
    spec = CausalGraphSpec(
        name="Audit whatif graph",
        dataset_id=dataset.dataset_id,
        nodes=[
            {"node_id": "x", "label": "x", "column": "x"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        edges=[{"source": "x", "target": "y"}, {"source": "t", "target": "y"}],
        analysis={"treatment": "t", "outcome": "y"},
    )
    record = _record(dataset, spec)
    request = _request(["x"])
    payload = run_what_if(dataset, record, request, {"x": 1.25})
    # Hand-derived: at x=1.25, m(1) = 2.0 + 1.5 + 0.8*1.25, m(0) = 2.0 + 0.8*1.25.
    expected_treated = 2.0 + 1.5 + 0.8 * 1.25
    expected_control = 2.0 + 0.8 * 1.25
    scenario = payload["profile_scenario"]
    assert scenario["treated_prediction"] == pytest.approx(expected_treated, abs=1e-6)
    assert scenario["control_prediction"] == pytest.approx(expected_control, abs=1e-6)
    assert scenario["contrast"] == pytest.approx(1.5, abs=1e-6)
    # Cohort-standardised contrast equals the g-computation ATE: exactly 1.5.
    assert payload["cohort_scenario"]["contrast"] == pytest.approx(1.5, abs=1e-6)
    assert payload["model_specification"]["uncertainty"] is not None
    assert "no interval" in payload["model_specification"]["uncertainty"].lower() or "none is reported" in payload["model_specification"]["uncertainty"].lower()


def test_audit_12_whatif_refuses_post_treatment_and_cross_cohort_profiles():
    frame = _confounded_frame(n=400, seed=SEED + 11)
    dataset = _dataset(frame)
    spec = _confounded_spec(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request(["x1", "x2"])
    # The outcome column can never be set in a profile.
    with pytest.raises(ValidationFailure):
        run_what_if(dataset, record, request, {"y": 3.0})
    with pytest.raises(ValidationFailure):
        run_what_if(dataset, record, request, {"t": 1})
    with pytest.raises(ValidationFailure):
        run_what_if(dataset, record, request, {"not_a_covariate": 1.0})


# --------------------------------------------------------------------------- #
# 5. Determinism and disclosure audits
# --------------------------------------------------------------------------- #


def test_audit_13_subgroup_and_robustness_runs_reproduce_bitwise_under_fixed_seeds():
    frame = _confounded_frame(seed=SEED + 12)
    frame["g"] = np.where(frame["x1"] > 0.0, "A", "B")
    dataset = _dataset(frame)
    spec = _confounded_spec_with_g(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request(["x1", "x2", "g"], seed=88_001)
    first = run_subgroup_estimation(dataset, record, request, SubgroupSpec("g"))
    second = run_subgroup_estimation(dataset, record, request, SubgroupSpec("g"))
    assert first["groups"] == second["groups"]
    assert first["contrasts"] == second["contrasts"]
    robust_first = run_robustness_experiment(
        dataset, record, request, "subsampling", SubsamplingSpec("aipw", reps=100, fraction=0.6)
    )
    robust_second = run_robustness_experiment(
        dataset, record, request, "subsampling", SubsamplingSpec("aipw", reps=100, fraction=0.6)
    )
    assert robust_first["result"]["estimates"] == robust_second["result"]["estimates"]
    assert robust_first["result"]["failures"] == robust_second["result"]["failures"]


def test_audit_14_contrast_intervals_use_the_recorded_level_and_normal_quantile():
    frame = _confounded_frame(seed=SEED + 13)
    frame["g"] = np.where(frame["x1"] > 0.0, "A", "B")
    dataset = _dataset(frame)
    spec = _confounded_spec_with_g(dataset.dataset_id)
    record = _record(dataset, spec)
    for level in (0.90, 0.95, 0.99):
        request = _request(["x1", "x2", "g"], seed=88_002)
        request.uncertainty.level = level
        payload = run_subgroup_estimation(dataset, record, request, SubgroupSpec("g"))
        estimated = [g for g in payload["groups"] if g["status"] == "estimated"]
        assert len(estimated) == 2
        a, b = estimated
        z = float(scipy_stats.norm.ppf(1.0 - (1.0 - level) / 2.0))
        contrast = payload["contrasts"][0]
        expected_se = float(np.sqrt(a["standard_error"] ** 2 + b["standard_error"] ** 2))
        assert contrast["standard_error"] == pytest.approx(expected_se, rel=1e-9)
        assert contrast["ci_lower"] == pytest.approx(contrast["difference"] - z * expected_se, abs=1e-12)
        assert contrast["ci_upper"] == pytest.approx(contrast["difference"] + z * expected_se, abs=1e-12)
        for group in (a, b):
            assert group["ci_lower"] == pytest.approx(group["estimate"] - z * group["standard_error"], abs=1e-12)
            assert group["ci_upper"] == pytest.approx(group["estimate"] + z * group["standard_error"], abs=1e-12)


def test_audit_15_every_payload_is_json_serialisable_and_records_reproducibility():
    import json

    frame = _confounded_frame(n=500, seed=SEED + 14)
    frame["g"] = np.where(frame["x1"] > 0.0, "A", "B")
    dataset = _dataset(frame)
    spec = _confounded_spec_with_g(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request(["x1", "x2", "g"], seed=88_003)

    subgroup = run_subgroup_estimation(dataset, record, request, SubgroupSpec("g"))
    robustness = run_robustness_experiment(
        dataset, record, request, "subsampling", SubsamplingSpec("aipw", reps=100, fraction=0.5)
    )
    whatif = run_what_if(dataset, record, request, {"x1": 0.5})
    for payload in (subgroup, robustness, whatif):
        serialised = json.dumps(payload)  # NaN/Infinity would raise here
        assert isinstance(serialised, str)
        repro = payload["reproducibility"]
        assert repro["dataset_fingerprint_sha256"] == dataset.fingerprint_sha256
        assert repro["graph_spec_fingerprint_sha256"] == record.fingerprint
        assert repro["software_versions"]["python"]
        assert repro["uncertainty"]["resolved_seed"] is not None
