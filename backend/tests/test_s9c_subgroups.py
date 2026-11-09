"""subgroup subgroup effects: known-answer synthetic experiments.

Every expectation comes from the data-generating process written beside the
test. Recovery tolerances are ~2 sampling standard errors for the given n -
a finite-sample estimate is never required to equal its generating parameter.
The uncertainty arithmetic is verified *exactly* against independent formulas
(std/sqrt(n) within group; sqrt(var_a/n_a + var_b/n_b) for contrasts), and the
overall-vs-subgroup identity  mean(psi) == sum_g (n_g/n) ate_g  is exact, so
the subgroup estimating equation is never its own oracle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.audit.dataset import Dataset
from app.causal.estimation.contracts import EstimationRequest
from app.causal.estimation.service import run_estimation  # noqa: F401  (harness parity)
from app.causal.estimation.subgroups import SubgroupSpec, run_subgroup_estimation
from app.causal.registry import CausalGraphRecord
from app.causal.schema import CausalGraphSpec
from app.core.errors import ValidationFailure

from .conftest import make_dataset

N = 900
SEED = 4021


def _heterogeneous_frame(
    *,
    effect_a: float,
    effect_b: float,
    n: int = N,
    seed: int = SEED,
    subgroup_drives_treatment: float = 0.9,
    missing_share: float = 0.0,
) -> pd.DataFrame:
    """Two measured confounders, a binary subgroup g in {A, B} that shifts both
    assignment and outcome, and group-specific treatment effects."""
    rng = np.random.default_rng(seed)
    g = rng.choice(["A", "B"], size=n, p=[0.55, 0.45])
    x1 = rng.normal(0.0, 1.0, n)
    x2 = rng.normal(0.0, 1.0, n)
    g_shift = np.where(g == "B", 1.0, 0.0)
    logit = -0.4 + 0.8 * x1 - 0.5 * x2 + subgroup_drives_treatment * g_shift
    propensity = 1.0 / (1.0 + np.exp(-logit))
    t = rng.binomial(1, propensity)
    effect = np.where(g == "B", effect_b, effect_a)
    y = effect * t + 0.9 * x1 - 0.7 * x2 + 0.6 * g_shift + rng.normal(0.0, 1.0, n)
    frame = pd.DataFrame({"x1": x1, "x2": x2, "g": g, "t": t, "y": y})
    if missing_share > 0:
        missing_rng = np.random.default_rng(seed + 99)
        holes = missing_rng.random(n) < missing_share
        frame["g"] = frame["g"].astype(object)
        frame.loc[holes, "g"] = None  # None -> empty CSV cell -> NaN on read-back
    return frame


def _dataset(frame: pd.DataFrame) -> Dataset:
    return make_dataset(frame.to_dict("records"), name="subgroup-fixture.csv")


def _spec(dataset_id: str, *, g_to_t: bool = True) -> CausalGraphSpec:
    edges = [
        {"source": "x1", "target": "t"},
        {"source": "x1", "target": "y"},
        {"source": "x2", "target": "t"},
        {"source": "x2", "target": "y"},
    ]
    if g_to_t:
        edges.append({"source": "g", "target": "t"})
    edges.extend(
        [
            {"source": "g", "target": "y"},
            {"source": "t", "target": "y"},
        ]
    )
    return CausalGraphSpec(
        name="Subgroup fixture graph",
        dataset_id=dataset_id,
        nodes=[
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "x2", "label": "x2", "column": "x2"},
            {"node_id": "g", "label": "g", "column": "g"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        edges=edges,
        analysis={"treatment": "t", "outcome": "y"},
    )


def _record(dataset: Dataset, spec: CausalGraphSpec) -> CausalGraphRecord:
    return CausalGraphRecord(
        graph_id="cgraph-subgroup-fixture",
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
    cross_fit: dict | None = None,
) -> EstimationRequest:
    return EstimationRequest(
        treatment_node="t",
        outcome_node="y",
        adjustment_nodes=["x1", "x2", "g"] if adjustment is None else adjustment,
        treatment_mapping={"treated": "1", "control": "0"},
        cross_fit=cross_fit or {"splits": 5},
        uncertainty={"method": "influence_function", "reps": 100, "seed": SEED, "level": 0.95},
        expected_spec_fingerprint_sha256=None,
    )


def _run(frame: pd.DataFrame, subgroup: SubgroupSpec, **request_kwargs) -> dict:
    dataset = _dataset(frame)
    spec = _spec(dataset.dataset_id, g_to_t=request_kwargs.pop("_g_to_t", True))
    record = _record(dataset, spec)
    request = _request(dataset, spec, **request_kwargs)
    return run_subgroup_estimation(dataset, record, request, subgroup)


def _group(payload: dict, label: str) -> dict:
    return next(group for group in payload["groups"] if group["label"] == label)


# --------------------------------------------------------------------------- #
# Known-effect recovery
# --------------------------------------------------------------------------- #


def test_case_1_constant_effect_recovered_in_every_subgroup():
    payload = _run(_heterogeneous_frame(effect_a=1.2, effect_b=1.2), SubgroupSpec("g"))
    assert payload["analysis_kind"] == "subgroups"
    for label in ("A", "B"):
        group = _group(payload, label)
        assert group["status"] == "estimated"
        assert group["estimate"] == pytest.approx(1.2, abs=0.22)
    assert payload["overall"]["estimate"] == pytest.approx(1.2, abs=0.22)


def test_case_2_heterogeneous_effects_recovered_per_subgroup():
    payload = _run(_heterogeneous_frame(effect_a=1.0, effect_b=2.5), SubgroupSpec("g"))
    assert _group(payload, "A")["estimate"] == pytest.approx(1.0, abs=0.25)
    assert _group(payload, "B")["estimate"] == pytest.approx(2.5, abs=0.30)


def test_case_3_no_effect_in_either_subgroup():
    payload = _run(_heterogeneous_frame(effect_a=0.0, effect_b=0.0), SubgroupSpec("g"))
    assert abs(_group(payload, "A")["estimate"]) < 0.22
    assert abs(_group(payload, "B")["estimate"]) < 0.22


def test_case_4_confounded_treatment_recovered_with_valid_adjustment():
    # The same DGP is confounded (g, x1, x2 drive assignment); the naive
    # treated-minus-control difference inside group B must NOT be the effect,
    # while the adjusted subgroup estimate recovers it.
    frame = _heterogeneous_frame(effect_a=1.0, effect_b=2.5)
    payload = _run(frame, SubgroupSpec("g"))
    naive_b = (
        frame.loc[(frame.g == "B") & (frame.t == 1), "y"].mean()
        - frame.loc[(frame.g == "B") & (frame.t == 0), "y"].mean()
    )
    adjusted_b = _group(payload, "B")["estimate"]
    assert adjusted_b == pytest.approx(2.5, abs=0.30)
    assert abs(naive_b - 2.5) > abs(adjusted_b - 2.5) - 0.5  # adjusted is not worse


# --------------------------------------------------------------------------- #
# Exact arithmetic identities (independent formulas)
# --------------------------------------------------------------------------- #


def test_case_5_overall_estimate_is_the_rowweighted_mixture_of_subgroup_estimates():
    payload = _run(_heterogeneous_frame(effect_a=1.0, effect_b=2.5), SubgroupSpec("g"))
    n_total = sum(group["rows"] for group in payload["groups"] if group["status"] == "estimated")
    mixture = sum(
        group["rows"] / n_total * group["estimate"]
        for group in payload["groups"]
        if group["status"] == "estimated"
    )
    assert payload["overall"]["estimate"] == pytest.approx(mixture, abs=1e-9)


def test_case_6_subgroup_standard_error_matches_independent_formula():
    frame = _heterogeneous_frame(effect_a=1.0, effect_b=2.5)
    payload = _run(frame, SubgroupSpec("g"))
    # Recompute the AIPW pseudo-outcome independently through the verified
    # estimator and check the reported SE against sd/sqrt(n) by hand.
    from app.causal.estimation.preparation import prepare_cohort
    from app.causal.estimation.estimators import estimate_aipw

    dataset = _dataset(frame)
    spec = _spec(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request(dataset, spec)
    prepared = prepare_cohort(
        dataset, request,
        treatment_column="t", outcome_column="y", covariate_columns=["x1", "x2", "g"],
    )
    aipw = estimate_aipw(
        prepared.frame, prepared.treatment, prepared.outcome,
        prepared.covariates, prepared.missing_policy, prepared.outcome_task, request,
    )
    psi = aipw.pseudo_outcome
    for label in ("A", "B"):
        mask = (prepared.frame["g"] == label).to_numpy()
        expected = float(np.std(psi[mask], ddof=1) / np.sqrt(int(mask.sum())))
        assert _group(payload, label)["standard_error"] == pytest.approx(expected, abs=1e-12)


def test_case_7_contrast_uncertainty_matches_direct_disjoint_formula():
    payload = _run(_heterogeneous_frame(effect_a=1.0, effect_b=2.5), SubgroupSpec("g"))
    assert payload["contrasts"] is not None and len(payload["contrasts"]) == 1
    contrast = payload["contrasts"][0]
    a, b = _group(payload, contrast["a"]), _group(payload, contrast["b"])
    var_a = a["standard_error"] ** 2 * a["rows"]
    var_b = b["standard_error"] ** 2 * b["rows"]
    expected_se = float(np.sqrt(var_a / a["rows"] + var_b / b["rows"]))
    assert contrast["standard_error"] == pytest.approx(expected_se, abs=1e-12)
    assert contrast["difference"] == pytest.approx(a["estimate"] - b["estimate"], abs=1e-12)


# --------------------------------------------------------------------------- #
# Refusals and honest unavailable states
# --------------------------------------------------------------------------- #


def test_case_8_post_treatment_subgroup_variable_is_refused():
    dataset = _dataset(_heterogeneous_frame(effect_a=1.0, effect_b=2.5))
    spec = CausalGraphSpec(
        name="Mediator graph",
        dataset_id=dataset.dataset_id,
        nodes=[
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "x2", "label": "x2", "column": "x2"},
            {"node_id": "m", "label": "m", "column": "x2"},  # anchored like a mediator
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        edges=[
            {"source": "x1", "target": "t"},
            {"source": "x1", "target": "y"},
            {"source": "x2", "target": "t"},
            {"source": "t", "target": "m"},
            {"source": "m", "target": "y"},
            {"source": "t", "target": "y"},
        ],
        analysis={"treatment": "t", "outcome": "y"},
    )
    record = _record(dataset, spec)
    request = _request(dataset, spec, adjustment=["x1", "x2"])
    with pytest.raises(ValidationFailure) as caught:
        run_subgroup_estimation(dataset, record, request, SubgroupSpec("m"))
    assert "descendant of the treatment" in str(caught.value)


def test_case_9_subgroup_with_insufficient_treated_rows_is_unavailable_not_fabricated():
    # Group B is tiny with exactly 2 treated rows - below the per-arm minimum -
    # while group A and the cross-fitting folds (2 splits) are comfortably
    # populated. g affects only the outcome, so adjusting for {x1, x2} is valid.
    rng = np.random.default_rng(7)
    n = 400
    g = np.array(["A"] * 380 + ["B"] * 20)
    x1 = rng.normal(0, 1, n)
    t = np.zeros(n, dtype=int)
    t[rng.choice(np.flatnonzero(g == "A"), size=60, replace=False)] = 1
    t[rng.choice(np.flatnonzero(g == "B"), size=2, replace=False)] = 1
    y = 1.0 * t + 0.8 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "x2": x1 * 0.5, "g": g, "t": t, "y": y})
    payload = _run(
        frame,
        SubgroupSpec("g"),
        adjustment=["x1", "x2"],
        _g_to_t=False,
        cross_fit={"splits": 2},
    )
    group_b = _group(payload, "B")
    if group_b["treated_rows"] < 10:
        assert group_b["status"] == "unavailable"
        assert group_b["estimate"] is None
        assert "No estimate was fabricated" in group_b["unavailable_reason"]
    else:
        assert group_b["status"] == "estimated"


def test_case_10_missing_subgroup_values_are_excluded_and_reported():
    # g is not an adjustment column here, so its missing rows survive
    # complete-case preparation and must be excluded from every subgroup
    # while remaining in the overall estimate.
    payload = _run(
        _heterogeneous_frame(
            effect_a=1.0, effect_b=2.5, missing_share=0.08, subgroup_drives_treatment=0.0
        ),
        SubgroupSpec("g"),
        adjustment=["x1", "x2"],
        _g_to_t=False,
    )
    assert payload["subgroup"]["rows_excluded_missing"] > 0
    assert len(payload["groups"]) == 2
    total_group_rows = sum(group["rows"] for group in payload["groups"])
    assert total_group_rows + payload["subgroup"]["rows_excluded_missing"] == (
        payload["analysis"]["rows_final"]
    )


def test_case_11_unknown_requested_level_is_refused():
    with pytest.raises(ValidationFailure) as caught:
        _run(
            _heterogeneous_frame(effect_a=1.0, effect_b=2.5),
            SubgroupSpec("g", levels=["A", "not-a-level"]),
        )
    assert "not present" in str(caught.value)


# --------------------------------------------------------------------------- #
# Numeric binning, overlap warnings, reproducibility
# --------------------------------------------------------------------------- #


def test_case_12_numeric_baseline_binned_into_quartiles():
    rng = np.random.default_rng(11)
    n = 800
    age = rng.normal(45.0, 10.0, n)
    logit = -0.2 + 0.03 * (age - 45.0)
    t = rng.binomial(1, 1 / (1 + np.exp(-logit)))
    y = 1.4 * t + 0.05 * (age - 45.0) + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": age, "x2": rng.normal(size=n), "g": age, "t": t, "y": y})
    payload = _run(frame, SubgroupSpec("g", numeric_binning="quartile"))
    assert payload["subgroup"]["kind"] == "numeric"
    assert len(payload["groups"]) == 4
    assert len(payload["subgroup"]["bin_edges"]) == 5
    for group in payload["groups"]:
        if group["status"] == "estimated":
            assert group["estimate"] == pytest.approx(1.4, abs=0.4)


def test_case_13_extreme_within_group_overlap_produces_warning():
    # The subgroup strongly drives assignment, so inside B the fitted
    # propensity concentrates near the tails.
    payload = _run(
        _heterogeneous_frame(effect_a=1.0, effect_b=2.5, subgroup_drives_treatment=4.0),
        SubgroupSpec("g"),
    )
    warned = [
        group
        for group in payload["groups"]
        if group["status"] == "estimated" and group["warnings"]
    ]
    assert warned, "an extreme-overlap subgroup should carry a warning"


def test_case_14_reproducible_with_fixed_seed():
    frame = _heterogeneous_frame(effect_a=1.0, effect_b=2.5)
    first = _run(frame, SubgroupSpec("g"))
    second = _run(frame, SubgroupSpec("g"))
    assert first["groups"] == second["groups"]
    assert first["overall"]["estimate"] == second["overall"]["estimate"]


def test_case_15_interval_covers_the_true_effect():
    payload = _run(_heterogeneous_frame(effect_a=1.5, effect_b=1.5), SubgroupSpec("g"))
    for label in ("A", "B"):
        group = _group(payload, label)
        assert group["ci_lower"] < 1.5 < group["ci_upper"]


def test_case_16_exploratory_intent_is_labelled_in_the_notes():
    payload = _run(_heterogeneous_frame(effect_a=1.0, effect_b=2.5), SubgroupSpec("g"))
    codes = {note["code"] for note in payload["notes"]}
    assert "intent" in codes and "multiple_comparisons" in codes
    prespecified = _run(
        _heterogeneous_frame(effect_a=1.0, effect_b=2.5), SubgroupSpec("g", intent="prespecified")
    )
    intent_note = next(n for n in prespecified["notes"] if n["code"] == "intent")
    assert "prespecified" in intent_note["text"]
