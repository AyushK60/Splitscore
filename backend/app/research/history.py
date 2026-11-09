"""Research run history and reproducibility manifests.

One coherent read-only view over the runs the process already stores, grouped
and typed per dataset - never a second storage system. The bounded in-memory
store (``app.core.store``) remains the only home of run state; history is a
projection of it that adds the identity, parameter, staleness and
reproducibility structure the raw stored payloads carry implicitly.

Honesty rules enforced here:

* A field the run did not record is ``"not_recorded"`` (or ``None`` with a
  reason) - never inferred, never invented.
* A run whose dataset fingerprint no longer matches the live dataset, or
  whose causal graph is gone or structurally changed, is reported **stale**
  with the reason spelled out; the numbers themselves are never edited.
* A manifest is metadata-only. It never embeds analysis results or dataset
  content, and it states plainly that reproducing an analysis requires the
  original data and a compatible software environment.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Callable

from app.audit.dataset import Dataset
from app.core.store import StoredRun

#: Version of the history projection contract, echoed in every payload.
HISTORY_SCHEMA_VERSION = "1.0.0"

#: Version of the portable reproducibility-manifest contract.
MANIFEST_SCHEMA_VERSION = "1.0.0"

NOT_RECORDED = "not_recorded"

MANIFEST_REPRODUCTION_NOTE = (
    "This manifest records how a stored analysis was configured, not a "
    "guarantee it can be reproduced. Reproduction additionally requires the "
    "original dataset (by the recorded fingerprint) and a compatible software "
    "environment. The manifest embeds no analysis results and no dataset "
    "content; export the run JSON separately if the results are needed."
)

STUDY_LINK_NOTE = (
    "Studies are not currently linked to stored runs, so no study identity is "
    "recorded here. This is an explicit gap of the current run storage, not a "
    "missing export."
)


def canonical_json(payload: Any) -> str:
    """Deterministic serialisation for stable hashing of manifest content."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _payload_timestamp(payload: dict[str, Any]) -> str | None:
    for key in ("created_at_utc", "generated_at_utc"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return None


def _dataset_fingerprint_of_run(payload: dict[str, Any], kind: str) -> str | None:
    """The dataset fingerprint the run recorded, per the run kind's contract."""
    if kind == "estimation":
        value = payload.get("reproducibility", {}).get("dataset_fingerprint_sha256")
        return value if isinstance(value, str) else None
    dataset = payload.get("dataset")
    if isinstance(dataset, dict):
        value = dataset.get("fingerprint_sha256") or dataset.get("sha256")
        return value if isinstance(value, str) else None
    return None


def _analysis_kind(payload: dict[str, Any], kind: str) -> str:
    if kind == "estimation":
        explicit = payload.get("analysis_kind")
        if isinstance(explicit, str):
            return explicit
        if "comparison" in payload:
            return "estimation_comparison"
        return "estimation"
    if kind == "audit":
        return "leakage_audit"
    if kind == "comparison":
        return "split_comparison"
    model_kind = payload.get("kind")
    if model_kind in ("statistical_model", "prediction_model"):
        return str(model_kind)
    return kind


def _estimation_parameters(payload: dict[str, Any]) -> dict[str, Any]:
    repro = payload.get("reproducibility", {})
    parameters: dict[str, Any] = {
        "estimand": payload.get("estimand"),
        "treatment_node": repro.get("treatment_node"),
        "outcome_node": repro.get("outcome_node"),
        "adjustment_nodes": repro.get("adjustment_nodes"),
        "estimators": repro.get("estimators"),
        "missing_data_policy": repro.get("missing_data_policy"),
        "cross_fitting": repro.get("cross_fitting"),
        "uncertainty": repro.get("uncertainty"),
        "cohort_rows": payload.get("analysis", {}).get("rows_final"),
    }
    analysis_kind = _analysis_kind(payload, "estimation")
    if analysis_kind == "subgroups":
        subgroup = payload.get("subgroup", {})
        parameters["subgroup"] = {
            "node_id": subgroup.get("node_id"),
            "column": subgroup.get("column"),
            "kind": subgroup.get("kind"),
            "numeric_binning": subgroup.get("numeric_binning"),
            "intent": subgroup.get("intent"),
        }
    if analysis_kind == "robustness":
        parameters["experiment"] = payload.get("reproducibility", {}).get("experiment")
    if analysis_kind == "what_if":
        parameters["scenario"] = payload.get("reproducibility", {}).get("scenario")
    return parameters


def _audit_parameters(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("audit_config", {})
    return {
        "audit_config": {key: config[key] for key in sorted(config)} if isinstance(config, dict) else {},
        "target": payload.get("roles", {}).get("target"),
        "split": payload.get("split", {}).get("label") if isinstance(payload.get("split"), dict) else None,
        "findings_total": payload.get("evaluation", {}).get("findings_total"),
    }


def _comparison_parameters(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategies": [strategy.get("strategy_id") for strategy in payload.get("strategies", []) if isinstance(strategy, dict)],
        "rows_compared": len(payload.get("rows", [])),
        "target": payload.get("roles", {}).get("target"),
        "selection_note": payload.get("selection_note"),
    }


def _model_parameters(payload: dict[str, Any]) -> dict[str, Any]:
    specification = payload.get("specification", {})
    if payload.get("kind") == "prediction_model":
        return {
            "task": payload.get("task"),
            "outcome": specification.get("outcome"),
            "predictors": specification.get("predictors"),
            "split": payload.get("split", {}).get("label") if isinstance(payload.get("split"), dict) else specification.get("split"),
        }
    return {
        "task": payload.get("task"),
        "formula": specification.get("formula") if isinstance(specification, dict) else None,
        "outcome": specification.get("outcome") if isinstance(specification, dict) else None,
    }


def _parameters(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind == "estimation":
        return _estimation_parameters(payload)
    if kind == "audit":
        return _audit_parameters(payload)
    if kind == "comparison":
        return _comparison_parameters(payload)
    return _model_parameters(payload)


def _stale_reasons(
    run: StoredRun,
    payload: dict[str, Any],
    dataset: Dataset,
    graph_lookup: Callable[[str, str], tuple[str, str] | None] | None,
) -> tuple[bool, list[str]]:
    """Re-check one stored run against the live dataset (and graph).

    ``graph_lookup(graph_id, dataset_id)`` returns the live graph's
    ``(graph_id, spec_fingerprint)`` or ``None`` when the graph no longer
    exists; only estimation runs consult it.
    """
    reasons: list[str] = []
    recorded = _dataset_fingerprint_of_run(payload, run.kind)
    if recorded is not None and recorded != dataset.fingerprint_sha256:
        reasons.append(
            "The dataset in memory no longer matches the fingerprint this run was computed on."
        )
    if recorded is None:
        reasons.append(
            "This run kind did not record a dataset fingerprint, so staleness against the "
            "live dataset cannot be verified."
        )
    if run.kind == "estimation" and graph_lookup is not None:
        repro = payload.get("reproducibility", {})
        graph_id = repro.get("graph_id")
        recorded_graph_fingerprint = repro.get("graph_spec_fingerprint_sha256")
        live = graph_lookup(str(graph_id), run.dataset_id) if graph_id else None
        if live is None:
            reasons.append(
                "The causal graph this analysis was computed against no longer exists for "
                "this dataset."
            )
        elif recorded_graph_fingerprint and live[1] != recorded_graph_fingerprint:
            reasons.append(
                "The stored graph's scientific content changed after this run was computed."
            )
    return bool(reasons), reasons


def build_history_entry(
    run: StoredRun,
    *,
    age_seconds: float,
    dataset: Dataset,
    graph_lookup: Callable[[str, str], tuple[str, str] | None] | None,
) -> dict[str, Any]:
    """One typed history entry for one stored run."""
    payload = run.payload
    stale, reasons = _stale_reasons(run, payload, dataset, graph_lookup)
    entry: dict[str, Any] = {
        "run_id": run.run_id,
        "kind": run.kind,
        "analysis_kind": _analysis_kind(payload, run.kind),
        "label": run.label,
        "created_at_utc": _payload_timestamp(payload),
        "age_seconds": round(age_seconds, 1),
        "dataset": {
            "dataset_id": run.dataset_id,
            "dataset_name": dataset.name,
            "dataset_fingerprint_sha256": _dataset_fingerprint_of_run(payload, run.kind) or NOT_RECORDED,
        },
        "study": {
            "study_id": None,
            "note": STUDY_LINK_NOTE,
        },
        "parameters": _parameters(payload, run.kind),
        "status": "available",
        "stale": stale,
        "staleness_reasons": reasons,
    }
    if run.kind == "estimation":
        repro = payload.get("reproducibility", {})
        entry["graph"] = {
            "graph_id": repro.get("graph_id"),
            "graph_spec_fingerprint_sha256": repro.get("graph_spec_fingerprint_sha256"),
            "graph_revision": repro.get("graph_revision"),
        }
        entry["reproducibility"] = {
            "resolved_seed": (repro.get("uncertainty") or {}).get("resolved_seed"),
            "cross_fitting": repro.get("cross_fitting"),
            "uncertainty": repro.get("uncertainty"),
            "estimation_version": repro.get("estimation_version"),
            "software_versions": repro.get("software_versions"),
        }
    else:
        entry["graph"] = None
        entry["reproducibility"] = {
            "resolved_seed": None,
            "note": (
                "This run kind predates structured reproducibility capture; its configuration "
                "is recorded under 'parameters'."
            ),
        }
    return entry


def build_run_history(
    dataset: Dataset,
    stored_runs: list[tuple[StoredRun, float]],
    graph_lookup: Callable[[str, str], tuple[str, str] | None] | None,
) -> dict[str, Any]:
    """The full history payload for one dataset.

    ``stored_runs`` holds ``(run, age_seconds)`` pairs, newest first, exactly
    as the store lists them; this function never re-orders or re-derives them.
    """
    entries = [
        build_history_entry(run, age_seconds=age, dataset=dataset, graph_lookup=graph_lookup)
        for run, age in stored_runs
    ]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["analysis_kind"]] = counts.get(entry["analysis_kind"], 0) + 1
    return {
        "history_schema_version": HISTORY_SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "fingerprint_sha256": dataset.fingerprint_sha256,
            "row_count": dataset.row_count,
            "column_count": len(dataset.columns),
        },
        "runs": entries,
        "counts_by_analysis_kind": counts,
        "stale_count": sum(1 for entry in entries if entry["stale"]),
        "storage_note": (
            "Runs live in this server's bounded in-memory store (LRU, with a TTL). Expired or "
            "evicted runs are absent from this history entirely - they are not recoverable. "
            "This projection adds identity and staleness structure; it stores nothing itself."
        ),
    }


# --------------------------------------------------------------------------- #
# Portable reproducibility manifest
# --------------------------------------------------------------------------- #


def _manifest_analysis(payload: dict[str, Any], run: StoredRun) -> dict[str, Any]:
    analysis = payload.get("analysis")
    if isinstance(analysis, dict):
        return {
            "rows_in_dataset": analysis.get("rows_in_dataset"),
            "rows_in_analysis_cohort_frame": analysis.get("rows_in_analysis_cohort_frame"),
            "rows_final": analysis.get("rows_final"),
            "treated_rows": analysis.get("treated_rows"),
            "control_rows": analysis.get("control_rows"),
            "missing_data_policy": analysis.get("missing_data_policy"),
            "outcome_task": analysis.get("outcome_task"),
            "outcome_coding": analysis.get("outcome_coding"),
            "covariates": analysis.get("covariates"),
        }
    return {"note": "This run kind does not record a structured analysis block."}


def build_manifest(
    run: StoredRun,
    dataset: Dataset,
    graph_lookup: Callable[[str, str], tuple[str, str] | None] | None,
) -> dict[str, Any]:
    """A portable, metadata-only reproducibility manifest for one stored run."""
    payload = run.payload
    stale, reasons = _stale_reasons(run, payload, dataset, graph_lookup)
    manifest: dict[str, Any] = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_kind": "reproducibility_manifest",
        "generated_at_utc": _utc_now(),
        "run": {
            "run_id": run.run_id,
            "kind": run.kind,
            "analysis_kind": _analysis_kind(payload, run.kind),
            "label": run.label,
            "created_at_utc": _payload_timestamp(payload) or NOT_RECORDED,
            "stale": stale,
            "staleness_reasons": reasons,
        },
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "source": dataset.source,
            "is_synthetic": dataset.is_synthetic,
            "fingerprint_sha256": dataset.fingerprint_sha256,
            "row_count": dataset.row_count,
            "column_count": len(dataset.columns),
            "fingerprint_recorded_in_run": _dataset_fingerprint_of_run(payload, run.kind) is not None,
            "dataset_matches_run": not any("fingerprint" in reason for reason in reasons),
            "still_in_memory": True,
        },
        "study": {
            "study_id": None,
            "note": STUDY_LINK_NOTE,
        },
        "graph": None,
        "analysis_definition": _parameters(payload, run.kind),
        "cohort": _manifest_analysis(payload, run.kind),
        "reproducibility": {},
        "results_included": "metadata_only",
        "reproduction_requirements": MANIFEST_REPRODUCTION_NOTE,
    }
    if run.kind == "estimation":
        repro = payload.get("reproducibility", {})
        manifest["reproducibility"] = {
            "estimation_version": repro.get("estimation_version"),
            "estimation_schema_version": repro.get("estimation_schema_version"),
            "estimators": repro.get("estimators"),
            "treatment_mapping": repro.get("treatment_mapping"),
            "cohort_request": repro.get("cohort"),
            "missing_data_policy": repro.get("missing_data_policy"),
            "cross_fitting": repro.get("cross_fitting"),
            "uncertainty": repro.get("uncertainty"),
            "propensity_truncation": repro.get("propensity_truncation"),
            "software_versions": repro.get("software_versions") or NOT_RECORDED,
            "limits": repro.get("limits"),
        }
        manifest["graph"] = {
            "graph_id": repro.get("graph_id"),
            "graph_revision": repro.get("graph_revision"),
            "graph_spec_fingerprint_sha256": repro.get("graph_spec_fingerprint_sha256"),
            "still_in_memory": (
                graph_lookup(str(repro.get("graph_id")), run.dataset_id) is not None
                if repro.get("graph_id")
                else False
            ),
            "adjustment_nodes": repro.get("adjustment_nodes"),
            "treatment_node": repro.get("treatment_node"),
            "outcome_node": repro.get("outcome_node"),
        }
    else:
        manifest["reproducibility"] = {
            "software_versions": NOT_RECORDED,
            "resolved_seed": NOT_RECORDED,
            "note": (
                "This run kind predates structured reproducibility capture; its configuration "
                "is recorded under 'analysis_definition'."
            ),
        }
        manifest["graph"] = None

    integrity_payload = {key: value for key, value in manifest.items() if key != "integrity"}
    digest = hashlib.sha256(canonical_json(integrity_payload).encode("utf-8")).hexdigest()
    manifest["integrity"] = {
        "canonical_json_sha256": digest,
        "canonicalisation": (
            "sha256 over UTF-8 of JSON with sorted keys, compact separators, no NaN/Infinity; "
            "computed over the manifest without this integrity block."
        ),
    }
    return manifest


__all__ = [
    "HISTORY_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "build_history_entry",
    "build_manifest",
    "build_run_history",
    "canonical_json",
]
