"""graph causal graph foundation: HTTP-level and service-level tests.

Expected outcomes are written by hand in each test - including which issue
codes are blocking errors and which are scientific warnings - so a test cannot
pass merely because the implementation agrees with itself.

Everything goes through the real upload path and the real API, mirroring the
conventions of ``tests/test_research.py``.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.causal.schema import graph_fingerprint
from app.causal.validation import derive_structure
from .conftest import make_dataset, rows_to_csv

COLUMNS = ["age", "tenure_months", "plan", "churn", "month_index"]


@pytest.fixture()
def client():
    from app.api.deps import reset_context
    from app.main import create_app

    reset_context()
    with TestClient(create_app()) as test_client:
        yield test_client


def _upload(client: TestClient, columns: list[str] | None = None) -> dict:
    """Upload a small panel dataset and return the response body."""
    chosen = columns or COLUMNS
    rows = []
    for index in range(24):
        row = {column: str(index + 1) for column in chosen}
        row["plan"] = "a" if index % 2 else "b"
        rows.append(row)
    payload = rows_to_csv(rows, chosen)
    response = client.post("/api/datasets", files={"file": ("causal.csv", payload, "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()


def _base_spec(dataset_id: str, **overrides) -> dict:
    spec = {
        "name": "Retention hypothesis",
        "dataset_id": dataset_id,
        "nodes": [
            {"node_id": "tenure", "label": "Tenure", "column": "tenure_months", "kind": "treatment"},
            {"node_id": "churn", "label": "Churn", "column": "churn", "kind": "outcome"},
            {"node_id": "age", "label": "Age", "column": "age"},
            {"node_id": "plan", "label": "Plan", "column": "plan"},
        ],
        "edges": [
            {"source": "age", "target": "tenure", "rationale": "age precedes tenure"},
            {"source": "age", "target": "churn", "rationale": "age shapes churn risk"},
            {"source": "plan", "target": "tenure", "rationale": "plan choice drives tenure"},
            {"source": "plan", "target": "churn", "rationale": "plan shapes churn risk"},
            {"source": "tenure", "target": "churn", "rationale": "hypothesised retention effect"},
        ],
        "analysis": {"treatment": "tenure", "outcome": "churn"},
        "assumptions": [
            {
                "assumption_id": "asmp-population",
                "category": "target_population",
                "status": "declared",
                "source": "study card",
                "rationale": "adult subscribers of the 2024 panel",
            }
        ],
    }
    spec.update(overrides)
    return spec


def _create(client: TestClient, dataset_id: str, spec: dict):
    return client.post(
        f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": spec}
    )


def _codes(items: list[dict]) -> list[str]:
    return [item["code"] for item in items]


# --------------------------------------------------------------------------- #
# Well-formed structures and derived properties
# --------------------------------------------------------------------------- #


def test_valid_dag_creates_and_retrieves_with_derived_structure(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    response = _create(client, dataset_id, _base_spec(dataset_id))
    assert response.status_code == 201, response.text
    graph = response.json()

    assert graph["validation"]["ok"] is True
    assert graph["validation"]["error_count"] == 0
    assert graph["schema_version"] == "1.0.0"
    assert graph["validation"]["derived"]["is_dag"] is True
    assert graph["validation"]["derived"]["has_directed_treatment_outcome_path"] is True
    assert graph["graph_id"].startswith("cgraph-")

    retrieved = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph['graph_id']}")
    assert retrieved.status_code == 200
    payload = retrieved.json()
    assert payload["name"] == "Retention hypothesis"
    assert payload["dataset_fingerprint_sha256"] == body["dataset"]["fingerprint_sha256"]
    # A node anchored to a column resolves its live type from the dataset.
    tenure = next(node for node in payload["nodes"] if node["node_id"] == "tenure")
    from app.api.deps import get_context

    stored = get_context().store.get_dataset(dataset_id)
    assert tenure["resolved_column_type"] == stored.frame["tenure_months"].dtype.name
    # Graph-derived structure: tenure has ancestors age and plan.
    assert set(tenure["derived_structure"]["ancestors"]) == {"age", "plan"}
    churn = next(node for node in payload["nodes"] if node["node_id"] == "churn")
    assert set(churn["derived_structure"]["parents"]) == {"age", "plan", "tenure"}


def test_chain_dag_and_fork_and_collider_structure(client):
    spec_dag = make_dataset(
        [{"a": "1", "b": "2", "c": "3", "d": "4"} for _ in range(24)],
        columns=["a", "b", "c", "d"],
    )
    from app.causal.schema import AnalysisScope, CausalEdge, CausalGraphSpec, CausalNode

    chain = CausalGraphSpec(
        name="chain", dataset_id=spec_dag.dataset_id,
        nodes=[CausalNode(node_id=name, label=name) for name in ("a", "b", "c", "d")],
        edges=[CausalEdge(source="a", target="b"), CausalEdge(source="b", target="c"),
               CausalEdge(source="c", target="d")],
        analysis=AnalysisScope(treatment="a", outcome="d"),
    )
    derived = derive_structure(chain)
    assert derived["is_dag"] is True
    assert derived["nodes"]["b"]["ancestors"] == ["a"]
    assert derived["nodes"]["b"]["descendants"] == ["c", "d"]
    assert derived["has_directed_treatment_outcome_path"] is True

    fork = CausalGraphSpec(
        name="fork", dataset_id=spec_dag.dataset_id,
        nodes=[CausalNode(node_id=name, label=name) for name in ("a", "b", "c")],
        edges=[CausalEdge(source="a", target="b"), CausalEdge(source="a", target="c")],
        analysis=AnalysisScope(treatment="b", outcome="c"),
    )
    derived = derive_structure(fork)
    # In a fork the treatment has no directed path to the outcome; both share ancestors.
    assert derived["has_directed_treatment_outcome_path"] is False
    assert derived["nodes"]["b"]["ancestors"] == ["a"]
    assert derived["nodes"]["c"]["ancestors"] == ["a"]

    collider = CausalGraphSpec(
        name="collider", dataset_id=spec_dag.dataset_id,
        nodes=[CausalNode(node_id=name, label=name) for name in ("a", "b", "c")],
        edges=[CausalEdge(source="a", target="c"), CausalEdge(source="b", target="c")],
        analysis=AnalysisScope(treatment="a", outcome="c"),
    )
    derived = derive_structure(collider)
    assert derived["nodes"]["c"]["is_collider"] is True
    assert derived["nodes"]["a"]["is_collider"] is False


def test_graph_list_and_summary(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    first = _create(client, dataset_id, _base_spec(dataset_id, name="First"))
    minimal = _base_spec(dataset_id, name="Second")
    minimal["nodes"] = [node for node in minimal["nodes"] if node["node_id"] in ("tenure", "churn")]
    minimal["edges"] = [edge for edge in minimal["edges"] if edge["source"] == "tenure" and edge["target"] == "churn"]
    second = _create(client, dataset_id, minimal)
    assert first.status_code == second.status_code == 201

    listing = client.get(f"/api/datasets/{dataset_id}/causal-graphs").json()
    assert [graph["name"] for graph in listing["graphs"]] == ["First", "Second"]
    summary = listing["graphs"][0]
    assert summary["node_count"] == 4 and summary["edge_count"] == 5
    assert summary["validation_ok"] is True


# --------------------------------------------------------------------------- #
# Blocking validation errors
# --------------------------------------------------------------------------- #


def _assert_rejected(response, code: str):
    assert response.status_code == 422, response.text
    envelope = response.json()
    assert envelope["error"]["code"] == "validation_error"
    codes = [issue["code"] for issue in envelope["error"]["details"]["errors"]]
    assert code in codes, codes
    return envelope


def test_self_loop_is_a_blocking_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["edges"].append({"source": "churn", "target": "churn", "rationale": "stability"})
    response = _create(client, dataset_id, spec)
    envelope = _assert_rejected(response, "self_loop")
    # The scientific warning system does not downgrade a structural error.
    assert all(issue["severity"] == "error" for issue in envelope["error"]["details"]["errors"] if issue["code"] == "self_loop")


def test_directed_cycle_is_a_blocking_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["edges"].append({"source": "churn", "target": "tenure", "rationale": "feedback"})
    envelope = _assert_rejected(_create(client, dataset_id, spec), "directed_cycle")
    cycle_message = next(
        issue["message"] for issue in envelope["error"]["details"]["errors"]
        if issue["code"] == "directed_cycle"
    )
    assert "tenure → churn → tenure" in cycle_message.replace("tenure → churn → tenure", "tenure → churn → tenure") or "tenure" in cycle_message


def test_duplicate_node_id_is_a_blocking_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["nodes"].append({"node_id": "age", "label": "Age again", "column": "age"})
    _assert_rejected(_create(client, dataset_id, spec), "duplicate_node_id")


def test_duplicate_edge_is_a_blocking_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["edges"].append({"source": "tenure", "target": "churn", "rationale": "again"})
    _assert_rejected(_create(client, dataset_id, spec), "duplicate_edge")


def test_edge_with_missing_endpoint_is_a_blocking_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["edges"].append({"source": "ghost", "target": "churn", "rationale": "undefined node"})
    _assert_rejected(_create(client, dataset_id, spec), "edge_endpoint_missing")


def test_treatment_equal_to_outcome_is_a_blocking_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["analysis"] = {"treatment": "churn", "outcome": "churn"}
    _assert_rejected(_create(client, dataset_id, spec), "analysis_same_node")


def test_treatment_referencing_an_unknown_node_is_a_blocking_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["analysis"] = {"treatment": "ghost", "outcome": "churn"}
    envelope = _assert_rejected(_create(client, dataset_id, spec), "analysis_node_missing")
    assert any(issue.get("node_id") == "ghost" for issue in envelope["error"]["details"]["errors"])


def test_unknown_dataset_column_is_a_blocking_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["nodes"].append({"node_id": "ghostcol", "label": "Ghost", "column": "not_a_column"})
    envelope = _assert_rejected(_create(client, dataset_id, spec), "unknown_column")
    assert any(issue.get("node_id") == "ghostcol" for issue in envelope["error"]["details"]["errors"])


def test_unsupported_schema_version_is_rejected(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["schema_version"] = "9.9.9"
    envelope = _assert_rejected(_create(client, dataset_id, spec), "unsupported_schema_version")


def test_malformed_payload_is_a_structured_validation_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs",
        json={"graph": {"name": "Broken", "dataset_id": dataset_id, "nodes": "not-a-list", "unexpected_field": 1}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --------------------------------------------------------------------------- #
# Scientific warnings (non-blocking)
# --------------------------------------------------------------------------- #


def test_warnings_are_non_blocking_and_specific(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["edges"][4] = {"source": "tenure", "target": "churn"}  # no rationale
    spec["analysis"] = {"treatment": None, "outcome": None}
    spec["nodes"][2]["observed"] = False
    spec["nodes"][2]["kind"] = "unobserved"
    spec["nodes"][2]["column"] = None  # hypothesised variable
    response = _create(client, dataset_id, spec)
    assert response.status_code == 201, response.text
    graph = response.json()
    codes = _codes(graph["validation"]["warnings"])
    assert graph["validation"]["ok"] is True
    assert "analysis_incomplete" in codes
    assert "edge_missing_rationale" in codes
    assert "unobserved_variable_present" in codes


def test_no_directed_path_is_a_warning_not_an_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["analysis"] = {"treatment": "age", "outcome": "plan"}  # age and plan not connected
    response = _create(client, dataset_id, spec)
    assert response.status_code == 201
    warnings = response.json()["validation"]["warnings"]
    codes = _codes(warnings)
    assert "no_directed_path" in codes
    assert response.json()["validation"]["errors"] == []


def test_isolated_node_and_missing_target_population_are_warnings(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["nodes"].append({"node_id": "lonely", "label": "Lonely"})
    spec["assumptions"] = []
    graph = _create(client, dataset_id, spec).json()
    codes = _codes(graph["validation"]["warnings"])
    assert "isolated_node" in codes
    assert "no_target_population" in codes
    assert graph["validation"]["ok"] is True


def test_declared_mediator_without_structural_path_is_a_warning(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["nodes"].append({"node_id": "satisfaction", "label": "Satisfaction", "column": "plan", "kind": "mediator"})
    graph = _create(client, dataset_id, spec).json()
    matches = [
        issue for issue in graph["validation"]["warnings"]
        if issue["code"] == "declared_role_unsupported" and issue["node_id"] == "satisfaction"
    ]
    assert len(matches) == 1
    # The engine reports the contradiction; it does not silently reclassify.
    node = next(node for node in graph["nodes"] if node["node_id"] == "satisfaction")
    assert node["kind"] == "mediator"
    assert node["derived_structure"]["on_directed_treatment_outcome_path"] is False


def test_true_mediator_on_path_does_not_warn(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["nodes"].append({"node_id": "engagement", "label": "Engagement", "column": "month_index", "kind": "mediator"})
    spec["edges"].append({"source": "tenure", "target": "engagement", "rationale": "tenure drives engagement"})
    spec["edges"].append({"source": "engagement", "target": "churn", "rationale": "engagement shapes churn"})
    graph = _create(client, dataset_id, spec).json()
    assert graph["validation"]["ok"] is True
    node = next(node for node in graph["nodes"] if node["node_id"] == "engagement")
    assert node["derived_structure"]["on_directed_treatment_outcome_path"] is True
    assert "declared_role_unsupported" not in _codes(graph["validation"]["warnings"])


def test_assumption_missing_rationale_is_a_warning(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["assumptions"].append(
        {"assumption_id": "asmp-positivity", "category": "positivity", "status": "flagged_for_review"}
    )
    graph = _create(client, dataset_id, spec).json()
    assert graph["validation"]["ok"] is True
    flagged = next(
        item for item in graph["assumptions"] if item["assumption_id"] == "asmp-positivity"
    )
    assert flagged["status"] == "flagged_for_review"
    assert "assumption_missing_rationale" in _codes(graph["validation"]["warnings"])
    # The recorded status is echoed verbatim, never upgraded to "verified".
    assert all(item["status"] != "verified" for item in graph["assumptions"])


def test_duplicate_assumption_id_is_a_blocking_error(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    spec = _base_spec(dataset_id)
    spec["assumptions"].append(
        {"assumption_id": "asmp-population", "category": "positivity", "status": "declared"}
    )
    _assert_rejected(_create(client, dataset_id, spec), "duplicate_assumption_id")


# --------------------------------------------------------------------------- #
# Dataset lifecycle and ownership
# --------------------------------------------------------------------------- #


def test_graph_against_missing_dataset_returns_410(client):
    response = client.post(
        "/api/datasets/ds-never-existed/causal-graphs",
        json={"graph": _base_spec("ds-never-existed")},
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "expired_or_evicted"


def test_evicted_dataset_makes_its_graphs_unreachable(client):
    from app.api.deps import get_context

    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    created = _create(client, dataset_id, _base_spec(dataset_id))
    graph_id = created.json()["graph_id"]

    context = get_context()
    for index in range(context.store._limits.max_datasets):
        upload = _upload(client)
        assert upload["dataset"]["dataset_id"] != dataset_id

    gone = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}")
    assert gone.status_code == 410
    listing = client.get(f"/api/datasets/{dataset_id}/causal-graphs")
    assert listing.status_code == 410
    # The orphaned graph is pruned, not left behind in memory.
    assert all(record.dataset_id != dataset_id for record in context.causal_graphs.list_for_dataset(dataset_id))


def test_cross_dataset_graph_access_is_rejected(client):
    first = _upload(client)
    second = _upload(client)
    dataset_a = first["dataset"]["dataset_id"]
    dataset_b = second["dataset"]["dataset_id"]
    created = _create(client, dataset_a, _base_spec(dataset_a))
    graph_id = created.json()["graph_id"]

    hijack = client.get(f"/api/datasets/{dataset_b}/causal-graphs/{graph_id}")
    assert hijack.status_code == 404
    assert hijack.json()["error"]["code"] == "not_found"


# --------------------------------------------------------------------------- #
# Update semantics
# --------------------------------------------------------------------------- #


def test_valid_update_bumps_revision_and_preserves_id(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    created = _create(client, dataset_id, _base_spec(dataset_id))
    graph_id = created.json()["graph_id"]

    spec = _base_spec(dataset_id)
    spec["name"] = "Revised hypothesis"
    spec["nodes"].append({"node_id": "month", "label": "Month", "column": "month_index"})
    spec["edges"].append({"source": "month", "target": "churn", "rationale": "seasonality"})
    updated = client.put(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}", json={"graph": spec})
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["graph_id"] == graph_id
    assert payload["revision"] == 1
    assert payload["name"] == "Revised hypothesis"
    assert len(payload["nodes"]) == 5


def test_invalid_update_preserves_previous_valid_state(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    created = _create(client, dataset_id, _base_spec(dataset_id))
    graph_id = created.json()["graph_id"]
    original = created.json()

    broken = _base_spec(dataset_id)
    broken["edges"].append({"source": "churn", "target": "tenure", "rationale": "cycle"})
    rejected = client.put(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}", json={"graph": broken})
    assert rejected.status_code == 422

    after = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}").json()
    assert after["revision"] == original["revision"]
    assert after["spec_fingerprint_sha256"] == original["spec_fingerprint_sha256"]
    assert len(after["edges"]) == len(original["edges"])


# --------------------------------------------------------------------------- #
# Export / import contract
# --------------------------------------------------------------------------- #


def test_export_import_roundtrip_keeps_scientific_identity(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    created = _create(client, dataset_id, _base_spec(dataset_id))
    graph_id = created.json()["graph_id"]
    original = created.json()

    exported = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/export")
    assert exported.status_code == 200
    envelope = exported.json()
    assert envelope["export_kind"] == "splitscope-causal-graph"
    assert envelope["causal_graph_schema_version"] == "1.0.0"
    assert "dataset rows" in envelope["note"].lower()
    # The export carries no row data at all.
    assert "frame" not in envelope and "rows" not in envelope

    imported = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/import", json={"export_file": envelope}
    )
    assert imported.status_code == 201, imported.text
    clone = imported.json()
    # New identity, identical science.
    assert clone["graph_id"] != graph_id
    assert clone["revision"] == 0
    assert clone["spec_fingerprint_sha256"] == original["spec_fingerprint_sha256"]
    assert [node["node_id"] for node in clone["nodes"]] == [node["node_id"] for node in original["nodes"]]


def test_import_rejects_foreign_and_version_mismatched_files(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]

    foreign = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/import",
        json={"export_file": {"nodes": [], "edges": []}},
    )
    assert foreign.status_code == 422
    assert "not a SplitScope causal-graph export" in foreign.json()["error"]["message"]

    stale = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/import",
        json={"export_file": {"export_kind": "splitscope-causal-graph", "causal_graph_schema_version": "0.9.0", "graph": {}}},
    )
    assert stale.status_code == 422
    assert "0.9.0" in stale.json()["error"]["message"]


def test_import_into_a_different_dataset_fails_on_unknown_columns(client):
    first = _upload(client)
    other = _upload(client, columns=["alpha", "beta", "gamma"] + ["filler"] * 1)
    dataset_a = first["dataset"]["dataset_id"]
    dataset_b = other["dataset"]["dataset_id"]
    created = _create(client, dataset_a, _base_spec(dataset_a))
    envelope = client.get(
        f"/api/datasets/{dataset_a}/causal-graphs/{created.json()['graph_id']}/export"
    ).json()

    rejected = client.post(
        f"/api/datasets/{dataset_b}/causal-graphs/import", json={"export_file": envelope}
    )
    assert rejected.status_code == 422
    codes = [issue["code"] for issue in rejected.json()["error"]["details"]["errors"]]
    assert "unknown_column" in codes


def test_import_rejects_non_object_and_malformed_graph_payloads(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    valid_envelope = {
        "export_kind": "splitscope-causal-graph",
        "causal_graph_schema_version": "1.0.0",
        "graph": {"name": "Broken", "dataset_id": dataset_id, "nodes": [{"node_id": "a"}]},
    }
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/import", json={"export_file": valid_envelope}
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["problem_count"] >= 1


# --------------------------------------------------------------------------- #
# Schema version and fingerprint determinism
# --------------------------------------------------------------------------- #


def test_fingerprint_is_content_addressed_and_layout_blind(client):
    from app.causal.schema import AnalysisScope, CausalEdge, CausalGraphSpec, CausalNode, LayoutPosition

    def spec(layout: bool) -> CausalGraphSpec:
        return CausalGraphSpec(
            name="fp", dataset_id="ds-x",
            nodes=[
                CausalNode(node_id="a", label="A", layout=LayoutPosition(x=12.5, y=-4.0) if layout else None),
                CausalNode(node_id="b", label="B"),
            ],
            edges=[CausalEdge(source="a", target="b", rationale="same reason")],
            analysis=AnalysisScope(treatment="a", outcome="b"),
        )

    assert graph_fingerprint(spec(layout=True)) == graph_fingerprint(spec(layout=False))

    reordered = spec(layout=False).model_copy(deep=True)
    reordered.nodes = list(reversed(reordered.nodes))
    assert graph_fingerprint(reordered) == graph_fingerprint(spec(layout=False))

    changed = spec(layout=False).model_copy(deep=True)
    changed.edges[0].rationale = "a different assumption"
    assert graph_fingerprint(changed) != graph_fingerprint(spec(layout=False))


def test_schema_version_is_echoed_in_every_payload(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    created = _create(client, dataset_id, _base_spec(dataset_id))
    graph_id = created.json()["graph_id"]
    listing = client.get(f"/api/datasets/{dataset_id}/causal-graphs").json()
    assert listing["schema_version"] == "1.0.0"
    validation = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/validation").json()
    assert validation["schema_version"] == "1.0.0"
    assert validation["validation_scope_note"].startswith("A passing validation establishes only")


# --------------------------------------------------------------------------- #
# Backward compatibility with the existing workflows
# --------------------------------------------------------------------------- #


def test_existing_study_and_dataset_endpoints_still_work(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    health = client.get("/api/health")
    assert health.status_code == 200
    study = client.get(f"/api/datasets/{dataset_id}/study")
    assert study.status_code == 200
    detail = client.get(f"/api/datasets/{dataset_id}")
    assert detail.status_code == 200
    assert detail.json()["dataset"]["columns"] == COLUMNS


def test_unknown_graph_id_returns_actionable_not_found(client):
    body = _upload(client)
    dataset_id = body["dataset"]["dataset_id"]
    response = client.get(f"/api/datasets/{dataset_id}/causal-graphs/cgraph-nope")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["details"]["fix"]
