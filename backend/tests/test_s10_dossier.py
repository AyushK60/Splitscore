"""S10-B integrated research dossier: causal sections, methodology, honesty.

Every assertion ties the dossier back to the stored runs it was composed
from: the estimate in the dossier equals the estimate in the stored run, the
subgroup rows equal the subgroup run's groups, the robustness caveats survive
verbatim, the what-if limitation text survives verbatim, and the methodology
generator can only say "Not evaluated" when a run was never selected. Cross-
dataset mixing and stale-dataset mixing are refused at the route.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.reports.dossier import SECTION_IDS, build_dossier


@pytest.fixture()
def client():
    from app.api.deps import reset_context
    from app.main import create_app

    reset_context()
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def loaded_demo(client):
    response = client.post("/api/demos/causal_effect/load")
    assert response.status_code == 200, response.text
    return response.json()


_GRAPH_SPEC = {
    "schema_version": "1.0.0",
    "name": "S10 dossier demonstration",
    "description": "Demonstration DAG for dossier integration.",
    "nodes": [
        {
            "node_id": node,
            "label": node,
            "column": node,
            "observed": True,
            "kind": "covariate",
            "description": None,
            "layout": None,
        }
        for node in ["age", "baseline_score", "region", "treatment", "outcome"]
    ],
    "edges": [
        {"source": source, "target": "treatment", "rationale": "confounder <assumption>", "reference": None}
        for source in ["age", "baseline_score", "region"]
    ]
    + [
        {"source": source, "target": "outcome", "rationale": None, "reference": None}
        for source in ["age", "baseline_score", "region", "treatment"]
    ],
    "analysis": {"treatment": "treatment", "outcome": "outcome"},
    "assumptions": [
        {
            "assumption_id": "a-unmeasured-1",
            "category": "unmeasured_confounding",
            "status": "not_assessed",
            "source": "test fixture",
            "rationale": "No unmeasured confounding is assumed.",
        }
    ],
}


def _estimation_request():
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


def _run_estimation(client, loaded_demo) -> tuple[str, str]:
    dataset_id = loaded_demo["dataset"]["dataset_id"]
    created = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": {**_GRAPH_SPEC, "dataset_id": dataset_id}}
    )
    assert created.status_code == 201, created.text
    graph = created.json().get("graph") or created.json()
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph['graph_id']}/estimation/run",
        json={"request": _estimation_request(), "estimator": "aipw", "label": "dossier estimation"},
    )
    assert response.status_code == 200, response.text
    return dataset_id, response.json()["run_id"]


def _run_subgroups(client, loaded_demo, graph_id) -> str:
    dataset_id = loaded_demo["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/subgroups",
        json={
            "request": _estimation_request(),
            "subgroup": {"node_id": "region", "numeric_binning": "quartile", "intent": "exploratory"},
            "label": "dossier subgroups",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def _run_robustness(client, loaded_demo, graph_id, experiment="subsampling", spec=None) -> str:
    dataset_id = loaded_demo["dataset"]["dataset_id"]
    body = {
        "request": _estimation_request(),
        "experiment": experiment,
        "parameters": spec or {"estimator": "aipw", "reps": 100, "fraction": 0.5},
        "label": f"dossier {experiment}",
    }
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/robustness", json=body
    )
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def _run_what_if(client, loaded_demo, graph_id) -> str:
    dataset_id = loaded_demo["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs/{graph_id}/estimation/whatif",
        json={"request": _estimation_request(), "profile": {"age": 45}, "label": "dossier what-if"},
    )
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def _dossier_request(section_ids, estimation_run_ids=None, presentation="concise"):
    return {
        "sections": section_ids,
        "audit_run_id": None,
        "comparison_run_id": None,
        "model_run_ids": [],
        "estimation_run_ids": estimation_run_ids or [],
        "presentation": presentation,
    }


def test_schema_is_additive_and_v1_sections_keep_their_ids():
    # The v1.0.0 section ids are all still present, in their original order.
    assert SECTION_IDS[:10] == (
        "summary", "provenance", "study", "audit", "scorecard",
        "findings", "comparison", "models", "limitations", "reproducibility",
    )
    assert SECTION_IDS[10:] == (
        "causal_graph", "identification", "causal_estimation",
        "subgroups", "robustness", "what_if", "methodology",
    )


def test_causal_sections_are_unavailable_without_estimation_runs(client, loaded_demo):
    dataset_id = loaded_demo["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/reports/dossier",
        json=_dossier_request(["causal_estimation", "subgroups", "robustness", "what_if", "identification", "causal_graph", "methodology"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "1.1.0"
    for section_id in ("causal_estimation", "subgroups", "robustness", "what_if", "identification", "causal_graph"):
        section = body["sections"][section_id]
        assert section["available"] is False
        assert "No estimation run" in section["reason"] or "No subgroup" in section["reason"] or "No robustness" in section["reason"] or "No what-if" in section["reason"] or "No causal graph" in section["reason"]
    # The methodology generator states the gap instead of inventing content.
    paragraphs = body["sections"]["methodology"]["data"]["paragraphs"]
    causal = next(p for p in paragraphs if p["title"] == "Causal identification and estimation")
    assert "Not evaluated" in causal["text"]


def test_estimation_values_in_dossier_equal_the_stored_run(client, loaded_demo):
    dataset_id, run_id = _run_estimation(client, loaded_demo)
    stored = client.get(f"/api/datasets/{dataset_id}/estimation-runs/{run_id}").json()
    stored_estimate = next(r for r in stored["results"] if r["estimator"] == "aipw")["estimate"]

    response = client.post(
        f"/api/datasets/{dataset_id}/reports/dossier",
        json=_dossier_request(["causal_estimation", "identification", "causal_graph", "methodology"], [run_id]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    section = body["sections"]["causal_estimation"]
    assert section["available"] is True
    run = section["data"]["runs"][0]
    assert run["run_id"] == run_id
    dossier_estimate = next(e for e in run["estimators"] if e["estimator"] == "aipw")["estimate"]
    assert dossier_estimate == stored_estimate

    # The identification section reports the recorded backdoor verdict.
    verdict = body["sections"]["identification"]["data"]["verdicts"][0]
    verification = verdict["adjustment_set_verification"]
    assert verification["valid"] is True
    assert verdict["adjustment_nodes"] == ["age", "baseline_score", "region"]

    # The causal graph section carries the stored spec, including the
    # user-authored edge rationale verbatim (it is an assumption, not proof).
    graph_section = body["sections"]["causal_graph"]["data"]
    rationales = [edge["rationale"] for edge in graph_section["edges"]]
    assert "confounder <assumption>" in rationales
    assumptions = graph_section["assumptions"]
    assert assumptions and assumptions[0]["rationale"] == "No unmeasured confounding is assumed."


def test_subgroup_and_robustness_and_what_if_sections_track_their_runs(client, loaded_demo):
    dataset_id = loaded_demo["dataset"]["dataset_id"]
    created = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": {**_GRAPH_SPEC, "dataset_id": dataset_id}}
    )
    graph = created.json().get("graph") or created.json()
    graph_id = graph["graph_id"]
    subgroup_run = _run_subgroups(client, loaded_demo, graph_id)
    robustness_run = _run_robustness(client, loaded_demo, graph_id, "unmeasured_confounder", {"estimator": "regression_adjustment", "reps": 100, "prevalence": 0.3})
    whatif_run = _run_what_if(client, loaded_demo, graph_id)

    stored_subgroups = client.get(f"/api/datasets/{dataset_id}/estimation-runs/{subgroup_run}").json()
    response = client.post(
        f"/api/datasets/{dataset_id}/reports/dossier",
        json=_dossier_request(["subgroups", "robustness", "what_if"], [subgroup_run, robustness_run, whatif_run]),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    dossier_groups = body["sections"]["subgroups"]["data"]["groups"]
    stored_groups = stored_subgroups["groups"]
    assert [g["label"] for g in dossier_groups] == [g["label"] for g in stored_groups]
    assert [g["estimate"] for g in dossier_groups] == [g["estimate"] for g in stored_groups]
    # The multiple-comparisons caveat survives verbatim.
    notes = body["sections"]["subgroups"]["data"]["notes"]
    assert any(note["code"] == "multiple_comparisons" for note in notes)

    # Sensitivity is presented as a scenario, never a bound.
    robust_section = body["sections"]["robustness"]["data"]
    assert any("not a bound" in warning for warning in robust_section["warnings"])
    assert robust_section["parameters"]["estimator"] == "regression_adjustment"

    # The what-if limitation text survives verbatim.
    whatif_section = body["sections"]["what_if"]["data"]
    assert any(
        "not an observed outcome" in warning and "not an individual counterfactual" in warning
        for warning in whatif_section["warnings"]
    )
    assert whatif_section["profile_scenario"]["disclosures"][0]["source"] == "explicit"


def test_methodology_technical_level_reports_cross_fitting_details(client, loaded_demo):
    dataset_id, run_id = _run_estimation(client, loaded_demo)
    response = client.post(
        f"/api/datasets/{dataset_id}/reports/dossier",
        json=_dossier_request(["methodology"], [run_id], presentation="technical"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sections"]["methodology"]["data"]["presentation"] == "technical"
    paragraphs = body["sections"]["methodology"]["data"]["paragraphs"]
    config = next(p for p in paragraphs if p["title"] == "Estimation configuration")
    assert "backdoor" in config["text"]


def test_dossier_refuses_a_stale_estimation_run(client, loaded_demo):
    dataset_id, run_id = _run_estimation(client, loaded_demo)
    from app.api.deps import get_context

    dataset = get_context().store.get_dataset(dataset_id)
    dataset.fingerprint_sha256 = "e" * 64
    response = client.post(
        f"/api/datasets/{dataset_id}/reports/dossier",
        json=_dossier_request(["causal_estimation"], [run_id]),
    )
    assert response.status_code == 422, response.text
    assert "no longer matches" in response.text or "content has since changed" in response.text


def test_dossier_refuses_a_cross_dataset_estimation_run(client, loaded_demo):
    dataset_id, run_id = _run_estimation(client, loaded_demo)
    other = client.post("/api/demos/causal_effect/load").json()["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{other}/reports/dossier",
        json=_dossier_request(["causal_estimation"], [run_id]),
    )
    assert response.status_code == 404, response.text
    assert "different dataset" in response.text


def test_mismatched_estimation_kind_is_refused_not_relabelled(client, loaded_demo):
    dataset_id = loaded_demo["dataset"]["dataset_id"]
    created = client.post(
        f"/api/datasets/{dataset_id}/causal-graphs", json={"graph": {**_GRAPH_SPEC, "dataset_id": dataset_id}}
    )
    graph = created.json().get("graph") or created.json()
    subgroup_run = _run_subgroups(client, loaded_demo, graph["graph_id"])
    stored = client.get(f"/api/datasets/{dataset_id}/estimation-runs/{subgroup_run}").json()
    from app.reports.dossier_estimation import require_estimation_run

    with pytest.raises(ValueError, match="subgroups"):
        require_estimation_run(stored, expected={"estimation", "estimation_comparison"}, section="causal effect estimation")


def test_dossier_json_and_html_exports_are_stable_and_escaped(client, loaded_demo):
    dataset_id, run_id = _run_estimation(client, loaded_demo)
    request = _dossier_request(
        ["causal_estimation", "causal_graph", "identification", "methodology", "robustness", "subgroups", "what_if"],
        [run_id],
    )
    json_response = client.post(f"/api/datasets/{dataset_id}/reports/dossier", json=request)
    assert json_response.status_code == 200, json_response.text
    payload = json.loads(json_response.content.decode("utf-8"))
    assert payload["report_kind"] == "dossier"

    html_response = client.post(f"/api/datasets/{dataset_id}/reports/dossier?format=html", json=request)
    assert html_response.status_code == 200, html_response.text
    html = html_response.text
    # Every included available section rendered (no missing-renderer drop).
    for section_id in ("causal_estimation", "causal_graph", "identification", "methodology"):
        assert f'id="{section_id}"' in html
    # The user-authored `<assumption>` marker must be escaped, not injected.
    assert "&lt;assumption&gt;" in html
    assert "confounder <assumption>" not in html
