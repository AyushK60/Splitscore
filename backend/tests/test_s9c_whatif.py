"""S9C-C what-if scenarios: model-based predictions under explicit assumptions.

The scenario service reuses the verified g-computation outcome model, so its
cohort-level contrast must equal the estimation engine's regression-adjustment
ATE exactly, and — because a linear outcome model without interactions gives a
constant treatment contrast — every fully numeric profile scenario must agree
with that same number. No interval is ever attached to a scenario.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.audit.dataset import Dataset
from app.causal.estimation.contracts import EstimationRequest
from app.causal.estimation.service import run_estimation
from app.causal.estimation.whatif import run_what_if
from app.causal.registry import CausalGraphRecord
from app.causal.schema import CausalGraphSpec
from app.core.errors import ValidationFailure

from .conftest import make_dataset

N = 600
SEED = 77


def _frame(effect: float = 1.5, n: int = N, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0.0, 1.0, n)
    x2 = rng.normal(0.0, 1.0, n)
    region = rng.choice(["north", "south", "east"], size=n, p=[0.4, 0.35, 0.25])
    propensity = 1.0 / (1.0 + np.exp(-(0.8 * x1 - 0.5 * x2 + 0.4 * (region == "south"))))
    t = rng.binomial(1, propensity)
    y = effect * t + 0.9 * x1 - 0.7 * x2 + 0.5 * (region == "south") + rng.normal(0.0, 1.0, n)
    return pd.DataFrame({"x1": x1, "x2": x2, "region": region, "t": t, "y": y})


def _dataset(frame: pd.DataFrame) -> Dataset:
    return make_dataset(frame.to_dict("records"), name="whatif-fixture.csv")


def _spec(dataset_id: str) -> CausalGraphSpec:
    return CausalGraphSpec(
        name="What-if fixture graph",
        dataset_id=dataset_id,
        nodes=[
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "x2", "label": "x2", "column": "x2"},
            {"node_id": "region", "label": "region", "column": "region"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        edges=[
            {"source": "x1", "target": "t"},
            {"source": "x1", "target": "y"},
            {"source": "x2", "target": "t"},
            {"source": "x2", "target": "y"},
            {"source": "region", "target": "t"},
            {"source": "region", "target": "y"},
            {"source": "t", "target": "y"},
        ],
        analysis={"treatment": "t", "outcome": "y"},
    )


def _record(dataset: Dataset, spec: CausalGraphSpec) -> CausalGraphRecord:
    return CausalGraphRecord(
        graph_id="cgraph-whatif-fixture",
        dataset_id=dataset.dataset_id,
        dataset_fingerprint_sha256=dataset.fingerprint_sha256,
        spec=spec,
        revision=1,
    )


def _request(dataset: Dataset, spec: CausalGraphSpec) -> EstimationRequest:
    return EstimationRequest(
        treatment_node="t",
        outcome_node="y",
        adjustment_nodes=["x1", "x2", "region"],
        treatment_mapping={"treated": "1", "control": "0"},
        uncertainty={"method": "influence_function", "reps": 100, "seed": SEED, "level": 0.95},
        expected_spec_fingerprint_sha256=None,
    )


def _run(frame: pd.DataFrame, profile: dict) -> dict:
    dataset = _dataset(frame)
    spec = _spec(dataset.dataset_id)
    record = _record(dataset, spec)
    request = _request(dataset, spec)
    return run_what_if(dataset, record, request, profile)


# --------------------------------------------------------------------------- #
# Correctness against the verified engine
# --------------------------------------------------------------------------- #


def test_case_1_cohort_contrast_equals_the_engine_regression_adjustment_ate():
    frame = _frame()
    payload = _run(frame, {})
    dataset = _dataset(frame)
    spec = _spec(dataset.dataset_id)
    request = _request(dataset, spec)
    engine = run_estimation(
        dataset,
        _record(dataset, spec),
        request,
        estimator_names=["regression_adjustment"],
    )
    engine_estimate = next(
        result["estimate"]
        for result in engine["results"]
        if result["estimator"] == "regression_adjustment"
    )
    assert payload["cohort_scenario"]["contrast"] == pytest.approx(engine_estimate, abs=1e-12)


def test_case_2_linear_profile_contrast_matches_the_cohort_contrast():
    # A linear outcome model without interactions implies a constant treatment
    # contrast for every baseline profile.
    payload = _run(_frame(), {"x1": 0.0, "x2": 0.0, "region": "north"})
    assert payload["profile_scenario"]["contrast"] == pytest.approx(
        payload["cohort_scenario"]["contrast"], abs=1e-10
    )


def test_case_3_scenario_predictions_are_deterministic():
    first = _run(_frame(), {"x1": 1.0})
    second = _run(_frame(), {"x1": 1.0})
    assert first["profile_scenario"] == second["profile_scenario"]


def test_case_4_both_arms_and_contrast_are_reported():
    payload = _run(_frame(), {"x1": 0.5, "x2": -0.5, "region": "south"})
    scenario = payload["profile_scenario"]
    assert set(scenario) >= {"treated_prediction", "control_prediction", "contrast"}
    assert scenario["contrast"] == pytest.approx(
        scenario["treated_prediction"] - scenario["control_prediction"], abs=1e-12
    )
    assert payload["model_specification"]["units"] == "outcome_units"


# --------------------------------------------------------------------------- #
# Honest guards
# --------------------------------------------------------------------------- #


def test_case_5_no_interval_is_attached_to_a_scenario():
    import json

    payload = _run(_frame(), {"x1": 0.0})
    blob = json.dumps(payload["profile_scenario"]) + json.dumps(payload["cohort_scenario"])
    assert "ci_lower" not in blob and "ci_upper" not in blob and "standard_error" not in blob


def test_case_6_extrapolation_outside_observed_support_warns():
    payload = _run(_frame(), {"x1": 50.0})  # x1 ~ N(0,1): 50 is far outside
    joined = " ".join(payload["warnings"])
    assert "Extrapolation" in joined and "x1" in joined


def test_case_7_unobserved_categorical_level_is_refused():
    with pytest.raises(ValidationFailure) as caught:
        _run(_frame(), {"region": "atlantis"})
    assert "not an observed level" in str(caught.value)


def test_case_8_unknown_profile_field_is_refused():
    with pytest.raises(ValidationFailure) as caught:
        _run(_frame(), {"post_treatment_score": 1.0})
    assert "not adjustment covariates" in str(caught.value)


def test_case_9_unset_fields_are_disclosed_defaults_not_silence():
    payload = _run(_frame(), {"x1": 0.0})
    disclosures = payload["profile_scenario"]["disclosures"]
    explicit = {item["field"] for item in disclosures if item["source"] == "explicit"}
    defaulted = {item["field"] for item in disclosures if item["source"] != "explicit"}
    assert explicit == {"x1"}
    assert {"x2", "region"} <= defaulted
    assert any(item["source"] == "cohort_median" for item in disclosures)
    assert any(item["source"] == "cohort_mode" for item in disclosures)
    assert any("median" in warning or "defaults" in warning for warning in payload["warnings"])


def test_case_10_non_numeric_value_for_numeric_field_is_refused():
    with pytest.raises(ValidationFailure):
        _run(_frame(), {"x1": "very high"})
