"""dossier - academic methodology generator for the research dossier.

Structured, academically styled methodology prose composed **only** from
verified analysis metadata the process already holds: the Study Card, the
dataset identity, the stored audit/comparison runs, model runs and stored
estimation runs. Nothing is invented:

* a sample size is reported only when a run recorded it;
* a confidence interval or significance level is reported only when a stored
  result carries one;
* a missing input becomes an explicit "Not provided" / "Not evaluated"
  statement with the reason - never a blank that reads as omission by choice.

Two presentation levels are supported (``concise`` default, ``technical``);
they differ in how much configuration detail is spelled out. Neither level
draws causal conclusions or grades the research: the generator describes what
was done, and the limitations section carries what was not.
"""

from __future__ import annotations

from typing import Any

METHODOLOGY_VERSION = "1.0.0"

NOT_PROVIDED = "Not provided by the study card."
NOT_EVALUATED = "Not evaluated - no qualifying analysis run was included in this dossier."


def _sentence(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return "; ".join(items[:-1]) + "; and " + items[-1]


def _join_names(names: list[str] | None) -> str:
    if not names:
        return ""
    return _sentence([f"'{name}'" for name in [str(name) for name in names]]) if names else ""


def _cohort_sentence(analysis: dict[str, Any]) -> str:
    rows = analysis.get("rows_final")
    treated = analysis.get("treated_rows")
    control = analysis.get("control_rows")
    if rows is None:
        return ""
    return (
        f"The analysis cohort comprised {rows} rows ({treated} treated, {control} control) after "
        "the recorded exclusions, under the "
        f"'{analysis.get('missing_data_policy')}' missing-data policy."
    )


def _estimation_paragraphs(
    estimation_runs: list[dict[str, Any]],
    *,
    technical: bool,
) -> list[dict[str, str]]:
    """Paragraphs for identification and estimation from stored runs."""
    paragraphs: list[dict[str, str]] = []
    for payload in estimation_runs:
        repro = payload.get("reproducibility", {})
        analysis = payload.get("analysis", {})
        gate = payload.get("gate") or {}
        kind = payload.get("analysis_kind") or (
            "estimation_comparison" if "comparison" in payload else "estimation"
        )
        cohort = _cohort_sentence(analysis)

        if kind in ("estimation", "estimation_comparison"):
            names = [result.get("estimator") for result in payload.get("results", []) if result.get("estimator")]
            adjustment = gate.get("adjustment_nodes") or repro.get("adjustment_nodes")
            text = (
                f"Potential outcomes were estimated with the {', '.join(str(n) for n in names)} "
                f"estimator(s) for the treatment '{repro.get('treatment_node')}' and outcome "
                f"'{repro.get('outcome_node')}', adjusting for {_join_names(adjustment) or 'no covariates'}. "
                + cohort
            )
            paragraphs.append({"title": "Causal effect estimation", "text": text})
            if technical:
                paragraphs.append(
                    {
                        "title": "Estimation configuration",
                        "text": (
                            f"Cross-fitting used {repro.get('cross_fitting')}; uncertainty follows the "
                            f"recorded '{(repro.get('uncertainty') or {}).get('method')}' procedure at level "
                            f"{(repro.get('uncertainty') or {}).get('level')}. The identification gate "
                            "re-verified the classical backdoor criterion on the stored graph before any "
                            "estimation; exchangeability, positivity and consistency remain assumptions."
                        ),
                    }
                )
        elif kind == "subgroups":
            subgroup = payload.get("subgroup", {})
            text = (
                f"Subgroup effects were computed as averages of the cross-fitted AIPW pseudo-outcome "
                f"within levels of '{subgroup.get('column')}' ({subgroup.get('definition')}, marked as "
                f"{subgroup.get('intent')}). " + cohort
            )
            paragraphs.append({"title": "Subgroup and heterogeneity analysis", "text": text})
        elif kind == "robustness":
            experiment = (payload.get("reproducibility") or {}).get("experiment", {})
            text = (
                f"A '{experiment.get('kind')}' robustness experiment was run with "
                f"{json_safe(experiment)} parameters on the same cohort. "
                "The experiment re-runs the production estimator machinery under the recorded "
                "perturbation; it does not verify the causal assumptions."
            )
            paragraphs.append({"title": "Robustness and sensitivity analysis", "text": text})
        elif kind == "what_if":
            text = (
                "A model-based what-if scenario was evaluated with the g-computation outcome model: "
                "expected outcomes under treatment and control were predicted for a stated baseline "
                "profile, with unset profile fields held at disclosed cohort medians/modes. Scenario "
                "predictions are conditional model expectations, not observed outcomes, not "
                "individual counterfactuals, and carry no interval."
            )
            paragraphs.append({"title": "Model-based scenario analysis", "text": text})
    return paragraphs


def json_safe(value: Any) -> str:
    return str(value)


def build_methodology(
    *,
    dataset: Any,
    study: dict[str, Any] | None,
    audit: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    models: list[dict[str, Any]],
    estimation_runs: list[dict[str, Any]],
    presentation: str = "concise",
) -> dict[str, Any]:
    """The dossier 'methodology' section: structured academic prose, no invention."""
    if presentation not in ("concise", "technical"):
        raise ValueError("presentation must be 'concise' or 'technical'.")
    technical = presentation == "technical"
    card = (study or {}).get("card") or {}

    def card_field(field: str) -> str:
        value = card.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return NOT_PROVIDED

    column_count = len(getattr(dataset, "columns", None) or []) or getattr(dataset, "column_count", "?")
    data_source_text = (
        f"The analysis used '{dataset.name}' ({dataset.row_count} rows × {column_count} columns, "
        f"{'synthetic demonstration data' if dataset.is_synthetic else 'user-uploaded data'}). "
        f"Objective: {card_field('objective')}"
    )
    paragraphs: list[dict[str, str]] = [{"title": "Data source and sample", "text": data_source_text}]

    definitions = (study or {}).get("fields") or []
    if definitions:
        declared = [
            f"'{field.get('name')}' ({field.get('value')})"
            for field in definitions
            if isinstance(field, dict) and field.get("value")
        ]
        variables_text = (
            "Variable roles were declared explicitly: " + _sentence(declared) + "."
            if declared
            else "Variable roles were declared in the Study Card; see the study section."
        )
    else:
        variables_text = "Variable operational definitions: " + NOT_PROVIDED
    paragraphs.append({"title": "Variables and operational definitions", "text": variables_text})

    if audit is not None:
        evaluation = audit.get("evaluation") or {}
        split = audit.get("split") or {}
        audits_text = (
            f"A train/test leakage audit evaluated the '{split.get('label')}' split "
            f"({split.get('train_rows')} train / {split.get('test_rows')} test rows): "
            f"{evaluation.get('findings_total')} finding(s) at the recorded severity thresholds. "
            f"Checks not evaluated: {len(evaluation.get('not_evaluated', []))}."
        )
    else:
        audits_text = "Leakage audit: " + NOT_EVALUATED
    paragraphs.append({"title": "Split and leakage evaluation", "text": audits_text})

    if comparison is not None:
        rows = comparison.get("rows") or []
        comparison_text = (
            f"Split strategies were compared by re-running the same audit under each candidate "
            f"({len(rows)} candidate strategy row(s) reported); SplitScope does not nominate a best split."
        )
    else:
        comparison_text = "Split-strategy comparison: " + NOT_EVALUATED
    paragraphs.append({"title": "Split strategy comparison", "text": comparison_text})

    if models:
        pieces = []
        for model in models:
            payload = model.get("payload") or {}
            kind = payload.get("kind")
            specification = payload.get("specification") or {}
            if kind == "statistical_model":
                pieces.append(
                    f"an OLS/logistic fit of '{specification.get('formula')}' "
                    "(coefficients, fit statistics and diagnostics reported separately)"
                )
            elif kind == "prediction_model":
                pieces.append(
                    f"a predictive model for '{specification.get('outcome')}' evaluated on one "
                    "sealed test split (metrics reported separately)"
                )
        models_text = (
            "The model analysis included " + _sentence(pieces) + "."
            if pieces
            else "Model runs were named but their kinds are not summarised here."
        )
    else:
        models_text = "Statistical and predictive modelling: " + NOT_EVALUATED
    paragraphs.append({"title": "Statistical and predictive analysis", "text": models_text})

    if estimation_runs:
        graph_runs = [payload for payload in estimation_runs if payload.get("reproducibility", {}).get("graph_id")]
        if graph_runs:
            repro = graph_runs[0].get("reproducibility", {})
            paragraphs.append(
                {
                    "title": "Causal graph assumptions",
                    "text": (
                        f"All causal analyses assume the directed acyclic graph '{repro.get('graph_id')}' "
                        "(recorded as drawn; see the causal graph section). The edges are assumptions, "
                        "documented with their rationales, not empirical findings."
                    ),
                }
            )
            paragraphs.append(
                {
                    "title": "Identification strategy",
                    "text": (
                        "Identification follows the classical backdoor criterion on the assumed graph, "
                        "re-verified server-side by the estimation gate before each run. No front-door "
                        "or instrumental-variable strategy is applied."
                    ),
                }
            )
        paragraphs.extend(_estimation_paragraphs(estimation_runs, technical=technical))
    else:
        paragraphs.append({"title": "Causal identification and estimation", "text": NOT_EVALUATED})

    diagnostics_text = (
        "Estimation diagnostics (covariate balance, propensity overlap, weight extremes) are "
        "reported with each estimation result; predictive diagnostics are reported with each "
        "model. No diagnostic is summarised into a single score."
        if estimation_runs or models
        else "Diagnostic procedures: " + NOT_EVALUATED
    )
    paragraphs.append({"title": "Diagnostic procedures", "text": diagnostics_text})

    robustness_runs = [
        payload for payload in estimation_runs
        if (payload.get("analysis_kind") or ("estimation_comparison" if "comparison" in payload else "estimation")) == "robustness"
    ]
    if robustness_runs:
        experiment = (robustness_runs[0].get("reproducibility") or {}).get("experiment", {})
        paragraphs.append(
            {
                "title": "Sensitivity and robustness methods",
                "text": (
                    f"Robustness was examined with the '{experiment.get('kind')}' experiment. Where the "
                    "experiment is a hypothetical unmeasured-confounder simulation, it is a scenario "
                    "analysis conditioned on the observed data - not a formal sensitivity bound."
                ),
            }
        )
    else:
        paragraphs.append({"title": "Sensitivity and robustness methods", "text": NOT_EVALUATED})

    software = set()
    seeds: list[Any] = []
    for payload in estimation_runs:
        repro = payload.get("reproducibility", {})
        versions = repro.get("software_versions") or {}
        if versions:
            software.add(
                f"Python {versions.get('python')}, NumPy {versions.get('numpy')}, pandas {versions.get('pandas')}, "
                f"scikit-learn {versions.get('scikit_learn')}"
            )
        seed = (repro.get("uncertainty") or {}).get("resolved_seed")
        if seed is not None:
            seeds.append(seed)
    reproducibility_text = (
        "; ".join(sorted(software)) + "."
        if software
        else "Software versions: not recorded for the included runs."
    )
    if seeds:
        reproducibility_text += f" Recorded random seeds: {sorted(set(seeds))}."
    reproducibility_text += (
        " Dataset and graph content are identified by SHA-256 fingerprints recorded in the "
        "reproducibility block of each included run."
    )
    paragraphs.append({"title": "Reproducibility", "text": reproducibility_text})

    limitations_text = (
        "This methodology describes analyses of one sample under stated assumptions. It contains no "
        " IRB, ethical-approval or consent determination, and it is not a causal conclusion: every "
        "causal statement is conditional on the assumed graph and the identification assumptions. "
        "Sections marked 'Not evaluated' identify analyses that were not run or not selected, so the "
        "record cannot read as complete when it is not."
    )
    paragraphs.append({"title": "Study limitations", "text": limitations_text})

    return {
        "methodology_version": METHODOLOGY_VERSION,
        "presentation": presentation,
        "paragraphs": paragraphs,
        "sources": {
            "study_card": bool(study),
            "audit_run": audit is not None,
            "comparison_run": comparison is not None,
            "model_runs": [model.get("run_id") for model in models],
            "estimation_runs": [payload.get("run_id") for payload in estimation_runs],
        },
        "scope_note": (
            "Generated from structured run metadata only. Missing inputs are marked 'Not provided' "
            "or 'Not evaluated'; no sample size, interval, performance figure, objective or causal "
            "conclusion is invented by this generator."
        ),
    }


__all__ = ["METHODOLOGY_VERSION", "build_methodology"]
