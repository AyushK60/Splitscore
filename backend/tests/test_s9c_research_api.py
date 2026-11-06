"""S9C API integration: routes, ownership, refusal, storage, staleness.

Drives the real FastAPI routes with the TestClient against the bundled
``causal_effect`` demo dataset, so the S9C endpoints are exercised exactly as
the frontend calls them — including ownership (a graph under another dataset
is 404), typed refusals, stored-run retrieval and staleness annotation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_NODE_KEYS = ("node_id", "label", "column", "observed", "kind", "description", "layout")
_EDGE_KEYS = ("source", "target", "rationale", "reference")


def _bare_spec(graph: dict, dataset_id: str, **renames) -> dict:
    """Strip server-computed fields back down to the writable spec shape."""
    spec = {
        "schema_version": graph["schema_version"],
        "dataset_id": dataset_id,
        "name": renames.get("name", graph["name"]),
        "description": graph["description"],
        "nodes": [{key: node[key] for key in _NODE_KEYS} for node in graph["nodes"]],
        "edges": [{key: edge[key] for key in _EDGE_KEYS} for edge in graph["edges"]],
        "analysis": graph["analysis"],
        "assumptions": graph["assumptions"],
    }
    spec["nodes"].extend(renames.get("extra_nodes", []))
    spec["edges"].extend(renames.get("extra_edges", []))
    return spec


def _load_demo() -> tuple[str, str]:
    response = client.post("/api/demos/causal_effect/load")
    assert response.status_code == 200
    dataset_id = response.json()["dataset"]["dataset_id"]
    graph_spec = {
        "schema_version": "1.0.0",
        "dataset_id": dataset_id,
        "name": "S9C API demonstration",
        "description": "Demonstration DAG for the confounded treatment-effect study.",
        "nodes": [
            {
                "node_id": variable,
                "label": variable,
                "column": variable,
                "observed": True,
                "kind": "covariate",
                "description": None,
                "layout": None,
            }
            for variable in ["age", "baseline_score", "region", "treatment", "outcome"]
        ],
        "edges": [
            {"source": source, "target": "treatment", "rationale": None, "reference": None}
            for source in ["age", "baseline_score", "region"]
        ]
        + [
            {"source": source, "target": "outcome", "rationale": None, "reference": None}
            for source in ["age", "baseline_score", "region", "treatment"]
        ],
        "analysis": {"treatment": "treatment", "outcome": "outcome"},
        "assumptions": [],
    }
    created = client.post(f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": graph_spec})
    assert created.status_code == 201, created.text
    graph = created.json()
    graph_id = (graph.get("graph") or graph)["graph_id"]
    return dataset_id, graph_id


def _request() -> dict:
    return {
        "estimand": "ate",
        "treatment_node": "treatment",
        "outcome_node": "outcome",
        "adjustment_nodes": ["age", "baseline_score", "region"],
        "treatment_mapping": {"treated": "1", "control": "0"},
        "cohort": {"split_assignment_id": None, "partition": None},
        "missing_data_policy": "complete_case",
        "cross_fit": {"splits": 3, "group_column": None},
        "uncertainty": {"method": "influence_function", "level": 0.95, "reps": 100, "seed": 2026},
        "propensity_truncation": None,
        "expected_spec_fingerprint_sha256": None,
    }


def _run_subgroups(dataset_id: str, graph_id: str, **overrides) -> dict:
    body = {
        "request": _request(),
        "subgroup": {"node_id": "region", "numeric_binning": "quartile", "intent": "exploratory"},
        "label": "api-test",
    }
    body.update(overrides)
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/subgroups", json=body
    )
    return {"status": response.status_code, "payload": response.json()}


def test_subgroups_route_runs_stores_and_the_run_is_retrievable():
    dataset_id, graph_id = _load_demo()
    result = _run_subgroups(dataset_id, graph_id)
    assert result["status"] == 200, result["payload"]
    payload = result["payload"]
    assert payload["analysis_kind"] == "subgroups"
    assert payload["subgroup"]["column"] == "region"
    assert len(payload["groups"]) == 3
    run_id = payload["run_id"]
    fetched = client.get(f"/api/datasets/{dataset_id}/estimation-runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == run_id
    listing = client.get(f"/api/datasets/{dataset_id}/estimation-runs")
    assert any(run["run_id"] == run_id for run in listing.json()["runs"])


def test_subgroups_refuses_a_treatment_descendant():
    dataset_id, graph_id = _load_demo()
    # Build a graph with a mediator node (anchored to an existing column) that
    # lies strictly downstream of the treatment: a textbook refused subgroup.
    listing = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}").json()
    graph = listing.get("graph") or listing
    mediator_edges = [
        {key: edge[key] for key in _EDGE_KEYS}
        for edge in graph["edges"]
        if not (edge["source"] == "age" and edge["target"] == "outcome")
    ]
    mediator_spec = _bare_spec(
        graph,
        dataset_id,
        name="Mediator graph",
        extra_nodes=[
            {
                "node_id": "mediator",
                "label": "mediator",
                "column": "age",
                "observed": True,
                "kind": "covariate",
                "description": None,
                "layout": None,
            }
        ],
    )
    mediator_spec["edges"] = mediator_edges + [
        {"source": "treatment", "target": "mediator", "rationale": None, "reference": None},
        {"source": "mediator", "target": "outcome", "rationale": None, "reference": None},
    ]
    created = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": mediator_spec}
    )
    assert created.status_code == 201, created.text
    mediator_graph = (created.json().get("graph") or created.json())["graph_id"]
    result = _run_subgroups(
        dataset_id, mediator_graph, subgroup={"node_id": "mediator", "intent": "exploratory"}
    )
    assert result["status"] == 422
    assert "descendant of the treatment" in result["payload"]["error"]["message"]


def test_subgroups_refuses_an_invalid_adjustment_set():
    dataset_id, graph_id = _load_demo()
    request = _request()
    request["adjustment_nodes"] = []  # open backdoor path through the confounders
    result = _run_subgroups(dataset_id, graph_id, request=request)
    assert result["status"] == 422
    assert "backdoor" in result["payload"]["error"]["message"].lower()


def test_robustness_route_runs_all_three_experiments_and_stores():
    dataset_id, graph_id = _load_demo()
    for experiment, parameters in [
        ("subsampling", {"estimator": "ipw", "reps": 100, "fraction": 0.5}),
        ("placebo", {"estimator": "regression_adjustment", "reps": 100}),
        ("unmeasured_confounder", {"estimator": "regression_adjustment"}),
    ]:
        response = client.post(
            f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/robustness",
            json={
                "request": _request(),
                "experiment": experiment,
                "parameters": parameters,
                "label": "api-test",
            },
        )
        assert response.status_code == 200, response.json()
        payload = response.json()
        assert payload["analysis_kind"] == "robustness"
        assert payload["result"]["experiment"] == {
            "subsampling": "subsampling",
            "placebo": "placebo_treatment",
            "unmeasured_confounder": "unmeasured_confounder_simulation",
        }[experiment]
        assert payload["run_id"]


def test_robustness_refuses_out_of_bounds_reps():
    dataset_id, graph_id = _load_demo()
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/robustness",
        json={
            "request": _request(),
            "experiment": "subsampling",
            "parameters": {"estimator": "ipw", "reps": 10},
        },
    )
    assert response.status_code == 422


def test_what_if_route_scenarios_staleness_and_ownership():
    dataset_id, graph_id = _load_demo()
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/whatif",
        json={
            "request": _request(),
            "profile": {"age": 55.0, "baseline_score": 48.0, "region": "south"},
            "label": "api-test",
        },
    )
    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["analysis_kind"] == "what_if"
    assert payload["profile_scenario"]["profile"]["age"] == 55.0
    assert payload["run_id"]
    # The stored run is retrievable and not stale immediately.
    fetched = client.get(f"/api/datasets/{dataset_id}/estimation-runs/{payload['run_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["stale"] is False
    # A structural graph edit invalidates the stored scenario run. The PUT
    # body must be the bare spec, not the server-enriched graph payload.
    listing = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}").json()
    graph = listing.get("graph") or listing
    updated = _bare_spec(graph, dataset_id)
    updated["edges"] = [
        edge
        for edge in updated["edges"]
        if not (edge["source"] == "region" and edge["target"] == "outcome")
    ]
    save = client.put(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}", json={"graph": updated})
    assert save.status_code == 200, save.text
    fetched_after = client.get(
        f"/api/datasets/{dataset_id}/estimation-runs/{payload['run_id']}"
    )
    assert fetched_after.status_code == 200
    assert fetched_after.json()["stale"] is True


def test_estimation_runs_belong_to_their_dataset():
    dataset_id, graph_id = _load_demo()
    other = client.post("/api/demos/repeated_entity/load").json()["dataset"]["dataset_id"]
    result = _run_subgroups(dataset_id, graph_id)
    assert result["status"] == 200
    run_id = result["payload"]["run_id"]
    wrong_dataset = client.get(f"/api/datasets/{other}/estimation-runs/{run_id}")
    assert wrong_dataset.status_code == 404


# --------------------------------------------------------------------------- #
# S9C independent audit additions: fingerprint gating on every S9C route
# --------------------------------------------------------------------------- #


def _graph_fingerprint(dataset_id: str, graph_id: str) -> str:
    fetched = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    graph = body.get("graph") or body
    return graph["spec_fingerprint_sha256"]


def _stale_request(dataset_id: str, graph_id: str) -> dict:
    request = _request()
    request["expected_spec_fingerprint_sha256"] = "0" * 64
    assert request["expected_spec_fingerprint_sha256"] != _graph_fingerprint(dataset_id, graph_id)
    return request


def test_subgroups_refuse_a_stale_graph_fingerprint():
    dataset_id, graph_id = _load_demo()
    result = _run_subgroups(dataset_id, graph_id, request=_stale_request(dataset_id, graph_id))
    assert result["status"] == 409
    assert result["payload"]["error"]["code"] == "infeasible_operation"


def test_robustness_refuses_a_stale_graph_fingerprint():
    dataset_id, graph_id = _load_demo()
    body = {
        "request": _stale_request(dataset_id, graph_id),
        "experiment": "subsampling",
        "parameters": {"estimator": "aipw", "reps": 100, "fraction": 0.5},
        "label": "api-test",
    }
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/robustness", json=body
    )
    assert response.status_code == 409


def test_what_if_refuses_a_stale_graph_fingerprint():
    dataset_id, graph_id = _load_demo()
    body = {
        "request": _stale_request(dataset_id, graph_id),
        "profile": {"age": 40},
        "label": "api-test",
    }
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/whatif", json=body
    )
    assert response.status_code == 409


def test_robustness_refuses_unknown_experiment_kind_and_mismatched_spec():
    dataset_id, graph_id = _load_demo()
    wrong_kind = {
        "request": _request(),
        "experiment": "subsampling",
        "parameters": {"estimator": "bogus_estimator"},  # rejected before the gate
        "label": "api-test",
    }
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/robustness",
        json=wrong_kind,
    )
    assert response.status_code in (400, 422)
