"""research dossier composition (F19/F21/F22, report layer).

The dossier is assembled from results the process already holds: the loaded
dataset, its Study Card and profile, and explicitly named audit, comparison and
model runs. It never re-fits, re-audits or invents an analysis. A requested
section whose source run is missing is returned with ``available: false`` and a
reason, so an exported report cannot turn "not run" into "passed".

Only bounded evidence examples from findings are embedded. Test predictions,
full rows and raw uploaded bytes are deliberately not part of the report.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from app.core.version import APP_NAME, APP_VERSION
from app.reports.dossier_estimation import (
    causal_estimation_section,
    causal_graph_section,
    identification_section,
    robustness_section,
    subgroups_section,
    what_if_section,
)
from app.reports.methodology import build_methodology

# v1.1.0: adds the causal_graph, identification, causal_estimation,
# subgroups, robustness, what_if and methodology sections. Additive only -
# every v1.0.0 section keeps its id, shape and semantics.
DOSSIER_SCHEMA_VERSION = "1.1.0"

SECTION_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "summary",
        "title": "Executive summary",
        "description": "The dataset, audited split, key findings and cautions in one review layer.",
    },
    {
        "id": "provenance",
        "title": "Dataset and provenance",
        "description": "Identity, fingerprint, shape, profile and column dictionary.",
    },
    {
        "id": "study",
        "title": "Study card",
        "description": "User-declared study context, completion and role declarations.",
    },
    {
        "id": "audit",
        "title": "Leakage audit",
        "description": "The stored audit run, its split, checks and not-evaluated list.",
    },
    {
        "id": "scorecard",
        "title": "Risk scorecard",
        "description": "Category states derived only from the audit outcomes.",
    },
    {
        "id": "findings",
        "title": "Findings and evidence",
        "description": "Each finding with its counts, bounded examples and limitations.",
    },
    {
        "id": "comparison",
        "title": "Split comparison",
        "description": "Candidate split consequences from the stored comparison run.",
    },
    {
        "id": "models",
        "title": "Model lab",
        "description": "Selected statistical and predictive runs, metrics and diagnostics.",
    },
    {
        "id": "limitations",
        "title": "Limitations and not-evaluated items",
        "description": "Explicit scope boundaries, warnings and checks that did not run.",
    },
    {
        "id": "reproducibility",
        "title": "Reproducibility and export metadata",
        "description": "Run identifiers, dataset fingerprint, versions and embedding policy.",
    },
    {
        "id": "causal_graph",
        "title": "Causal graph specification",
        "description": "The assumed DAG behind the causal analyses: nodes, edges and assumptions.",
    },
    {
        "id": "identification",
        "title": "Graphical identification",
        "description": "The backdoor-criterion verdicts the estimation gate recorded at run time.",
    },
    {
        "id": "causal_estimation",
        "title": "Causal effect estimation",
        "description": "Stored effect-estimation runs: cohort, estimators, intervals and diagnostics.",
    },
    {
        "id": "subgroups",
        "title": "Subgroup and heterogeneity",
        "description": "Stored subgroup effects, contrasts and their multiple-comparisons caveats.",
    },
    {
        "id": "robustness",
        "title": "Robustness and sensitivity",
        "description": "One stored robustness experiment with its parameters and honest scope.",
    },
    {
        "id": "what_if",
        "title": "Model-based what-if scenarios",
        "description": "Stored conditional outcome-model scenarios; never individual counterfactuals.",
    },
    {
        "id": "methodology",
        "title": "Methodology",
        "description": "Generated academic methodology from the included runs; gaps are explicit.",
    },
)

SECTION_IDS: tuple[str, ...] = tuple(spec["id"] for spec in SECTION_SPECS)
DEFAULT_SECTIONS: tuple[str, ...] = SECTION_IDS

SEVERITY_RANK = {"high": 4, "medium": 3, "low": 2, "info": 1}


def normalise_sections(requested: Iterable[str] | None) -> list[str]:
    if requested is None:
        return list(DEFAULT_SECTIONS)
    wanted = set(requested)
    unknown = sorted(wanted - set(SECTION_IDS))
    if unknown:
        raise ValueError(f"Unknown report section(s): {', '.join(unknown)}")
    ordered = [section for section in SECTION_IDS if section in wanted]
    if not ordered:
        raise ValueError("Select at least one report section.")
    return ordered


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _section(
    spec: dict[str, str],
    *,
    included: bool,
    available: bool,
    data: Any = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": spec["id"],
        "title": spec["title"],
        "description": spec["description"],
        "included": included,
        "available": available,
        "reason": reason,
        "data": data if available else None,
    }


def _declared_fields(study: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not study:
        return []
    fields = []
    for field in study.get("fields", []):
        value = field.get("value")
        if not field.get("declared") or value in (None, "", []):
            continue
        fields.append(
            {
                "name": field.get("name"),
                "label": field.get("label"),
                "section": field.get("section"),
                "value": value,
            }
        )
    return fields


def _study_data(study: dict[str, Any] | None) -> dict[str, Any]:
    if not study:
        return {
            "study_id": None,
            "revision": None,
            "completion": None,
            "declared_fields": [],
            "roles": {},
            "issues": [],
            "provenance": None,
            "note": "No Study Card record was available for this dataset.",
        }
    return {
        "study_id": study.get("study_id"),
        "revision": study.get("revision"),
        "updated_at_utc": study.get("updated_at_utc"),
        "completion": study.get("completion"),
        "declared_fields": _declared_fields(study),
        "roles": study.get("roles", {}),
        "column_declarations": study.get("column_declarations", {}),
        "issues": study.get("issues", []),
        "provenance": study.get("provenance"),
        "storage_note": study.get("storage_note"),
        "note": (
            "Study fields are user declarations; missing fields remain missing. "
            "SplitScope never fills in a design, consent status or objective."
        ),
    }


def _provenance_data(
    dataset: Any, study: dict[str, Any] | None, profile: dict[str, Any] | None
) -> dict[str, Any]:
    profile_dataset = (profile or {}).get("dataset", {})
    columns = []
    for column in (profile or {}).get("columns", []):
        columns.append(
            {
                "column": column.get("column"),
                "detected_type": column.get("detected_type"),
                "declared_type": column.get("declared_type"),
                "roles": column.get("roles", []),
                "missing_count": column.get("missing_count"),
                "missing_ratio": column.get("missing_ratio"),
                "distinct_count": column.get("distinct_count"),
                "unit": column.get("unit"),
                "description": column.get("description"),
                "flags": column.get("flags", []),
            }
        )
    return {
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "source": dataset.source,
            "is_synthetic": dataset.is_synthetic,
            "demo_id": dataset.demo.demo_id if dataset.demo is not None else None,
            "sha256": dataset.fingerprint_sha256,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
            "created_at_utc": dataset.created_at.isoformat(),
            "warnings": dataset.warnings,
        },
        "profile": {
            "numeric_columns": profile_dataset.get("numeric_columns"),
            "datetime_columns": profile_dataset.get("datetime_columns"),
            "duplicate_rows": profile_dataset.get("duplicate_rows"),
            "duplicate_row_groups": profile_dataset.get("duplicate_row_groups"),
            "summary": (profile or {}).get("summary", {}),
            "warnings": (profile or {}).get("warnings", []),
            "conventions": (profile or {}).get("conventions", []),
        },
        "columns": columns,
        "role_assignments": (study or {}).get("roles", {}).get("assignments", {}),
        "role_note": (
            "Detected types and counts are computed from the loaded file. Role assignments and "
            "declared types are user declarations, not inferences."
        ),
    }


def _audit_data(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    evaluation = payload.get("evaluation", {})
    outcomes = []
    for outcome in payload.get("rule_outcomes", []):
        outcomes.append(
            {
                "rule_id": outcome.get("rule_id"),
                "title": outcome.get("title"),
                "status": outcome.get("status"),
                "duration_ms": outcome.get("duration_ms"),
                "finding_count": len(outcome.get("findings", [])),
            }
        )
    return {
        "run_id": payload.get("run_id"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "duration_ms": payload.get("duration_ms"),
        "split": payload.get("split"),
        "roles": payload.get("roles"),
        "resolved_roles": payload.get("resolved_roles"),
        "evaluation": evaluation,
        "settings": {
            "audit_config": payload.get("audit_config"),
            "audit_limits": payload.get("audit_limits"),
        },
        "rule_outcomes": outcomes,
        "not_evaluated": evaluation.get("not_evaluated", []),
        "limitations": payload.get("limitations", []),
        "assumptions": payload.get("assumptions", []),
        "diagnostics_note": (payload.get("diagnostics") or {}).get("disclaimer"),
    }


def _findings_data(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    findings = []
    for finding in payload.get("findings", []):
        findings.append(
            {
                "rule_id": finding.get("rule_id"),
                "title": finding.get("title"),
                "severity": finding.get("severity"),
                "severity_rationale": finding.get("severity_rationale"),
                "description": finding.get("description"),
                "evidence_summary": finding.get("evidence_summary"),
                "counts": finding.get("counts", []),
                "examples": finding.get("examples", []),
                "example_total": finding.get("example_total"),
                "examples_truncated": finding.get("examples_truncated"),
                "recommended_action": finding.get("recommended_action"),
                "limitations": finding.get("limitations", []),
                "assumptions": finding.get("assumptions", []),
            }
        )
    return findings


def _comparison_data(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    return {
        "run_id": payload.get("run_id"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "split": payload.get("split"),
        "strategies": payload.get("strategies", []),
        "rows": payload.get("rows", []),
        "plans": payload.get("plans", []),
        "selection_note": payload.get("selection_note"),
        "limitations": payload.get("limitations", []),
    }


def _model_summary(run: dict[str, Any]) -> dict[str, Any]:
    payload = run["payload"]
    base = {
        "run_id": payload.get("run_id") or run["run_id"],
        "label": run.get("label") or "",
        "created_at_utc": payload.get("created_at_utc"),
        "versions": payload.get("versions", {}),
        "warnings": payload.get("warnings", []),
    }
    if payload.get("kind") == "statistical_model":
        diagnostics = payload.get("diagnostics", {})
        return {
            **base,
            "kind": "statistical_model",
            "task": payload.get("task"),
            "specification": payload.get("specification"),
            "dataset": payload.get("dataset"),
            "population": payload.get("population"),
            "coefficients": payload.get("coefficients", []),
            "fit": payload.get("fit", {}),
            "diagnostics": {
                "condition_number": diagnostics.get("condition_number"),
                "vif": diagnostics.get("vif", []),
                "residual_summary": diagnostics.get("residual_summary"),
                "sample": {
                    key: diagnostics.get("sample", {}).get(key)
                    for key in ("method", "stride", "drawn_rows", "analyzed_rows", "description")
                },
            },
            "note": (
                "Statistical estimates describe the analysed complete-case rows. They are not "
                "predictive test metrics and are not causal effects."
            ),
        }
    if payload.get("kind") == "prediction_model":
        evaluation = payload.get("evaluation", {})
        metrics = evaluation.get("metrics", {})
        diagnostics = evaluation.get("diagnostics", {})
        selected = payload.get("selected", {})
        split = payload.get("split", {})
        return {
            **base,
            "kind": "prediction_model",
            "task": payload.get("task"),
            "outcome": payload.get("outcome"),
            "specification": payload.get("specification"),
            "design": payload.get("design"),
            "split": {
                "source": split.get("source"),
                "summary": split.get("summary"),
                "partitions": split.get("partitions"),
            },
            "selected": {
                "family": selected.get("family"),
                "label": selected.get("label"),
                "validation": selected.get("validation"),
                "parameters": selected.get("parameters"),
                "refit_rows": selected.get("refit_rows"),
            },
            "evaluation": {
                "partition": evaluation.get("partition"),
                "n": evaluation.get("n"),
                "metrics": metrics,
            },
            "diagnostics": {
                "calibration_summary": diagnostics.get("calibration_summary"),
                "qq": diagnostics.get("qq"),
                "influence": {
                    key: (diagnostics.get("influence") or {}).get(key)
                    for key in (
                        "applicable",
                        "reason",
                        "partition",
                        "n",
                        "parameters",
                        "counts",
                        "max_leverage",
                        "max_cooks",
                    )
                },
                "permutation_importance": {
                    key: (diagnostics.get("permutation_importance") or {}).get(key)
                    for key in ("applicable", "reason", "partition", "n", "metric", "rows")
                },
            },
            "subgroups": payload.get("subgroups"),
            "note": (
                "Predictive metrics describe one sealed test split. They are not causal effects, "
                "and a good score does not establish deployment safety."
            ),
        }
    return {
        **base,
        "kind": payload.get("kind", "unknown"),
        "note": "This run kind is not summarised by the dossier reporter.",
    }


def _summary(
    *,
    dataset: Any,
    study: dict[str, Any] | None,
    audit: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    models: list[dict[str, Any]],
    comparison_id: str | None,
    audit_id: str | None,
) -> dict[str, Any]:
    fields = {field["name"]: field["value"] for field in _declared_fields(study)}
    evaluation = (audit or {}).get("evaluation", {})
    findings = (audit or {}).get("findings", [])
    ranked = sorted(
        findings,
        key=lambda finding: (
            SEVERITY_RANK.get(str(finding.get("severity")), 0),
            str(finding.get("rule_id")),
        ),
        reverse=True,
    )
    analyses = []
    if audit:
        analyses.append(
            {
                "key": "audit",
                "label": "Leakage audit",
                "run_id": audit.get("run_id") or audit_id,
                "status": "included",
            }
        )
    else:
        analyses.append({"key": "audit", "label": "Leakage audit", "run_id": None, "status": "not_run"})
    if comparison:
        analyses.append(
            {
                "key": "comparison",
                "label": "Split comparison",
                "run_id": comparison.get("run_id") or comparison_id,
                "status": "included",
            }
        )
    else:
        analyses.append(
            {
                "key": "comparison",
                "label": "Split comparison",
                "run_id": None,
                "status": "not_run",
            }
        )
    for model in models:
        analyses.append(
            {
                "key": f"model:{model['run_id']}",
                "label": model.get("label") or model["run_id"],
                "run_id": model["run_id"],
                "status": "included",
            }
        )
    cautions: list[str] = []
    if audit:
        cautions.extend((audit.get("limitations") or [])[:2])
        not_evaluated = (audit.get("evaluation") or {}).get("not_evaluated", [])
        if not_evaluated:
            cautions.append(
                f"{len(not_evaluated)} check(s) were not evaluated. Absence of a finding for those "
                "checks is not evidence of absence."
            )
    else:
        cautions.append(
            "No audit run is included, so this report cannot state whether the split has leakage."
        )
    if comparison:
        cautions.append(
            "The split comparison reports consequences of alternative splits; it does not select "
            "a winner or prove that a split is safe."
        )
    if models:
        cautions.append(
            "Model results describe analysed rows or one sealed test split. They are not causal "
            "effects and do not guarantee deployment performance."
        )
    if dataset.warnings:
        cautions.extend(dataset.warnings[:1])
    cautions.append(
        "This dossier is an evidence package. It is not an IRB approval, a consent record or a "
        "certificate that the dataset is leakage-free."
    )
    return {
        "study_title": fields.get("title") or dataset.name,
        "objective": fields.get("objective"),
        "design": fields.get("design"),
        "dataset_name": dataset.name,
        "synthetic": dataset.is_synthetic,
        "split": (audit or {}).get("split", {}),
        "audit_headline": evaluation.get("headline"),
        "findings_total": len(findings),
        "findings_by_severity": evaluation.get("findings_by_severity", {}),
        "evaluated_rule_count": len(evaluation.get("evaluated_rule_ids", [])),
        "not_evaluated_count": len(evaluation.get("not_evaluated", [])),
        "key_findings": [
            {
                "rule_id": finding.get("rule_id"),
                "title": finding.get("title"),
                "severity": finding.get("severity"),
            }
            for finding in ranked[:4]
        ],
        "analyses": analyses,
        "model_count": len(models),
        "comparison_available": bool(comparison),
        "cautions": _unique(cautions),
        "note": (
            "This summary synthesises only the sections and runs named in the request. It makes no "
            "causal claim and does not convert not-evaluated checks into passed checks."
        ),
    }


def build_dossier(
    *,
    dataset: Any,
    study: dict[str, Any] | None,
    profile: dict[str, Any] | None,
    audit: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    models: list[dict[str, Any]],
    requested_sections: Iterable[str] | None = None,
    generated_at_utc: str | None = None,
    estimation_runs: list[dict[str, Any]] | None = None,
    graph_record: dict[str, Any] | None = None,
    presentation: str = "concise",
) -> dict[str, Any]:
    sections_requested = normalise_sections(requested_sections)
    specs = {spec["id"]: spec for spec in SECTION_SPECS}
    estimation_runs = estimation_runs or []
    causal_runs: list[dict[str, Any]] = []
    subgroup_runs: list[dict[str, Any]] = []
    robustness_runs: list[dict[str, Any]] = []
    whatif_runs: list[dict[str, Any]] = []
    for payload in estimation_runs:
        kind = payload.get("analysis_kind") or (
            "estimation_comparison" if "comparison" in payload else "estimation"
        )
        if kind in ("estimation", "estimation_comparison"):
            causal_runs.append(payload)
        elif kind == "subgroups":
            subgroup_runs.append(payload)
        elif kind == "robustness":
            robustness_runs.append(payload)
        elif kind == "what_if":
            whatif_runs.append(payload)
    audit_data = _audit_data(audit)
    findings = _findings_data(audit)
    comparison_data = _comparison_data(comparison)
    model_data = [_model_summary(run) for run in models]
    summary_data = _summary(
        dataset=dataset,
        study=study,
        audit=audit,
        comparison=comparison,
        models=model_data,
        comparison_id=comparison.get("run_id") if comparison else None,
        audit_id=audit.get("run_id") if audit else None,
    )

    sections: dict[str, dict[str, Any]] = {}

    def add(
        section_id: str,
        *,
        available: bool,
        data: Any = None,
        reason: str | None = None,
    ) -> None:
        sections[section_id] = _section(
            specs[section_id],
            included=section_id in sections_requested,
            available=available,
            data=data,
            reason=reason,
        )

    add("summary", available=True, data=summary_data)
    add("provenance", available=True, data=_provenance_data(dataset, study, profile))
    add("study", available=True, data=_study_data(study))

    audit_reason = "No audit run was named for this dossier. Run the audit, then generate again."
    add("audit", available=audit_data is not None, data=audit_data, reason=audit_reason)
    scorecard = (audit or {}).get("risk_scorecard")
    add(
        "scorecard",
        available=scorecard is not None,
        data=scorecard,
        reason="The risk scorecard is derived from an audit run; no audit run is included.",
    )
    add(
        "findings",
        available=audit_data is not None,
        data={"items": findings, "total": len(findings)},
        reason=audit_reason,
    )
    add(
        "comparison",
        available=comparison_data is not None,
        data=comparison_data,
        reason="No split comparison was named. Run a comparison to include its consequences.",
    )
    add(
        "models",
        available=bool(model_data),
        data={"runs": model_data, "total": len(model_data)},
        reason="No model run was named. Fit and select a model in Model Lab to include it.",
    )

    # -- dossier: causal sections from stored estimation runs ------------------- #
    estimation_reason = (
        "No estimation run was named for this dossier. Run the Effect Estimation Studio, "
        "then select the stored run in the Report Studio."
    )
    add(
        "causal_graph",
        available=graph_record is not None,
        data=(
            causal_graph_section(graph_record.get("spec", {}), graph_record)
            if graph_record is not None
            else None
        ),
        reason=(
            "No causal graph was named. The graph arrives with a stored estimation run; select "
            "one in the Report Studio."
        ),
    )
    add(
        "identification",
        available=bool(causal_runs or subgroup_runs or robustness_runs or whatif_runs),
        data=identification_section(estimation_runs) if estimation_runs else None,
        reason=estimation_reason,
    )
    add(
        "causal_estimation",
        available=bool(causal_runs),
        data=causal_estimation_section(causal_runs) if causal_runs else None,
        reason=estimation_reason,
    )
    add(
        "subgroups",
        available=bool(subgroup_runs),
        data=subgroups_section(subgroup_runs[0]) if subgroup_runs else None,
        reason=(
            "No subgroup run was named. Run subgroup effects in the Causal Research stage and "
            "select it in the Report Studio."
        ),
    )
    add(
        "robustness",
        available=bool(robustness_runs),
        data=robustness_section(robustness_runs[0]) if robustness_runs else None,
        reason=(
            "No robustness experiment was named. Run one in the Causal Research stage and "
            "select it in the Report Studio."
        ),
    )
    add(
        "what_if",
        available=bool(whatif_runs),
        data=what_if_section(whatif_runs[0]) if whatif_runs else None,
        reason=(
            "No what-if scenario was named. Run one in the Causal Research stage and select it "
            "in the Report Studio."
        ),
    )
    methodology_data = build_methodology(
        dataset=dataset,
        study=study,
        audit=audit,
        comparison=comparison,
        models=models,
        estimation_runs=estimation_runs,
        presentation=presentation,
    )
    add("methodology", available=True, data=methodology_data)

    not_evaluated = ((audit or {}).get("evaluation") or {}).get("not_evaluated", [])
    limitations = {
        "audit_limitations": (audit or {}).get("limitations", []),
        "audit_assumptions": (audit or {}).get("assumptions", []),
        "comparison_limitations": (comparison or {}).get("limitations", []),
        "dataset_warnings": dataset.warnings,
        "profile_warnings": (profile or {}).get("warnings", []),
        "model_warnings": [
            {"run_id": model["run_id"], "warnings": model.get("warnings", [])}
            for model in model_data
            if model.get("warnings")
        ],
        "estimation_warnings": [
            {
                "run_id": payload.get("run_id"),
                "analysis_kind": payload.get("analysis_kind"),
                "warnings": (payload.get("result") or {}).get("warnings") or payload.get("warnings"),
            }
            for payload in estimation_runs
            if ((payload.get("result") or {}).get("warnings") or payload.get("warnings"))
        ],
        "not_evaluated": not_evaluated,
        "general": [
            "Synthetic demonstrations are teaching fixtures, not evidence about real-world accuracy.",
            "A finding is evidence about the selected split, not a global safety verdict.",
            "Predictive and descriptive subgroup results are not causal treatment effects.",
            "The report embeds bounded evidence examples only, never the full dataset.",
        ],
    }
    add("limitations", available=True, data=limitations)

    environment = []
    for model in model_data:
        if model.get("versions"):
            environment.append({"run_id": model["run_id"], "versions": model["versions"]})
    reproducibility = {
        "report_schema_version": DOSSIER_SCHEMA_VERSION,
        "app": {"name": APP_NAME, "version": APP_VERSION},
        "generated_at_utc": generated_at_utc or datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.name,
        "dataset_sha256": dataset.fingerprint_sha256,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "audit_run_id": (audit or {}).get("run_id"),
        "comparison_run_id": (comparison or {}).get("run_id"),
        "model_run_ids": [model["run_id"] for model in model_data],
        "estimation_run_ids": [payload.get("run_id") for payload in estimation_runs],
        "methodology_presentation": presentation,
        "model_environments": environment,
        "deterministic_note": (
            "Audit and comparison algorithms are deterministic for identical input bytes, roles and "
            "settings. Only generation timestamps and run identifiers vary between executions."
        ),
        "storage_note": (
            "Dataset and run records live in the server process and expire. The HTML and JSON "
            "artifacts are the durable copies; raw data are not embedded."
        ),
    }
    add("reproducibility", available=True, data=reproducibility)

    integrity = {
        "raw_data_embedded": False,
        "row_predictions_embedded": False,
        "bounded_evidence_embedded": bool(findings),
        "note": (
            "The full uploaded dataset and row-level test predictions are not embedded. Findings "
            "carry only the bounded evidence examples already stored in the audit run. A SHA-256 "
            "fingerprint identifies bytes; it is not anonymisation."
        ),
    }

    return {
        "report_kind": "dossier",
        "schema_version": DOSSIER_SCHEMA_VERSION,
        "generated_at_utc": reproducibility["generated_at_utc"],
        "app": {"name": APP_NAME, "version": APP_VERSION},
        "title": f"SplitScope evidence dossier - {dataset.name}",
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "is_synthetic": dataset.is_synthetic,
            "source": dataset.source,
            "sha256": dataset.fingerprint_sha256,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
        },
        "request": {
            "sections": sections_requested,
            "audit_run_id": (audit or {}).get("run_id"),
            "comparison_run_id": (comparison or {}).get("run_id"),
            "model_run_ids": [model["run_id"] for model in model_data],
            "estimation_run_ids": [payload.get("run_id") for payload in estimation_runs],
        },
        "summary": summary_data,
        "sections": sections,
        "included_sections": sections_requested,
        "integrity": integrity,
        "reproducibility": reproducibility,
        "section_catalogue": list(SECTION_SPECS),
    }


__all__ = [
    "DEFAULT_SECTIONS",
    "DOSSIER_SCHEMA_VERSION",
    "SECTION_IDS",
    "SECTION_SPECS",
    "build_dossier",
    "normalise_sections",
]
