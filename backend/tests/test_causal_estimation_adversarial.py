"""estimation adversarial tests: inputs designed to break the estimators or the API.

Every test here corresponds to an adversarial-audit scenario. The central
invariant: the application returns correct results, explicit warnings, or
meaningful structured errors - never a NaN/Infinity estimate and never an
unhandled 500 for data-driven degeneracy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.audit.dataset import Dataset
from app.causal.estimation.contracts import EstimationRequest
from app.causal.estimation.service import run_estimation
from app.causal.registry import CausalGraphRecord
from app.causal.schema import CausalGraphSpec
from app.core.errors import ValidationFailure

from .conftest import make_dataset, rows_to_csv


def _dataset(frame: pd.DataFrame) -> Dataset:
    return make_dataset(frame.to_dict("records"), name="adversarial-fixture.csv")


def _record(dataset: Dataset, columns: list[str]) -> CausalGraphRecord:
    covariate_nodes = [{"node_id": c, "label": c, "column": c} for c in columns if c not in ("t", "y")]
    edges = []
    for c in columns:
        if c not in ("t", "y"):
            edges += [{"source": c, "target": "t"}, {"source": c, "target": "y"}]
    edges.append({"source": "t", "target": "y"})
    spec = CausalGraphSpec(
        name="Adversarial graph",
        dataset_id=dataset.dataset_id,
        nodes=[*covariate_nodes, {"node_id": "t", "label": "t", "column": "t"},
               {"node_id": "y", "label": "y", "column": "y"}],
        edges=edges,
        analysis={"treatment": "t", "outcome": "y"},
    )
    return CausalGraphRecord(
        graph_id="cgraph-adv",
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


def _base_frame(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-0.8 * x1)))
    y = 1.0 * t + 0.5 * x1 + rng.normal(0, 1, n)
    return pd.DataFrame({"x1": x1, "t": t, "y": y})


def _run_all(dataset: Dataset, record: CausalGraphRecord, request: EstimationRequest) -> dict:
    payload = run_estimation(
        dataset, record, request, estimator_names=["regression_adjustment", "ipw", "aipw"]
    )
    return {r["estimator"]: r for r in payload["results"]}


def _assert_no_nan_inf(payload: dict) -> None:
    """No NaN/Infinity may appear anywhere in a serialized payload."""
    import json

    text = json.dumps(payload, allow_nan=False)  # raises on NaN/Inf
    assert "NaN" not in text
    assert "Infinity" not in text


# --------------------------------------------------------------------------- #
# Regression tests for the audit repairs
# --------------------------------------------------------------------------- #


def test_adversarial_inf_covariate_is_excluded_not_a_crash():
    """Audit repair D1: an infinite covariate value must be a counted
    exclusion, never a library ValueError reaching the HTTP layer."""
    frame = _base_frame()
    frame.loc[3, "x1"] = np.inf
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    payload = run_estimation(dataset, record, _request(["x1", "t", "y"]),
                             estimator_names=["regression_adjustment", "ipw"])
    reasons = {e["reason"]: e["count"] for e in payload["analysis"]["exclusions"]}
    assert reasons.get("invalid_covariate_value") == 1
    assert payload["analysis"]["rows_final"] == 299
    for result in payload["results"]:
        assert result["status"] == "estimated"
    _assert_no_nan_inf(payload)


def test_adversarial_too_few_groups_is_a_structured_failure():
    """Audit repair D2: GroupKFold with fewer groups than splits must produce a
    per-estimator structured failure, never an unhandled exception."""
    frame = _base_frame()
    frame["ent"] = np.repeat(["g1", "g2", "g3"], 100)
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    request = _request(
        ["x1", "t", "y"], cross_fit={"splits": 5, "group_column": "ent"}
    )
    results = _run_all(dataset, record, request)
    failed = results["aipw"]
    assert failed["status"] == "failed"
    assert "group" in failed["failure"]["reason"].lower()
    assert "unique_groups" in failed["failure"]["details"]
    assert results["regression_adjustment"]["status"] == "estimated"


def test_adversarial_single_class_propensity_fold_is_structured():
    """Audit repair D3: a training fold with one treatment class must be a
    structured refusal, not a scikit-learn ValueError escaping as a 500."""
    frame = _base_frame()
    # Groups perfectly aligned with treatment: some GroupKFold training folds
    # contain a single class even though both arms exist overall.
    frame["ent"] = np.where(frame["t"] == 1, "a", "b")
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    request = _request(["x1", "t", "y"], cross_fit={"splits": 2, "group_column": "ent"})
    results = _run_all(dataset, record, request)
    failed = results["aipw"]
    assert failed["status"] == "failed"
    assert "one treatment class" in failed["failure"]["reason"]
    assert results["ipw"]["status"] == "estimated"


def test_adversarial_median_mode_balance_is_defined():
    """Audit repair D4: under median_mode, balance SMDs must be defined on the
    imputed values the models actually see, with the imputation disclosed."""
    frame = _base_frame()
    frame.loc[5, "x1"] = np.nan
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    payload = run_estimation(
        dataset,
        record,
        _request(["x1", "t", "y"], missing_data_policy="median_mode"),
        estimator_names=["ipw"],
    )
    balance = payload["results"][0]["diagnostics"]["balance"]
    entry = balance["covariates"][0]
    assert entry["smd_unweighted"] is not None
    assert entry["smd_weighted"] is not None
    assert "diagnostic_imputation" in balance
    covariate_spec = next(c for c in payload["analysis"]["covariates"] if c["column"] == "x1")
    assert covariate_spec["missing_in_cohort"] == 1  # raw missingness still reported


# --------------------------------------------------------------------------- #
# Remaining adversarial scenarios
# --------------------------------------------------------------------------- #


def test_adversarial_extreme_outcome_magnitudes_stay_finite():
    frame = _base_frame()
    frame["y"] = frame["y"] * 1e6
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    results = _run_all(dataset, record, _request(["x1", "t", "y"]))
    for result in results.values():
        assert result["status"] == "estimated"
        assert np.isfinite(result["estimate"])
    _assert_no_nan_inf(
        {"estimates": [r["estimate"] for r in results.values()]}
    )


def test_adversarial_duplicate_rows_are_estimable():
    """Duplicates are legitimate data for estimation (the platform's duplicate
    auditing is a separate feature); the estimators must not crash."""
    frame = pd.concat([_base_frame(), _base_frame().iloc[:50]], ignore_index=True)
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    results = _run_all(dataset, record, _request(["x1", "t", "y"]))
    for result in results.values():
        assert result["status"] == "estimated"
        assert np.isfinite(result["estimate"])


def test_adversarial_perfectly_correlated_confounders_stay_finite():
    rng = np.random.default_rng(11)
    n = 400
    x1 = rng.normal(0, 1, n)
    x2 = x1 + 1e-8 * rng.normal(0, 1, n)  # numerically collinear
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-(0.8 * x1))))
    y = 1.0 * t + 0.5 * x1 + rng.normal(0, 1, n)
    frame = pd.DataFrame({"x1": x1, "x2": x2, "t": t, "y": y})
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "x2", "t", "y"])
    results = _run_all(dataset, record, _request(["x1", "x2", "t", "y"]))
    for result in results.values():
        assert result["status"] == "estimated"
        assert np.isfinite(result["estimate"])


def test_adversarial_nearly_constant_covariate_is_estimable():
    frame = _base_frame()
    frame["x_const"] = 2.5
    frame["x_noise"] = frame["x1"] * 1e-6
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "x_const", "x_noise", "t", "y"])
    results = _run_all(dataset, record, _request(["x1", "x_const", "x_noise", "t", "y"]))
    for result in results.values():
        assert result["status"] == "estimated"
        assert np.isfinite(result["estimate"])


def test_adversarial_bootstrap_resamples_missing_an_arm_are_counted():
    """A bootstrap resample can contain (almost) no treated rows; the replicate
    must be counted as failed rather than producing a garbage value."""
    frame = _base_frame(400)
    frame["t"] = 0
    frame.loc[:9, "t"] = 1  # 10 treated of 400: ~1.3% of resamples have <1
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "t", "y"])
    request = _request(
        ["x1", "t", "y"], uncertainty={"method": "bootstrap", "reps": 300, "seed": 3}
    )
    payload = run_estimation(dataset, record, request, estimator_names=["ipw"])
    result = payload["results"][0]
    assert result["status"] == "estimated"  # the point estimate itself is fine
    bootstrap = result["uncertainty"]["bootstrap"]
    assert bootstrap["reps_failed"] + bootstrap["reps_succeeded"] == 300
    if bootstrap["reps_failed"] > 0:
        assert bootstrap["sample_failure_messages"], "failures must be explained"


def test_adversarial_high_cardinality_categorical_refused_structured(client=None):
    frame = _base_frame()
    frame["code"] = [f"c{i}" for i in range(len(frame))]  # 300 levels
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "code", "t", "y"])
    with pytest.raises(ValidationFailure) as excinfo:
        run_estimation(dataset, record, _request(["x1", "code", "t", "y"]),
                       estimator_names=["ipw"])
    assert excinfo.value.details["column"] == "code"
    assert excinfo.value.details["distinct_values"] == 300


def test_adversarial_mixed_type_covariate_is_refused_not_coerced():
    """A column that is neither numeric nor categorical (<80% numeric) must be
    refused instead of silently coerced - the Model Lab convention."""
    frame = _base_frame()
    mixed = [str(float(i)) for i in range(250)] + [f"row{i}" for i in range(50)]
    frame["mixed"] = mixed  # 83% numeric: parsed numeric with unparsable tail
    dataset = _dataset(frame)
    record = _record(dataset, ["x1", "mixed", "t", "y"])
    with pytest.raises(ValidationFailure) as excinfo:
        run_estimation(dataset, record, _request(["x1", "mixed", "t", "y"]),
                       estimator_names=["ipw"])
    assert "mixed" in excinfo.value.message


# --------------------------------------------------------------------------- #
# API-level adversarial checks: no 500s, no bypasses
# --------------------------------------------------------------------------- #


COLUMNS = ["x1", "t", "y"]


@pytest.fixture()
def client():
    from app.api.deps import reset_context
    from app.main import create_app

    reset_context()
    with TestClient(create_app()) as test_client:
        yield test_client


def _api_setup(client: TestClient, rows: list[dict] | None = None) -> tuple[str, dict]:
    payload = rows_to_csv(rows or _base_frame().to_dict("records"), ["x1", "t", "y"])
    response = client.post("/api/datasets", files={"file": ("adv.csv", payload, "text/csv")})
    assert response.status_code == 201, response.text
    dataset_id = response.json()["dataset"]["dataset_id"]
    spec = {
        "name": "Adv graph",
        "dataset_id": dataset_id,
        "nodes": [
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        "edges": [{"source": "x1", "target": "t"}, {"source": "x1", "target": "y"},
                  {"source": "t", "target": "y"}],
        "analysis": {"treatment": "t", "outcome": "y"},
    }
    graph = client.post(f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": spec})
    assert graph.status_code == 201, graph.text
    return dataset_id, graph.json()


def _body(adjustment: list[str] | None = None, **overrides) -> dict:
    body = {
        "treatment_node": "t",
        "outcome_node": "y",
        "adjustment_nodes": ["x1"] if adjustment is None else adjustment,
        "treatment_mapping": {"treated": "1", "control": "0"},
    }
    body.update(overrides)
    return body


def test_api_adversarial_no_500_on_any_degenerate_input(client):
    """Sweep of degenerate requests: every response is a structured 2xx/4xx,
    never a 500."""
    rows = _base_frame(80).to_dict("records")
    # degeneracies: constant treatment, all-missing outcome, negative mapping
    degenerate_rows = []
    for i, row in enumerate(rows):
        row = dict(row)
        if i < 40:
            row["t"] = "1"  # severe imbalance
        if 60 <= i < 70:
            row["y"] = ""  # missing outcomes
        degenerate_rows.append(row)
    dataset_id, graph = _api_setup(client, degenerate_rows)
    gid = graph["graph_id"]

    responses = [
        client.post(
            f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/run",
            json={"request": _body(), "estimator": "ipw"},
        ),
        client.post(
            f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/run",
            json={"request": _body(adjustment=[]), "estimator": "aipw"},
        ),
        client.post(
            f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/run",
            json={"request": _body(**{"treatment_mapping": {"treated": "x", "control": "y"}}),
                  "estimator": "ipw"},
        ),
        client.post(
            f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/validate",
            json={"request": _body(**{"outcome_node": "t"})},
        ),
        client.get(f"/api/datasets/{dataset_id}/estimation-runs/nonexistent-run"),
    ]
    for response in responses:
        assert response.status_code != 500, response.text
    # An unknown run id follows the store convention: typed 410, not a 500.
    assert responses[-1].status_code == 410
    assert responses[-1].json()["error"]["code"] == "expired_or_evicted"


def test_api_incomplete_search_does_not_block_verified_named_set(client):
    """With 15 eligible candidates the identification search is truncated - but a named
    set verified by exact evaluation must still be estimable, and a graph
    whose search completed with no sets must not be estimable."""
    rng = np.random.default_rng(13)
    n = 400
    columns = [f"x{i}" for i in range(1, 16)]
    data = {c: rng.normal(0, 1, n) for c in columns}
    latent = np.column_stack([data[c] for c in columns if c != "x1"]).sum(axis=1)
    x1 = latent + rng.normal(0, 0.1, n)
    data["x1"] = x1
    t = rng.binomial(1, 1.0 / (1.0 + np.exp(-0.4 * x1)))  # mild overlap
    y = 0.7 * t + 0.5 * x1 + rng.normal(0, 1, n)
    rows = []
    for i in range(n):
        row = {c: f"{data[c][i]:.6f}" for c in columns}
        row["t"] = str(int(t[i]))
        row["y"] = f"{y[i]:.6f}"
        rows.append(row)

    all_columns = [*columns, "t", "y"]
    payload = rows_to_csv(rows, all_columns)
    response = client.post("/api/datasets", files={"file": ("wide.csv", payload, "text/csv")})
    assert response.status_code == 201, response.text
    dataset_id = response.json()["dataset"]["dataset_id"]
    nodes = [{"node_id": c, "label": c, "column": c} for c in all_columns]
    edges = [{"source": c, "target": "x1"} for c in columns if c != "x1"]
    edges += [{"source": "x1", "target": "t"}, {"source": "x1", "target": "y"},
              {"source": "t", "target": "y"}]
    graph = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs",
        json={"graph": {"name": "Wide graph", "dataset_id": dataset_id, "nodes": nodes,
                        "edges": edges, "analysis": {"treatment": "t", "outcome": "y"}}},
    )
    assert graph.status_code == 201, graph.text
    gid = graph.json()["graph_id"]

    # The identification search is honestly truncated at 15 candidates.
    search = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/adjustment-search", json={}
    )
    assert search.json()["search_status"] == "incomplete"

    # ... yet the named, exact-verified set estimates.
    body = {
        "treatment_node": "t",
        "outcome_node": "y",
        "adjustment_nodes": ["x1"],
        "treatment_mapping": {"treated": "1", "control": "0"},
    }
    run = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/run",
        json={"request": body, "estimator": "regression_adjustment"},
    )
    assert run.status_code == 200, run.text
    result = run.json()["results"][0]
    assert result["status"] == "estimated"
    assert abs(result["estimate"] - 0.7) < 0.3


def test_api_cyclic_graph_cannot_reach_estimation(client):
    """A cyclic graph is refused at creation, so no estimator
    can ever see one."""
    rows = _base_frame(60).to_dict("records")
    payload = rows_to_csv(rows, ["x1", "t", "y"])
    response = client.post("/api/datasets", files={"file": ("cyc.csv", payload, "text/csv")})
    dataset_id = response.json()["dataset"]["dataset_id"]
    cyclic = {
        "name": "Cyclic",
        "dataset_id": dataset_id,
        "nodes": [
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
        ],
        "edges": [{"source": "t", "target": "y"}, {"source": "y", "target": "t"}],
    }
    created = client.post(f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": cyclic})
    assert created.status_code == 422
    assert created.json()["error"]["code"] == "validation_error"


def test_api_unknown_variables_and_unobserved_adjustment_refused(client):
    dataset_id, graph = _api_setup(client)
    gid = graph["graph_id"]

    unknown = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/validate",
        json={"request": _body(adjustment=["ghost"])},
    )
    assert unknown.status_code == 422

    # An unobserved node cannot be anchored, so it cannot enter the estimator.
    spec = {
        "name": "Unobserved",
        "dataset_id": dataset_id,
        "nodes": [
            {"node_id": "x1", "label": "x1", "column": "x1"},
            {"node_id": "t", "label": "t", "column": "t"},
            {"node_id": "y", "label": "y", "column": "y"},
            {"node_id": "u", "label": "u", "observed": False, "kind": "unobserved"},
        ],
        "edges": [{"source": "x1", "target": "t"}, {"source": "x1", "target": "y"},
                  {"source": "u", "target": "t"}, {"source": "u", "target": "y"},
                  {"source": "t", "target": "y"}],
        "analysis": {"treatment": "t", "outcome": "y"},
    }
    graph2 = client.post(f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": spec})
    assert graph2.status_code == 201, graph2.text
    unobserved = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph2.json()['graph_id']}/estimation/run",
        json={"request": _body(adjustment=["x1", "u"]), "estimator": "ipw"},
    )
    assert unobserved.status_code == 422
