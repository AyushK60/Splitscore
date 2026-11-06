"""S10-C — publication figure of the causal graph (SVG).

The figure must be valid XML, drawn from the stored spec, deterministic, and
honest: unobserved nodes dashed, roles labelled, the assumption caveat in the
caption, user-authored text escaped. Layout coordinates position nodes but
never appear in the scientific fingerprint — the figure is display output.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.causal.figure import FIGURE_CAVEAT, build_graph_figure_svg
from xml.etree import ElementTree as StdParseXml


_NODE_KEYS = ("node_id", "label", "column", "observed", "kind", "description", "layout")
_EDGE_KEYS = ("source", "target", "rationale", "reference")


def _bare_spec(graph: dict, dataset_id: str) -> dict:
    """Strip server-computed fields back to the writable spec shape."""
    return {
        "schema_version": graph["schema_version"],
        "dataset_id": dataset_id,
        "name": graph["name"],
        "description": graph["description"],
        "nodes": [{key: node.get(key) for key in _NODE_KEYS} for node in graph["nodes"]],
        "edges": [{key: edge.get(key) for key in _EDGE_KEYS} for edge in graph["edges"]],
        "analysis": graph["analysis"],
        "assumptions": graph["assumptions"],
    }


@pytest.fixture()
def client():
    from app.api.deps import reset_context
    from app.main import create_app

    reset_context()
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def demo_with_graph(client):
    loaded = client.post("/api/demos/causal_effect/load")
    assert loaded.status_code == 200
    dataset_id = loaded.json()["dataset"]["dataset_id"]
    spec = {
        "schema_version": "1.0.0",
        "dataset_id": dataset_id,
        "name": "Figure <test> graph",
        "description": None,
        "nodes": [
            {"node_id": node, "label": label, "column": column, "observed": True,
             "kind": "covariate", "description": None, "layout": layout}
            for node, label, column, layout in [
                ("age", "Age", "age", {"x": 60, "y": 40}),
                ("baseline_score", "Baseline", "baseline_score", {"x": 60, "y": 140}),
                ("region", "Region", "region", {"x": 60, "y": 240}),
                ("treatment", "Treatment", "treatment", {"x": 320, "y": 140}),
                ("outcome", "Outcome", "outcome", {"x": 580, "y": 140}),
            ]
        ],
        "edges": [
            {"source": "age", "target": "treatment", "rationale": None, "reference": None},
            {"source": "baseline_score", "target": "treatment", "rationale": None, "reference": None},
            {"source": "region", "target": "treatment", "rationale": None, "reference": None},
            {"source": "age", "target": "outcome", "rationale": None, "reference": None},
            {"source": "baseline_score", "target": "outcome", "rationale": None, "reference": None},
            {"source": "region", "target": "outcome", "rationale": None, "reference": None},
            {"source": "treatment", "target": "outcome", "rationale": None, "reference": None},
        ],
        "analysis": {"treatment": "treatment", "outcome": "outcome"},
        "assumptions": [],
    }
    created = client.post(f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": spec})
    assert created.status_code == 201, created.text
    graph = created.json().get("graph") or created.json()
    return dataset_id, graph["graph_id"]


def test_figure_is_valid_xml_with_all_nodes_and_edges(demo_with_graph, client):
    dataset_id, graph_id = demo_with_graph
    response = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/figure.svg")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/svg+xml")
    svg = response.text
    root = StdParseXml.fromstring(svg)
    assert root.tag.endswith("svg")
    rects = [el for el in root.iter() if el.tag.endswith("rect")]
    texts = [el for el in root.iter() if el.tag.endswith("text")]
    paths = [el for el in root.iter() if el.tag.endswith("path")]
    assert len(rects) == 6  # five node rects + the background rect
    assert len(paths) == 8  # seven edge arrows + the arrowhead marker path
    text_content = ["".join(el.itertext()) for el in texts]
    # Roles and the caveat are present.
    assert any("treatment" in text for text in text_content)
    assert any("outcome" in text for text in text_content)
    assert any(FIGURE_CAVEAT in text for text in text_content)
    # User-authored label text is escaped, never raw markup.
    assert any("Figure <test> graph" in text for text in text_content)


def test_figure_is_deterministic_and_ignores_layout_for_fingerprint(demo_with_graph, client):
    dataset_id, graph_id = demo_with_graph
    first = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/figure.svg").text
    second = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/figure.svg").text
    assert first == second
    # Moving a node (layout-only edit) must not change the scientific
    # fingerprint — the figure carries the fingerprint, so it must be stable.
    graphs = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}").json()
    graph = graphs.get("graph") or graphs
    spec = _bare_spec(graph, dataset_id)
    spec["nodes"][0]["layout"] = {"x": 90, "y": 90}
    saved = client.put(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}", json={"graph": spec})
    assert saved.status_code == 200, saved.text
    updated = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}").json()
    updated_graph = updated.get("graph") or updated
    assert updated_graph["spec_fingerprint_sha256"] == graph["spec_fingerprint_sha256"]


def test_figure_refuses_a_missing_graph(demo_with_graph, client):
    dataset_id, _ = demo_with_graph
    response = client.get(f"/api/datasets/{dataset_id}/causal-graphs/cgraph-nope/figure.svg")
    assert response.status_code == 404


def test_unobserved_nodes_are_dashed_in_the_figure(demo_with_graph, client):
    dataset_id, graph_id = demo_with_graph
    graphs = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}").json()
    graph = graphs.get("graph") or graphs
    graph["nodes"][0]["observed"] = False
    saved = client.put(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}", json={"graph": _bare_spec(graph, dataset_id)}
    )
    assert saved.status_code == 200, saved.text
    svg = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/figure.svg").text
    assert 'stroke-dasharray="4 3"' in svg


def test_layered_layout_when_no_positions_recorded(demo_with_graph, client):
    dataset_id, graph_id = demo_with_graph
    graphs = client.get(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}").json()
    graph = graphs.get("graph") or graphs
    for node in graph["nodes"]:
        node["layout"] = None
    spec = _bare_spec(graph, dataset_id)
    saved = client.put(f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}", json={"graph": spec})
    assert saved.status_code == 200, saved.text
    svg = build_graph_figure_svg(
        spec,
        {"graph_id": "g", "revision": 1, "spec_fingerprint_sha256": "a" * 64},
    )
    assert svg
    assert "treatment" in svg
