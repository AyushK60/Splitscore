"""S9A API integration: real upload path, real registry, real store, real gate.

Case 25 of the S9A brief lives here, together with the lifecycle guarantees:
dataset ownership (404 across datasets), expiry (typed 410), fingerprint-mismatch
refusal (409), the structured gate refusals (422), run storage with staleness
re-checking, and the strict request schema. Nothing is mocked.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient


def _dgp_rows(n: int = 360, seed: int = 101) -> list[dict]:
    """Confounded DGP with a known effect of 1.5, written to CSV rows."""
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0.0, 1.0, n)
    x2 = rng.normal(0.0, 1.0, n)
    propensity = 1.0 / (1.0 + np.exp(-(0.8 * x1 - 0.5 * x2)))
    t = rng.binomial(1, propensity)
    y = 1.5 * t + 0.9 * x1 - 0.7 * x2 + rng.normal(0.0, 1.0, n)
    return [
        {
            "x1": f"{x1[i]:.6f}",
            "x2": f"{x2[i]:.6f}",
            "t": str(int(t[i])),
            "y": f"{y[i]:.6f}",
        }
        for i in range(n)
    ]


COLUMNS = ["x1", "x2", "t", "y"]


@pytest.fixture()
def client():
    from app.api.deps import reset_context
    from app.main import create_app

    reset_context()
    with TestClient(create_app()) as test_client:
        yield test_client


def _upload(client: TestClient, rows=None, name: str = "estimation.csv") -> str:
    from .conftest import rows_to_csv

    rows = rows if rows is not None else _dgp_rows()
    payload = rows_to_csv(rows, COLUMNS)
    response = client.post("/api/datasets", files={"file": (name, payload, "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()["dataset"]["dataset_id"]


def _graph_spec(dataset_id: str, *, with_mediator: bool = False, with_unobserved: bool = False) -> dict:
    nodes = [
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "x2", "label": "x2", "column": "x2"},
        {"node_id": "t", "label": "t", "column": "t", "kind": "treatment"},
        {"node_id": "y", "label": "y", "column": "y", "kind": "outcome"},
    ]
    edges = [
        {"source": "x1", "target": "t"},
        {"source": "x1", "target": "y"},
        {"source": "x2", "target": "t"},
        {"source": "x2", "target": "y"},
        {"source": "t", "target": "y"},
    ]
    if with_mediator:
        nodes.append({"node_id": "m", "label": "m", "column": "x2"})
        edges.append({"source": "t", "target": "m"})
        edges.append({"source": "m", "target": "y"})
    if with_unobserved:
        nodes.append({"node_id": "u", "label": "u", "observed": False, "kind": "unobserved"})
        edges.append({"source": "u", "target": "t"})
        edges.append({"source": "u", "target": "y"})
    return {
        "name": "Estimation graph",
        "dataset_id": dataset_id,
        "nodes": nodes,
        "edges": edges,
        "analysis": {"treatment": "t", "outcome": "y"},
    }


def _create_graph(client: TestClient, dataset_id: str, **kwargs) -> dict:
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": _graph_spec(dataset_id, **kwargs)}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _request_body(
    fingerprint: str | None = None,
    adjustment: list[str] | None = None,
    **overrides,
) -> dict:
    body = {
        "treatment_node": "t",
        "outcome_node": "y",
        "adjustment_nodes": ["x1", "x2"] if adjustment is None else adjustment,
        "treatment_mapping": {"treated": "1", "control": "0"},
        "uncertainty": {"method": "bootstrap", "reps": 150, "seed": 2026, "level": 0.95},
    }
    if fingerprint:
        body["expected_spec_fingerprint_sha256"] = fingerprint
    body.update(overrides)
    return body


# --------------------------------------------------------------------------- #
# Case 25: genuine API integration
# --------------------------------------------------------------------------- #


def test_estimation_roundtrip_validate_run_store_retrieve(client):
    dataset_id = _upload(client)
    graph = _create_graph(client, dataset_id)
    gid = graph["graph_id"]
    fingerprint = graph["spec_fingerprint_sha256"]

    # Readiness: the gate runs, nothing is estimated, nothing is stored.
    ready = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/validate",
        json={"request": _request_body(fingerprint)},
    )
    assert ready.status_code == 200, ready.text
    ready_payload = ready.json()
    assert ready_payload["readiness"] == "ready"
    assert ready_payload["gate"]["gate"] == "passed"
    assert ready_payload["cohort_preview"]["rows_final"] == 360
    assert ready_payload["spec_fingerprint_sha256"] == fingerprint
    assert "run_id" not in ready_payload

    # Run one estimator.
    run = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/run",
        json={"request": _request_body(fingerprint), "estimator": "ipw"},
    )
    assert run.status_code == 200, run.text
    run_payload = run.json()
    assert run_payload["results"][0]["estimator"] == "ipw"
    assert run_payload["results"][0]["status"] == "estimated"
    # n = 360, so the tolerance here is deliberately wide (≈ 2 SEs).
    assert abs(run_payload["results"][0]["estimate"] - 1.5) < 0.5
    assert run_payload["reproducibility"]["graph_spec_fingerprint_sha256"] == fingerprint
    assert run_payload["reproducibility"]["graph_revision"] == 0
    assert "positivity" in run_payload["scope_note"]
    run_id = run_payload["run_id"]

    # The run is retrievable from the store and not stale.
    listing = client.get(f"/api/datasets/{dataset_id}/estimation-runs")
    assert listing.status_code == 200
    assert any(item["run_id"] == run_id for item in listing.json()["runs"])

    fetched = client.get(f"/api/datasets/{dataset_id}/estimation-runs/{run_id}")
    assert fetched.status_code == 200, fetched.text
    fetched_payload = fetched.json()
    assert fetched_payload["stale"] is False
    assert fetched_payload["results"][0]["estimate"] == run_payload["results"][0]["estimate"]


def test_estimation_compare_runs_all_three_under_one_analysis(client):
    dataset_id = _upload(client)
    graph = _create_graph(client, dataset_id)
    gid = graph["graph_id"]
    fingerprint = graph["spec_fingerprint_sha256"]

    comparison = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/compare",
        json={"request": _request_body(fingerprint)},
    )
    assert comparison.status_code == 200, comparison.text
    payload = comparison.json()
    assert len(payload["results"]) == 3
    assert {r["estimator"] for r in payload["results"]} == {
        "regression_adjustment",
        "ipw",
        "aipw",
    }
    sizes = {r["sample_size"] for r in payload["results"] if r.get("status") == "estimated"}
    assert len(sizes) <= 1
    assert "shared_analysis" in payload["comparison"]
    assert payload["comparison"]["estimates"]


def test_gate_refuses_post_treatment_and_unobserved_adjustment(client):
    dataset_id = _upload(client)
    graph = _create_graph(client, dataset_id, with_mediator=True, with_unobserved=True)
    gid = graph["graph_id"]

    mediator = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/run",
        json={"request": _request_body(adjustment=["x1", "m"]), "estimator": "ipw"},
    )
    assert mediator.status_code == 422
    violations = mediator.json()["error"]["details"]["verification"]["violations"]
    assert any(v["code"] == "post_treatment_variable" for v in violations)

    # No adjustment set can pass when an unobserved confounder remains.
    empty = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/validate",
        json={"request": _request_body(adjustment=[])},
    )
    assert empty.status_code == 422
    unobserved = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/validate",
        json={"request": _request_body(adjustment=["x1", "x2"])},
    )
    assert unobserved.status_code == 422
    unobserved_violations = unobserved.json()["error"]["details"]["verification"]["violations"]
    assert unobserved_violations  # the backdoor path through u stays open


def test_fingerprint_mismatch_is_a_conflict_not_a_silent_estimate(client):
    dataset_id = _upload(client)
    graph = _create_graph(client, dataset_id)
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph['graph_id']}/estimation/run",
        json={
            "request": _request_body(fingerprint="0" * 64),
            "estimator": "ipw",
        },
    )
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "infeasible_operation"
    assert error["details"]["current_spec_fingerprint_sha256"] == graph["spec_fingerprint_sha256"]


def test_cross_dataset_graph_access_is_404(client):
    first = _upload(client)
    second = _upload(client, name="estimation-b.csv")
    graph = _create_graph(client, first)
    response = client.post(
        f"/api/datasets/{second}/causal-graphs/{graph['graph_id']}/estimation/run",
        json={"request": _request_body(), "estimator": "ipw"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_expired_dataset_returns_typed_410(client):
    dataset_id = _upload(client)
    graph = _create_graph(client, dataset_id)
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph['graph_id']}/estimation/validate",
        json={"request": _request_body()},
    )
    assert response.status_code == 200

    from app.api.deps import reset_context

    reset_context()  # the process restarted: everything expired
    gone = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph['graph_id']}/estimation/validate",
        json={"request": _request_body()},
    )
    assert gone.status_code == 410
    assert gone.json()["error"]["code"] == "expired_or_evicted"


def test_structural_edit_makes_run_stale_but_layout_edit_does_not(client):
    dataset_id = _upload(client)
    graph = _create_graph(client, dataset_id)
    gid = graph["graph_id"]
    fingerprint = graph["spec_fingerprint_sha256"]

    run = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/run",
        json={"request": _request_body(fingerprint), "estimator": "ipw"},
    )
    assert run.status_code == 200
    run_id = run.json()["run_id"]

    # A layout-only edit (node coordinates) never changes the fingerprint.
    layout_spec = _graph_spec(dataset_id)
    for node in layout_spec["nodes"]:
        node["layout"] = {"x": 40.0, "y": 40.0}
    relayout = client.put(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}", json={"graph": layout_spec}
    )
    assert relayout.status_code == 200, relayout.text
    assert relayout.json()["spec_fingerprint_sha256"] == fingerprint
    still_fresh = client.get(f"/api/datasets/{dataset_id}/estimation-runs/{run_id}")
    assert still_fresh.json()["stale"] is False

    # A structural edit (drop a confounder edge) changes the fingerprint: the
    # stored estimate becomes stale.
    structural = _graph_spec(dataset_id)
    structural["edges"] = [e for e in structural["edges"] if e["source"] != "x2"]
    edited = client.put(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}", json={"graph": structural}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["spec_fingerprint_sha256"] != fingerprint
    stale = client.get(f"/api/datasets/{dataset_id}/estimation-runs/{run_id}")
    stale_payload = stale.json()
    assert stale_payload["stale"] is True
    assert "changed" in stale_payload["staleness_reason"]


def test_estimation_refused_when_node_is_not_column_anchored(client):
    dataset_id = _upload(client)
    spec = _graph_spec(dataset_id)
    spec["nodes"].append({"node_id": "ghost", "label": "ghost"})  # no column
    spec["edges"].append({"source": "ghost", "target": "y"})
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": spec}
    )
    assert response.status_code == 201, response.text
    gid = response.json()["graph_id"]

    request = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/validate",
        json={"request": _request_body(adjustment=["x1", "ghost"])},
    )
    assert request.status_code == 422
    assert "ghost" in request.json()["error"]["message"]


def test_ambiguous_treatment_encoding_is_a_structured_422(client):
    rows = _dgp_rows(n=60)
    for row in rows[:10]:
        row["t"] = "maybe"  # a third treatment value: ambiguous
    dataset_id = _upload(client, rows=rows)
    graph = _create_graph(client, dataset_id)
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph['graph_id']}/estimation/run",
        json={"request": _request_body(), "estimator": "ipw"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert "ambiguous" in error["message"]
    assert "maybe" in error["details"]["unmatched_values_with_counts"]


def test_request_schema_is_strict_and_estimators_are_named_only(client):
    dataset_id = _upload(client)
    graph = _create_graph(client, dataset_id)
    gid = graph["graph_id"]

    # No user-supplied code or unknown fields can reach the estimators.
    extra = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/run",
        json={
            "request": {**_request_body(), "custom_objective": "import os"},
            "estimator": "ipw",
        },
    )
    assert extra.status_code == 422
    assert extra.json()["error"]["code"] == "validation_error"

    unknown_estimator = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/run",
        json={"request": _request_body(), "estimator": "neural_network"},
    )
    assert unknown_estimator.status_code == 422


def test_run_listing_and_mixed_kinds_are_separated(client):
    dataset_id = _upload(client)
    graph = _create_graph(client, dataset_id)
    gid = graph["graph_id"]
    client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/estimation/run",
        json={"request": _request_body(), "estimator": "ipw"},
    )
    listing = client.get(f"/api/datasets/{dataset_id}/estimation-runs")
    assert listing.status_code == 200
    runs = listing.json()["runs"]
    assert runs
    assert all(item["kind"] == "estimation" for item in runs)
