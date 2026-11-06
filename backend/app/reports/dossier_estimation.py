"""S10-B — estimation-run summarisers for the research dossier.

Six dossier sections (causal graph, identification, causal effect
estimation, subgroup heterogeneity, robustness, what-if scenarios) are
composed from **stored estimation runs** — the same bounded, stale-refusing
payloads the Causal Research stage renders. Nothing here re-fits, re-derives
or invents: every number is copied from the recorded payload, every caveat is
carried through verbatim, and a run whose analysis kind does not match the
section is refused rather than silently substituted.

The honest-state rule matches the rest of the dossier: a section whose source
run is missing is returned with ``available: false`` and a reason, so an
exported report cannot turn "not run" into "passed".
"""

from __future__ import annotations

from typing import Any

DOSSIER_ESTIMATION_VERSION = "1.0.0"

CAUSAL_STRUCTURE_CAVEAT = (
    "The graph below is the user's assumed structure, recorded as drawn. An edge is an "
    "assumption about how the world works, not empirical proof; every identification and "
    "estimation result in this dossier depends on it."
)


def _estimation_run_kind(payload: dict[str, Any]) -> str:
    explicit = payload.get("analysis_kind")
    if isinstance(explicit, str):
        return explicit
    if "comparison" in payload:
        return "estimation_comparison"
    return "estimation"


def require_estimation_run(payload: dict[str, Any], *, expected: set[str], section: str) -> None:
    """Refuse a run whose analysis kind does not match the section.

    Raising (rather than degrading) keeps dossier composition explicit: a
    mismatched run is a caller error — e.g. naming a what-if run for the
    subgroup section — and must never be silently re-labelled.
    """
    kind = _estimation_run_kind(payload)
    if kind not in expected:
        raise ValueError(
            f"The run named for the {section} section is a '{kind}' analysis; "
            f"this section accepts {sorted(expected)}."
        )


def _estimation_run_header(payload: dict[str, Any]) -> dict[str, Any]:
    repro = payload.get("reproducibility", {})
    return {
        "run_id": payload.get("run_id"),
        "created_at_utc": payload.get("created_at_utc"),
        "estimand": payload.get("estimand"),
        "graph_id": repro.get("graph_id"),
        "graph_spec_fingerprint_sha256": repro.get("graph_spec_fingerprint_sha256"),
        "dataset_fingerprint_sha256": repro.get("dataset_fingerprint_sha256"),
        "software_versions": repro.get("software_versions"),
    }


def _cohort_header(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload.get("analysis", {})
    return {
        "rows_in_dataset": analysis.get("rows_in_dataset"),
        "rows_final": analysis.get("rows_final"),
        "treated_rows": analysis.get("treated_rows"),
        "control_rows": analysis.get("control_rows"),
        "exclusions": analysis.get("exclusions"),
        "missing_data_policy": analysis.get("missing_data_policy"),
        "outcome_task": analysis.get("outcome_task"),
        "outcome_coding": analysis.get("outcome_coding"),
        "treatment_column": analysis.get("treatment_column"),
        "outcome_column": analysis.get("outcome_column"),
        "adjustment_columns": analysis.get("adjustment_columns"),
    }


def _interval_summary(result: dict[str, Any]) -> dict[str, Any] | None:
    uncertainty = result.get("uncertainty") or {}
    if not isinstance(uncertainty, dict) or uncertainty.get("ci_lower") is None:
        return None
    return {
        "ci_lower": uncertainty.get("ci_lower"),
        "ci_upper": uncertainty.get("ci_upper"),
        "interval_level": uncertainty.get("level"),
        "method": uncertainty.get("method"),
        "standard_error": uncertainty.get("standard_error"),
    }


def _balance_digest(balance: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(balance, dict):
        return None
    covariates = balance.get("covariates") or []
    weighted = [
        item for item in covariates
        if isinstance(item, dict) and isinstance(item.get("smd_weighted"), (int, float))
    ]
    unweighted = [
        item for item in covariates
        if isinstance(item, dict) and isinstance(item.get("smd_unweighted"), (int, float))
    ]

    def _extreme(items: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
        if not items:
            return None
        worst = max(items, key=lambda item: abs(float(item[key])))
        return {"column": worst.get("column"), "level": worst.get("level"), "smd": worst.get(key)}

    return {
        "covariate_terms": len(covariates),
        "worst_unweighted": _extreme(unweighted, "smd_unweighted"),
        "worst_weighted": _extreme(weighted, "smd_weighted") or None,
        "diagnostic_imputation": balance.get("diagnostic_imputation"),
        "n": balance.get("n"),
    }


def _overlap_digest(overlap: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(overlap, dict):
        return None
    return {
        "n": overlap.get("n"),
        "propensity_summary": overlap.get("propensity_summary"),
        "extreme_rows": overlap.get("extreme_rows"),
        "truncation": overlap.get("truncation"),
        "note": overlap.get("note"),
    }


def causal_estimation_section(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Section G — the stored effect-estimation runs (one cohort each)."""
    runs = []
    for payload in payloads:
        require_estimation_run(payload, expected={"estimation", "estimation_comparison"}, section="causal effect estimation")
        estimators = []
        for result in payload.get("results", []):
            if result.get("status") != "estimated":
                estimators.append(
                    {
                        "estimator": result.get("estimator"),
                        "status": "failed",
                        "failure": result.get("failure"),
                    }
                )
                continue
            diagnostics = result.get("diagnostics") or {}
            estimators.append(
                {
                    "estimator": result.get("estimator"),
                    "status": "estimated",
                    "estimate": result.get("estimate"),
                    "units": result.get("units"),
                    "treated_mean": result.get("treated_mean"),
                    "control_mean": result.get("control_mean"),
                    "interval": _interval_summary(result),
                    "balance": _balance_digest(diagnostics.get("balance")),
                    "overlap": _overlap_digest(diagnostics.get("overlap")),
                    "warnings": result.get("warnings", []),
                    "model_specification": result.get("model_specification"),
                }
            )
        runs.append(
            {
                **_estimation_run_header(payload),
                "gate": payload.get("gate"),
                "cohort": _cohort_header(payload),
                "estimators": estimators,
                "comparison": payload.get("comparison"),
                "defaults_applied": payload.get("defaults_applied"),
                "scope_note": payload.get("scope_note"),
            }
        )
    return {
        "runs": runs,
        "total": len(runs),
        "interpretation_note": (
            "Estimates are average treatment effects on one explicitly prepared cohort under the "
            "assumed graph and verified adjustment set. They are conditional on exchangeability, "
            "positivity, consistency and correct specification — assumptions the gate cannot prove."
        ),
    }


def subgroups_section(payload: dict[str, Any]) -> dict[str, Any]:
    """Section H — subgroup heterogeneity from one stored subgroup run."""
    require_estimation_run(payload, expected={"subgroups"}, section="subgroup heterogeneity")
    return {
        **_estimation_run_header(payload),
        "subgroup": payload.get("subgroup"),
        "overall": payload.get("overall"),
        "groups": payload.get("groups"),
        "contrasts": payload.get("contrasts"),
        "notes": payload.get("notes"),
        "cohort": _cohort_header(payload),
        "scope_note": payload.get("scope_note"),
    }


def robustness_section(payload: dict[str, Any]) -> dict[str, Any]:
    """Section I — one stored robustness/sensitivity experiment."""
    require_estimation_run(payload, expected={"robustness"}, section="robustness and sensitivity")
    result = payload.get("result", {})
    # Bounded disclosure: the full repetition series stays in the stored run;
    # the dossier carries the distribution summary, parameters and failures.
    estimates = result.get("estimates")
    return {
        **_estimation_run_header(payload),
        "original": payload.get("original"),
        "experiment": result.get("experiment"),
        "parameters": result.get("parameters"),
        "distribution": result.get("distribution"),
        "repetition_count": len(estimates) if isinstance(estimates, list) else None,
        "full_series_included": False,
        "failures": result.get("failures"),
        "warnings": result.get("warnings"),
        "method_note": result.get("method_note"),
        "cohort": _cohort_header(payload),
        "scope_note": payload.get("scope_note"),
    }


def what_if_section(payload: dict[str, Any]) -> dict[str, Any]:
    """Section J — one stored model-based what-if scenario."""
    require_estimation_run(payload, expected={"what_if"}, section="what-if scenario")
    return {
        **_estimation_run_header(payload),
        "model_specification": payload.get("model_specification"),
        "profile_scenario": payload.get("profile_scenario"),
        "cohort_scenario": payload.get("cohort_scenario"),
        "warnings": payload.get("warnings"),
        "cohort": _cohort_header(payload),
        "scope_note": payload.get("scope_note"),
    }


def causal_graph_section(spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Section E — the assumed causal structure behind the estimation runs.

    ``spec`` is the stored graph's writable spec (nodes, edges, analysis,
    assumptions); ``record`` carries the registry identity and fingerprints.
    """
    edges = [
        {
            "source": edge.get("source"),
            "target": edge.get("target"),
            "rationale": edge.get("rationale"),
            "reference": edge.get("reference"),
        }
        for edge in spec.get("edges", [])
    ]
    nodes = [
        {
            "node_id": node.get("node_id"),
            "label": node.get("label"),
            "column": node.get("column"),
            "observed": node.get("observed"),
            "kind": node.get("kind"),
            "description": node.get("description"),
        }
        for node in spec.get("nodes", [])
    ]
    return {
        "graph_id": record.get("graph_id"),
        "graph_revision": record.get("revision"),
        "graph_spec_fingerprint_sha256": record.get("spec_fingerprint_sha256"),
        "name": spec.get("name"),
        "description": spec.get("description"),
        "analysis": spec.get("analysis"),
        "nodes": nodes,
        "edges": edges,
        "assumptions": spec.get("assumptions", []),
        "caveat": CAUSAL_STRUCTURE_CAVEAT,
    }


def identification_section(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Section F — the verification verdicts recorded by the estimation gate.

    The gate re-verified the backdoor criterion server-side at run time; the
    dossier reports those recorded verdicts. It does not re-run search.
    """
    verdicts = []
    for payload in payloads:
        require_estimation_run(payload, expected={"estimation", "estimation_comparison", "subgroups", "robustness", "what_if"}, section="graphical identification")
        gate = payload.get("gate") or {}
        repro = payload.get("reproducibility", {})
        verification = gate.get("adjustment_set_verification")
        verdicts.append(
            {
                "run_id": payload.get("run_id"),
                "analysis_kind": _estimation_run_kind(payload),
                "treatment_node": gate.get("treatment_node") or repro.get("treatment_node"),
                "outcome_node": gate.get("outcome_node") or repro.get("outcome_node"),
                "adjustment_nodes": gate.get("adjustment_nodes") or repro.get("adjustment_nodes"),
                "adjustment_set_verification": verification,
                "caveat": gate.get("caveat"),
            }
        )
    return {
        "verdicts": verdicts,
        "total": len(verdicts),
        "interpretation_note": (
            "Each verdict certifies that the named adjustment set satisfies the classical "
            "backdoor criterion on the assumed graph at run time. Identification under the "
            "backdoor criterion is a property of the assumed structure; it is not proof that "
            "the structure is true."
        ),
    }


__all__ = [
    "DOSSIER_ESTIMATION_VERSION",
    "causal_estimation_section",
    "causal_graph_section",
    "identification_section",
    "require_estimation_run",
    "robustness_section",
    "subgroups_section",
    "what_if_section",
]
