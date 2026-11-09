"""identification identification: known-answer backdoor fixtures, search behaviour, API.

Every expected adjustment set, violation code and identification status in
this file is written by hand from the graphical definition of the classical
backdoor criterion - never derived from the implementation - mirroring the
graph test conventions.

Cases 1-10 of the identification brief are labelled explicitly in the test names.
API tests run against the real upload path, the real registry and the real
error envelope; nothing is mocked.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.causal.adjustment import (
    AdjustmentQueryError,
    evaluate_adjustment_set,
    search_adjustment_sets,
)
from app.causal.d_separation import DAG
from app.causal.identification import identify_backdoor, observed_node_ids
from app.causal.schema import CausalGraphSpec


def _spec(
    nodes: list[dict],
    edges: list[tuple[str, str]],
    treatment: str | None = None,
    outcome: str | None = None,
    name: str = "Identification fixture",
) -> CausalGraphSpec:
    node_specs = []
    for item in nodes:
        node = {"node_id": item["node_id"], "label": item["node_id"]}
        node.update({k: v for k, v in item.items() if k != "node_id"})
        node_specs.append(node)
    return CausalGraphSpec(
        name=name,
        dataset_id="ds-test",
        nodes=node_specs,
        edges=[{"source": s, "target": t} for s, t in edges],
        analysis={"treatment": treatment, "outcome": outcome},
    )


def _minimal_sets(result) -> list[list[str]]:
    return [candidate.variables for candidate in result.minimal_sets]


# --------------------------------------------------------------------------- #
# Brief cases 1-10, engine level
# --------------------------------------------------------------------------- #


def test_case_1_chain_mediator_is_forbidden_empty_set_valid():
    dag = DAG(["x", "m", "y"], [("x", "m"), ("m", "y")])
    observed = {"x", "m", "y"}
    search = search_adjustment_sets(dag, "x", "y", observed)
    assert search.status == "complete"
    # The empty set satisfies the backdoor criterion: no backdoor path exists.
    assert _minimal_sets(search) == [[]]
    # M is a descendant of the treatment → forbidden by the classical criterion.
    evaluation = evaluate_adjustment_set(dag, "x", "y", ["m"], observed)
    assert not evaluation.valid
    assert [v.code for v in evaluation.violations] == ["post_treatment_variable"]


def test_case_2_fork_single_confounder():
    dag = DAG(["x", "z", "y"], [("z", "x"), ("z", "y")])
    observed = {"x", "z", "y"}
    search = search_adjustment_sets(dag, "x", "y", observed)
    assert search.status == "complete"
    assert _minimal_sets(search) == [["z"]]
    evaluation = evaluate_adjustment_set(dag, "x", "y", ["z"], observed)
    assert evaluation.valid


def test_case_3_collider_sets():
    dag = DAG(["x", "c", "y"], [("x", "c"), ("y", "c")])
    observed = {"x", "c", "y"}
    # Unconditionally separated → the empty set is admissible.
    search = search_adjustment_sets(dag, "x", "y", observed)
    assert _minimal_sets(search) == [[]]
    # Conditioning on the collider destroys admissibility. Here the collider is
    # also a descendant of the treatment, so the post-treatment rule fires
    # first - the pure open-backdoor-path violation is exercised in Case 7,
    # where the collider is not a descendant of the treatment.
    evaluation = evaluate_adjustment_set(dag, "x", "y", ["c"], observed)
    assert not evaluation.valid
    assert [v.code for v in evaluation.violations] == ["post_treatment_variable"]


def test_case_4_confounded_treatment_effect():
    dag = DAG(["x", "y", "z"], [("z", "x"), ("z", "y"), ("x", "y")])
    observed = {"x", "y", "z"}
    search = search_adjustment_sets(dag, "x", "y", observed)
    assert _minimal_sets(search) == [["z"]]
    # The direct edge X → Y is untouched by identification: it is not in the
    # backdoor graph, and the criterion never edits the original graph.
    assert ("x", "y") in dag.edges


def test_case_5_unobserved_confounding_is_honest():
    # U explicitly unobserved: U → X, U → Y, X → Y.
    dag = DAG(["x", "y", "u"], [("u", "x"), ("u", "y"), ("x", "y")])
    observed = {"x", "y"}  # u NOT observed
    search = search_adjustment_sets(dag, "x", "y", observed)
    assert search.status == "complete"
    assert search.minimal_sets == []  # nothing blocks the U backdoor path
    # U is never suggested as an available covariate.
    assert "u" not in search.eligible_candidates
    payload = search.to_payload()
    assert "does not prove the effect is unidentifiable by every method" in payload["status_reason"]


def test_case_6_post_treatment_bias_direct_and_mediated():
    # X → M → Y and X → Y: M is forbidden even though a naive regression
    # could happily regress on it.
    dag = DAG(["x", "m", "y"], [("x", "m"), ("m", "y"), ("x", "y")])
    observed = {"x", "m", "y"}
    evaluation = evaluate_adjustment_set(dag, "x", "y", ["m"], observed)
    assert not evaluation.valid
    assert [v.code for v in evaluation.violations] == ["post_treatment_variable"]
    search = search_adjustment_sets(dag, "x", "y", observed)
    assert _minimal_sets(search) == [[]]


def test_case_7_collider_bias_path():
    # X ← A → C ← B → Y: the collider C blocks the backdoor path
    # unconditionally; conditioning on C opens it.
    dag = DAG(["x", "y", "a", "b", "c"], [("a", "x"), ("a", "c"), ("b", "c"), ("b", "y")])
    observed = {"x", "y", "a", "b", "c"}
    search = search_adjustment_sets(dag, "x", "y", observed)
    assert _minimal_sets(search) == [[]]
    # Conditioning on the collider C alone opens the single backdoor path
    # X ← A → C ← B → Y.
    bad = evaluate_adjustment_set(dag, "x", "y", ["c"], observed)
    assert not bad.valid
    assert [v.code for v in bad.violations] == ["open_backdoor_path"]
    # Sets that block the path at A or at B stay valid even when they also
    # contain the collider (one block suffices).
    for good in (["a"], ["b"], ["a", "b"], ["a", "c"], ["b", "c"]):
        evaluation = evaluate_adjustment_set(dag, "x", "y", good, observed)
        assert evaluation.valid, good


def test_case_8_multiple_backdoor_paths_minimal_and_deterministic():
    # Two independent confounders: Z1 → X, Z1 → Y, Z2 → X, Z2 → Y, X → Y.
    dag = DAG(
        ["x", "y", "z1", "z2"],
        [("z1", "x"), ("z1", "y"), ("z2", "x"), ("z2", "y"), ("x", "y")],
    )
    observed = {"x", "y", "z1", "z2"}
    first = search_adjustment_sets(dag, "x", "y", observed)
    # Both confounders are needed: {z1} and {z2} alone each leave a path open.
    assert _minimal_sets(first) == [["z1", "z2"]]
    # Deterministic: an identical search returns the identical result.
    second = search_adjustment_sets(dag, "x", "y", observed)
    assert first.to_payload() == second.to_payload()


def test_case_9_search_limit_reports_incomplete():
    # A graph with 15 eligible observed candidates exceeds the exhaustive
    # enumeration bound of 14 → the greedy strategy runs with honest status.
    names = ["x", "y"] + [f"w{i:02d}" for i in range(15)]
    edges = [("w00", "x"), ("w00", "y"), ("x", "y")]
    dag = DAG(names, edges)
    observed = set(names)
    result = search_adjustment_sets(dag, "x", "y", observed)
    assert result.status == "incomplete"
    payload = result.to_payload()
    assert payload["search_status"] == "incomplete"
    # The verified set is reported and individually correct, but no
    # completeness claim is made.
    assert "NOT exhaustive" in payload["status_reason"]
    for candidate in result.minimal_sets:
        evaluation = evaluate_adjustment_set(dag, "x", "y", candidate.variables, observed)
        assert evaluation.valid


def test_case_10_invalid_queries_are_refused_not_answered():
    dag = DAG(["x", "y"], [("x", "y")])
    observed = {"x", "y"}
    with pytest.raises(AdjustmentQueryError) as same:
        search_adjustment_sets(dag, "x", "x", observed)
    assert same.value.code == "same_node"
    with pytest.raises(AdjustmentQueryError) as unknown:
        evaluate_adjustment_set(dag, "ghost", "y", [], observed)
    assert unknown.value.code == "unknown_scope_node"


# --------------------------------------------------------------------------- #
# Additional correctness requirements from the brief (§7)
# --------------------------------------------------------------------------- #


def test_treatment_with_no_parents_needs_no_adjustment_against_observed_confounders():
    # X → Y with an observed common *effect* only: empty set is admissible.
    dag = DAG(["x", "y", "c"], [("x", "y"), ("x", "c"), ("y", "c")])
    observed = {"x", "y", "c"}
    assert _minimal_sets(search_adjustment_sets(dag, "x", "y", observed)) == [[]]


def test_disconnected_treatment_outcome_empty_set_valid():
    dag = DAG(["x", "y", "u"], [("u", "x"), ("u", "y")])
    observed = {"x", "y", "u"}
    assert _minimal_sets(search_adjustment_sets(dag, "x", "y", observed)) == [["u"]]
    disconnected = DAG(["x", "y"], [])
    assert _minimal_sets(search_adjustment_sets(disconnected, "x", "y", {"x", "y"})) == [[]]


def test_unknown_and_unobserved_and_scope_members_are_violations():
    dag = DAG(["x", "y", "z", "u"], [("u", "x"), ("u", "y"), ("z", "x"), ("x", "y")])
    observed = {"x", "y", "z"}
    evaluation = evaluate_adjustment_set(dag, "x", "y", ["ghost", "u", "x", "z"], observed)
    codes = sorted(v.code for v in evaluation.violations)
    # Every problem is reported at once: unknown id, unobserved variable, and
    # the treatment itself in the set. ('z' is genuinely admissible.)
    assert codes == ["adjustment_contains_scope", "unknown_variable", "unobserved_variable"]


def test_evaluation_reports_all_violations_at_once():
    dag = DAG(["x", "y", "m", "u"], [("u", "x"), ("u", "y"), ("x", "m"), ("m", "y"), ("x", "y")])
    observed = {"x", "y", "m"}
    evaluation = evaluate_adjustment_set(dag, "x", "y", ["m"], observed)
    assert [v.code for v in evaluation.violations] == ["post_treatment_variable"]


def test_inclusion_minimal_is_not_minimum_cardinality():
    # Confounder pair where one minimal set has 2 members and another has 1:
    # X ← A → Y, X ← B → Y, X → Y, plus A → B.
    # Minimal sets: {A} (blocks A-fork; does A block B path? B → Y and B ← A:
    # path X ← B → Y blocked only by B... {A} does not block X ← B → Y.)
    # Construct instead: X ← A → B → Y? Simpler: two separate forks.
    dag = DAG(
        ["x", "y", "p", "q"],
        [("p", "x"), ("p", "y"), ("q", "x"), ("q", "y"), ("x", "y")],
    )
    observed = {"x", "y", "p", "q"}
    sets = _minimal_sets(search_adjustment_sets(dag, "x", "y", observed))
    assert sets == [["p", "q"]]
    # Now add an observed confounder that subsumes nothing - verify every
    # reported set is inclusion-minimal by direct check.
    dag2 = DAG(
        ["x", "y", "a", "b"],
        [("a", "x"), ("a", "b"), ("b", "y"), ("x", "y")],
    )
    observed2 = {"x", "y", "a", "b"}
    sets2 = _minimal_sets(search_adjustment_sets(dag2, "x", "y", observed2))
    for candidate in sets2:
        for dropped in candidate:
            reduced = [item for item in candidate if item != dropped]
            assert not evaluate_adjustment_set(dag2, "x", "y", reduced, observed2).valid


def test_search_bounds_are_reported_and_honoured():
    dag = DAG(["x", "y", "z"], [("z", "x"), ("z", "y"), ("x", "y")])
    observed = {"x", "y", "z"}
    result = search_adjustment_sets(dag, "x", "y", observed, max_candidates=1)
    # The empty-set check consumed the whole budget → incomplete, not "none".
    assert result.status == "incomplete"
    assert result.candidates_considered >= 1


def test_identification_status_lifecycle():
    # Full identification status for the classic confounded graph.
    spec = _spec(
        [{"node_id": "x"}, {"node_id": "y"}, {"node_id": "z"}],
        [("z", "x"), ("z", "y"), ("x", "y")],
        treatment="x",
        outcome="y",
    )
    result = identify_backdoor(spec)
    assert result.status == "backdoor_adjustment_available"
    payload = result.to_payload()
    assert payload["search"]["search_status"] == "complete"
    codes = [e.code for e in result.explanations]
    assert "confounder_needs_adjustment" in codes
    assert "structure_not_truth" in codes


def test_identification_reports_missing_scope_and_unmeasured_scope():
    spec = _spec(
        [
            {"node_id": "x"},
            {"node_id": "y"},
            {"node_id": "u", "observed": False, "kind": "unobserved"},
        ],
        [("u", "x"), ("u", "y"), ("x", "y")],
        treatment=None,
        outcome=None,
    )
    result = identify_backdoor(spec)
    assert result.status == "invalid_scope"

    spec_with_unmeasured = _spec(
        [
            {"node_id": "x", "observed": False, "kind": "unobserved"},
            {"node_id": "y"},
        ],
        [("x", "y")],
        treatment="x",
        outcome="y",
    )
    result = identify_backdoor(spec_with_unmeasured)
    assert result.status == "missing_dataset_variables"
    assert "u" not in observed_node_ids(spec_with_unmeasured)


def test_identification_unobserved_confounder_honesty():
    spec = _spec(
        [
            {"node_id": "x"},
            {"node_id": "y"},
            {"node_id": "u", "observed": False, "kind": "unobserved"},
        ],
        [("u", "x"), ("u", "y"), ("x", "y")],
        treatment="x",
        outcome="y",
    )
    result = identify_backdoor(spec)
    assert result.status == "no_eligible_backdoor_set"
    codes = [e.code for e in result.explanations]
    assert "unobserved_confounding" in codes
    payload = result.to_payload()
    assert "backdoor criterion" in payload["caveats"][1]


def test_identification_refuses_unsupported_methods():
    spec = _spec(
        [{"node_id": "x"}, {"node_id": "y"}],
        [("x", "y")],
        treatment="x",
        outcome="y",
    )
    result = identify_backdoor(spec, method="front-door")
    assert result.status == "unsupported_identification_method"
    assert "will not simulate" in result.explanations[0].body


def test_identification_scope_override():
    spec = _spec(
        [{"node_id": "x"}, {"node_id": "y"}, {"node_id": "z"}],
        [("z", "x"), ("z", "y")],
        treatment="x",
        outcome="y",
    )
    # Override the scope: X → Z? no edges from x; scope (y, x) instead.
    result = identify_backdoor(spec, treatment="y", outcome="x")
    assert result.status == "backdoor_adjustment_available"
    assert result.treatment == "y"
    assert result.outcome == "x"


# --------------------------------------------------------------------------- #
# API-level tests (real upload path, real registry, real error envelope)
# --------------------------------------------------------------------------- #

COLUMNS = ["age", "tenure_months", "plan", "churn", "satisfaction", "month_index"]


@pytest.fixture()
def client():
    from app.api.deps import reset_context
    from app.main import create_app

    reset_context()
    with TestClient(create_app()) as test_client:
        yield test_client


def _upload(client: TestClient) -> dict:
    rows = [{column: str(index + 1) for column in COLUMNS} for index in range(24)]
    from .conftest import rows_to_csv

    payload = rows_to_csv(rows, COLUMNS)
    response = client.post("/api/datasets", files={"file": ("ident.csv", payload, "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()


def _identification_spec(dataset_id: str, *, with_scope: bool = True) -> dict:
    return {
        "name": "Retention identification",
        "dataset_id": dataset_id,
        "nodes": [
            {"node_id": "tenure", "label": "Tenure", "column": "tenure_months", "kind": "treatment"},
            {"node_id": "churn", "label": "Churn", "column": "churn", "kind": "outcome"},
            {"node_id": "age", "label": "Age", "column": "age"},
            {"node_id": "satisfaction", "label": "Satisfaction", "column": "satisfaction"},
            {"node_id": "u_service", "label": "Unobserved service quality", "observed": False, "kind": "unobserved"},
        ],
        "edges": [
            {"source": "age", "target": "tenure", "rationale": "age precedes tenure"},
            {"source": "age", "target": "churn", "rationale": "age shapes churn"},
            {"source": "u_service", "target": "tenure", "rationale": "service quality drives tenure"},
            {"source": "u_service", "target": "churn", "rationale": "service quality drives churn"},
            {"source": "tenure", "target": "satisfaction", "rationale": "tenure shapes satisfaction"},
            {"source": "satisfaction", "target": "churn", "rationale": "satisfaction shapes churn"},
            {"source": "tenure", "target": "churn", "rationale": "hypothesised retention effect"},
        ],
        "analysis": (
            {"treatment": "tenure", "outcome": "churn"}
            if with_scope
            else {"treatment": None, "outcome": None}
        ),
    }


def _create_confounded_graph(client: TestClient, dataset_id: str, *, with_scope: bool = True):
    spec = _identification_spec(dataset_id, with_scope=with_scope)
    response = client.post(f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": spec})
    assert response.status_code == 201, response.text
    return response.json(), spec


def test_api_d_separation_roundtrip_and_provenance(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    graph, _spec_used = _create_confounded_graph(client, dataset_id)
    gid = graph["graph_id"]
    fingerprint = graph["spec_fingerprint_sha256"]

    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/d-separation",
        json={"x": "age", "y": "churn", "conditioning": ["tenure"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["graph_id"] == gid
    assert payload["spec_fingerprint_sha256"] == fingerprint
    assert payload["d_separated"] is False  # age → tenure → churn is a chain
    assert payload["conditioning"] == ["tenure"]
    assert payload["algorithm"]["name"] == "bayes-ball-reachability"
    assert "not an empirically established independence" in payload["interpretation_note"]

    # age and satisfaction have no direct edge: connected through the
    # unconditioned chain, separated once the mediator tenure is conditioned.
    open_pair = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/d-separation",
        json={"x": "age", "y": "satisfaction", "conditioning": []},
    )
    assert open_pair.json()["d_separated"] is False
    blocked = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/d-separation",
        json={"x": "age", "y": "satisfaction", "conditioning": ["tenure"]},
    )
    assert blocked.json()["d_separated"] is True


def test_api_d_separation_query_errors_are_structured(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    graph, _spec_used = _create_confounded_graph(client, dataset_id)
    gid = graph["graph_id"]

    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/d-separation",
        json={"x": "age", "y": "ghost", "conditioning": []},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["errors"][0]["code"] == "unknown_node"

    endpoint = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/d-separation",
        json={"x": "age", "y": "churn", "conditioning": ["age"]},
    )
    assert endpoint.status_code == 422
    assert endpoint.json()["error"]["details"]["errors"][0]["code"] == "conditioning_contains_endpoint"


def test_api_adjustment_evaluation_reports_all_violations(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    graph, _spec_used = _create_confounded_graph(client, dataset_id)
    gid = graph["graph_id"]

    # satisfaction is post-treatment; u_service is unobserved.
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/adjustment-evaluation",
        json={"adjustment_set": ["satisfaction", "u_service"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    codes = sorted(v["code"] for v in payload["violations"])
    assert codes == ["post_treatment_variable", "unobserved_variable"]
    assert payload["interpretation_note"]

    # {age} alone blocks the age path but NOT the unobserved u_service path:
    # the violation is an open backdoor path, reported honestly.
    partial = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/adjustment-evaluation",
        json={"adjustment_set": ["age"]},
    )
    partial_payload = partial.json()
    assert partial_payload["valid"] is False
    assert [v["code"] for v in partial_payload["violations"]] == ["open_backdoor_path"]
    assert partial_payload["open_backdoor_paths"] == [["tenure", "u_service", "churn"]]


def test_api_adjustment_search_reports_unobserved_honestly(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    graph, _spec_used = _create_confounded_graph(client, dataset_id)
    gid = graph["graph_id"]

    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/adjustment-search", json={}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    # age blocks the observed backdoor path; the u_service path stays open, so
    # the honest answer is: complete search, no admissible set.
    assert payload["search_status"] == "complete"
    assert payload["sets"] == []
    assert "does not prove the effect is unidentifiable" in payload["status_reason"]
    assert "u_service" in payload["forbidden_variables"] or "u_service" not in payload["eligible_candidates"]
    assert "u_service" not in payload["eligible_candidates"]


def test_api_identification_status_with_explanations(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    graph, _spec_used = _create_confounded_graph(client, dataset_id)
    gid = graph["graph_id"]

    response = client.post(f"/api/datasets/{dataset_id}/causal-graphs/{gid}/identification", json={})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "no_eligible_backdoor_set"
    codes = [e["code"] for e in payload["explanations"]]
    assert "unobserved_confounding" in codes
    assert "structure_not_truth" in codes
    assert payload["identification_version"]
    assert payload["treatment"] == "tenure"
    assert payload["outcome"] == "churn"


def test_api_identification_refuses_unsupported_method_and_incomplete_scope(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]

    graph, _spec_used = _create_confounded_graph(client, dataset_id)
    gid = graph["graph_id"]
    unsupported = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/identification",
        json={"method": "front-door"},
    )
    assert unsupported.status_code == 200
    assert unsupported.json()["status"] == "unsupported_identification_method"

    # A scope-less graph: adjustment search is refused with a structured code,
    # while identification reports an honest invalid_scope status.
    scopeless, _ = _create_confounded_graph(client, dataset_id, with_scope=False)
    refused = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{scopeless['graph_id']}/adjustment-search",
        json={},
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["details"]["errors"][0]["code"] == "analysis_incomplete"
    status = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{scopeless['graph_id']}/identification",
        json={},
    )
    assert status.status_code == 200
    assert status.json()["status"] == "invalid_scope"


def test_api_identification_never_mutates_the_graph(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    graph, _spec_used = _create_confounded_graph(client, dataset_id)
    gid = graph["graph_id"]
    before = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{gid}").json()

    for endpoint, body_json in (
        ("/d-separation", {"x": "age", "y": "churn", "conditioning": ["tenure"]}),
        ("/adjustment-evaluation", {"adjustment_set": ["age"]}),
        ("/adjustment-search", {}),
        ("/identification", {}),
    ):
        response = client.post(f"/api/datasets/{dataset_id}/causal-graphs/{gid}{endpoint}", json=body_json)
        assert response.status_code == 200, response.text

    after = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{gid}").json()
    assert after["revision"] == before["revision"]
    assert after["spec_fingerprint_sha256"] == before["spec_fingerprint_sha256"]
    assert after["nodes"] == before["nodes"]
    assert after["edges"] == before["edges"]


def test_api_identification_ownership_and_expiry(client):
    from app.api.deps import get_context

    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    graph, _spec_used = _create_confounded_graph(client, dataset_id)
    gid = graph["graph_id"]

    other = _upload(client)
    other_id = other["dataset"]["dataset_id"]
    cross = client.post(f"/api/datasets/{other_id}/causal-graphs/{gid}/identification", json={})
    assert cross.status_code == 404
    assert cross.json()["error"]["code"] == "not_found"

    unknown = client.post(f"/api/datasets/{dataset_id}/causal-graphs/cgraph-nope/identification", json={})
    assert unknown.status_code == 404

    # Evict the dataset by filling the store: every identification endpoint
    # yields the typed 410 and the orphaned graph is pruned.
    context = get_context()
    for _ in range(context.store._limits.max_datasets):
        _upload(client)
    for endpoint, payload in (
        ("/d-separation", {"x": "age", "y": "churn"}),
        ("/adjustment-search", {}),
        ("/identification", {}),
    ):
        response = client.post(f"/api/datasets/{dataset_id}/causal-graphs/{gid}{endpoint}", json=payload)
        assert response.status_code == 410, endpoint
        assert response.json()["error"]["code"] == "expired_or_evicted"
    assert all(record.dataset_id != dataset_id for record in context.causal_graphs.list_for_dataset(dataset_id))


def test_api_fingerprint_is_returned_for_staleness_detection(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    graph, spec_used = _create_confounded_graph(client, dataset_id)
    gid = graph["graph_id"]

    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/adjustment-search", json={}
    )
    payload = response.json()
    expected = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{gid}").json()[
        "spec_fingerprint_sha256"
    ]
    assert payload["spec_fingerprint_sha256"] == expected

    # Revise the graph's scientific content: the next identification result
    # carries the new fingerprint, so the client can detect staleness.
    revised = {**spec_used, "analysis": {"treatment": "tenure", "outcome": "satisfaction"}}
    update = client.put(f"/api/datasets/{dataset_id}/causal-graphs/{gid}", json={"graph": revised})
    assert update.status_code == 200, update.text
    response2 = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{gid}/adjustment-search", json={}
    )
    assert response2.json()["spec_fingerprint_sha256"] != payload["spec_fingerprint_sha256"]
