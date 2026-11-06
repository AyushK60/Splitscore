"""S9C-B robustness experiments: reproducibility, failure honesty, boundaries.

Every experiment must be reproducible from its recorded seed, must report
failures per repetition instead of averaging them away, and must refuse
out-of-bounds parameters up front. The original estimate is cross-checked
against the verified S9A engine (run_estimation), so the robustness layer is
never its own oracle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.audit.dataset import Dataset
from app.causal.estimation.contracts import EstimationRequest
from app.causal.estimation.robustness import (
    ConfounderSpec,
    PlaceboSpec,
    SubsamplingSpec,
    run_robustness_experiment,
)
from app.causal.estimation.service import run_estimation
from app.causal.registry import CausalGraphRecord
from app.causal.schema import CausalGraphSpec
from app.core.errors import ValidationFailure

from .conftest import make_dataset

N = 600
SEED = 991


def _frame(effect: float = 1.5, n: int = N, seed: int = SEED) -> pd.DataFrame:
    """Confounded DGP with a known constant effect (no subgroup structure)."""
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0.0, 1.0, n)
    x2 = rng.normal(0.0, 1.0, n)
    propensity = 1.0 / (1.0 + np.exp(-(0.8 * x1 - 0.5 * x2)))
    t = rng.binomial(1, propensity)
    y = effect * t + 0.9 * x1 - 0.7 * x2 + rng.normal(0.0, 1.0, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "t": t, "y": y})


def _dataset(frame: pd.DataFrame) -> Dataset:
    return make_dataset(frame.to_dict("records"), name="robustness-fixture.csv")


_SPEC = CausalGraphSpec(
    name="Robustness fixture graph",
    dataset_id="will-be-set",
    nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "x2", "label": "x2", "column": "x2"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ],
    edges=[
        {"source": "x1", "target": "t"},
        {"source": "x1", "target": "y"},
        {"source": "x2", "target": "t"},
        {"source": "x2", "target": "y"},
        {"source": "t", "target": "y"},
    ],
    analysis={"treatment": "t", "outcome": "y"},
)


def _request(dataset: Dataset, spec: CausalGraphSpec) -> EstimationRequest:
    return EstimationRequest(
        treatment_node="t",
        outcome_node="y",
        adjustment_nodes=["x1", "x2"],
        treatment_mapping={"treated": "1", "control": "0"},
        uncertainty={"method": "influence_function", "reps": 100, "seed": SEED, "level": 0.95},
        expected_spec_fingerprint_sha256=None,
    )


def _record(dataset: Dataset, spec: CausalGraphSpec) -> CausalGraphRecord:
    return CausalGraphRecord(
        graph_id="cgraph-robustness-fixture",
        dataset_id=dataset.dataset_id,
        dataset_fingerprint_sha256=dataset.fingerprint_sha256,
        spec=spec,
        revision=1,
    )


def _run(frame: pd.DataFrame, experiment: str, spec) -> dict:
    dataset = _dataset(frame)
    spec_graph = _SPEC.model_copy(update={"dataset_id": dataset.dataset_id})
    record = _record(dataset, spec_graph)
    request = _request(dataset, spec_graph)
    return run_robustness_experiment(dataset, record, request, experiment, spec)


# --------------------------------------------------------------------------- #
# Subsampling
# --------------------------------------------------------------------------- #


def test_case_1_subsampling_is_reproducible_from_the_recorded_seed():
    first = _run(_frame(), "subsampling", SubsamplingSpec(estimator="ipw", reps=120))
    second = _run(_frame(), "subsampling", SubsamplingSpec(estimator="ipw", reps=120))
    assert first["result"]["estimates"] == second["result"]["estimates"]
    assert first["reproducibility"]["uncertainty"]["resolved_seed"] == (
        second["reproducibility"]["uncertainty"]["resolved_seed"]
    )


def test_case_2_subsampling_variation_covers_the_original_estimate():
    payload = _run(_frame(), "subsampling", SubsamplingSpec(estimator="ipw", reps=150))
    result = payload["result"]
    assert result["distribution"] is not None
    original = payload["original"]["estimate"]
    assert original is not None
    # ~50% subsamples are noisier than the full cohort, but the original
    # estimate should sit inside the bulk of their distribution.
    assert result["distribution"]["q05"] - 0.3 <= original <= result["distribution"]["q95"] + 0.3
    assert result["distribution"]["standard_deviation"] > 0


def test_case_3_subsampling_bounds_are_enforced():
    with pytest.raises(ValidationFailure):
        _run(_frame(), "subsampling", SubsamplingSpec(reps=50))
    with pytest.raises(ValidationFailure):
        _run(_frame(), "subsampling", SubsamplingSpec(fraction=0.02))


def test_case_4_subsampling_failures_are_recorded_not_averaged():
    # 11 treated rows out of 200 clears the full-cohort minimum, but 10%
    # subsamples (20 rows) frequently contain no treated row at all, where the
    # Hájek estimator is undefined and must fail honestly per repetition.
    rng = np.random.default_rng(3)
    n = 200
    t = np.zeros(n, dtype=int)
    t[rng.choice(n, size=11, replace=False)] = 1
    frame = pd.DataFrame(
        {
            "x1": rng.normal(size=n),
            "x2": rng.normal(size=n),
            "t": t,
            "y": 1.0 * t + rng.normal(size=n),
        }
    )
    payload = _run(frame, "subsampling", SubsamplingSpec(estimator="ipw", reps=150, fraction=0.1))
    result = payload["result"]
    assert len(result["failures"]) > 0
    for failure in result["failures"]:
        assert "reason" in failure
    # Successful repetitions still produced a distribution; failed ones never
    # contributed a number.
    assert len(result["estimates"]) == 150 - len(result["failures"])


# --------------------------------------------------------------------------- #
# Placebo
# --------------------------------------------------------------------------- #


def test_case_5_placebo_is_reproducible():
    first = _run(_frame(), "placebo", PlaceboSpec(estimator="regression_adjustment", reps=120))
    second = _run(_frame(), "placebo", PlaceboSpec(estimator="regression_adjustment", reps=120))
    assert first["result"]["estimates"] == second["result"]["estimates"]


def test_case_6_placebo_distribution_centers_near_zero_for_randomized_data():
    # No confounding, no effect: placebo estimates are pure estimator noise.
    rng = np.random.default_rng(21)
    n = 400
    frame = pd.DataFrame(
        {
            "x1": rng.normal(size=n),
            "x2": rng.normal(size=n),
            "t": rng.binomial(1, 0.5, n),
            "y": rng.normal(size=n),
        }
    )
    payload = _run(frame, "placebo", PlaceboSpec(estimator="regression_adjustment", reps=150))
    distribution = payload["result"]["distribution"]
    assert abs(distribution["mean"]) < 0.2
    assert distribution["q05"] <= 0 <= distribution["q95"]


def test_case_7_original_estimate_matches_the_verified_engine():
    frame = _frame()
    payload = _run(frame, "placebo", PlaceboSpec(estimator="regression_adjustment", reps=100))
    dataset = _dataset(frame)
    spec_graph = _SPEC.model_copy(update={"dataset_id": dataset.dataset_id})
    request = _request(dataset, spec_graph)
    engine = run_estimation(
        dataset,
        _record(dataset, spec_graph),
        request,
        estimator_names=["regression_adjustment"],
    )
    engine_estimate = next(
        result["estimate"]
        for result in engine["results"]
        if result["estimator"] == "regression_adjustment"
    )
    assert payload["original"]["estimate"] == pytest.approx(engine_estimate, abs=1e-12)


# --------------------------------------------------------------------------- #
# Hypothetical unmeasured confounder
# --------------------------------------------------------------------------- #


def test_case_8_sensitivity_null_cell_matches_original():
    payload = _run(_frame(), "unmeasured_confounder", ConfounderSpec(estimator="regression_adjustment"))
    result = payload["result"]
    assert len(result["grid"]) == 5 and all(len(row) == 5 for row in result["grid"])
    original = payload["original"]["estimate"]
    null_cell = result["grid"][0][0]
    assert null_cell is not None
    # A treatment/outcome-orthogonal U can only move a linear fit slightly.
    assert abs(null_cell - original) < 0.15


def test_case_9_sensitivity_is_reproducible():
    first = _run(_frame(), "unmeasured_confounder", ConfounderSpec(estimator="regression_adjustment"))
    second = _run(_frame(), "unmeasured_confounder", ConfounderSpec(estimator="regression_adjustment"))
    assert first["result"]["grid"] == second["result"]["grid"]


def test_case_10_sensitivity_grid_carries_the_scenario_caveat():
    payload = _run(_frame(), "unmeasured_confounder", ConfounderSpec())
    assert any("not a bound" in warning for warning in payload["result"]["warnings"])
    assert any("scenario" in warning for warning in payload["result"]["warnings"])


def test_case_11_sensitivity_prevalence_bounds_are_enforced():
    with pytest.raises(ValidationFailure):
        _run(_frame(), "unmeasured_confounder", ConfounderSpec(prevalence=0.01))
    with pytest.raises(ValidationFailure):
        _run(_frame(), "unmeasured_confounder", ConfounderSpec(prevalence=0.99))


def test_case_12_unknown_experiment_is_refused():
    with pytest.raises(ValidationFailure):
        _run(_frame(), "astrology", SubsamplingSpec())
