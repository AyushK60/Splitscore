# S9A API contract — causal effect estimation

Base: `/api` (FastAPI, OpenAPI at `/api/openapi.json`). Extends the S8A/S8C
contract unchanged: the single error envelope

```json
{"error": {"code": "...", "message": "...", "details": {...}}}
```

dataset liveness (missing/expired/evicted → HTTP 410 `expired_or_evicted`),
cross-dataset access refused with 404 `not_found`, and failures as 422
`validation_error` (or 409 `infeasible_operation` for a fingerprint mismatch /
413 `limit_exceeded` for bounds).

## Provenance block

Every success payload begins with the S8C block plus the estimation versions:

```json
{
  "graph_id": "cgraph-…", "dataset_id": "ds-…", "revision": 3,
  "spec_fingerprint_sha256": "…64 hex…",
  "estimation_version": "1.0.0", "estimation_schema_version": "1.0.0",
  …
}
```

## The estimation request

One nested object (`"request"`), strict (`extra="forbid"`; unknown fields are
422 — no client-supplied code, functions or payloads can reach the estimators):

```jsonc
{
  "treatment_node": "t",            // graph node, observed + column-anchored
  "outcome_node": "y",
  "adjustment_nodes": ["x1", "x2"], // verified by S8C before any fitting
  "treatment_mapping": {"treated": "1", "control": "0"},
  "estimand": "ate",                                   // the only supported value
  "cohort": {"split_assignment_id": null, "partition": null},
  "missing_data_policy": "complete_case",              // or "median_mode"
  "cross_fit": {"splits": 5, "group_column": null},
  "uncertainty": {"method": "bootstrap", "level": 0.95, "reps": 500, "seed": null},
  "propensity_truncation": null,                       // or {"lower": .05, "upper": .95}
  "expected_spec_fingerprint_sha256": "…64 hex…"       // optional staleness guard
}
```

## Endpoints

| Method & path | Body | Purpose |
|---|---|---|
| `POST /datasets/{id}/causal-graphs/{gid}/estimation/validate` | `{"request": …}` | Readiness probe: runs the full gate + cohort preview; estimates and stores nothing. |
| `POST /datasets/{id}/causal-graphs/{gid}/estimation/run` | `{"request": …, "estimator": "regression_adjustment"\|"ipw"\|"aipw", "label"?}` | Run one estimator; stores a bounded `estimation` run. |
| `POST /datasets/{id}/causal-graphs/{gid}/estimation/compare` | `{"request": …, "label"?}` | Runs all three estimators on one shared analysis; adds a `comparison` block. |
| `GET /datasets/{id}/estimation-runs` | — | Lists the dataset's stored estimation runs. |
| `GET /datasets/{id}/estimation-runs/{run_id}` | — | Returns one stored run, re-checked for staleness (`stale`, `staleness_reason`). |

## Run payload shape (run/compare)

```jsonc
{
  "gate": {"gate": "passed", "adjustment_set_verification": {…S8C verdict…}, "caveat": "…"},
  "analysis": {
    "rows_in_dataset": 360, "rows_in_analysis_cohort_frame": 360, "rows_final": 348,
    "treated_rows": 171, "control_rows": 177,
    "exclusions": [{"reason": "missing_outcome_value", "count": 12, "sample_row_ids": [...], "detail": "…"}],
    "covariates": [{"column": "x1", "kind": "numeric", "missing_in_cohort": 0, "levels": null}],
    "outcome_task": "linear", "outcome_coding": {…},
    "treatment_column": "t", "outcome_column": "y", "adjustment_columns": ["x1", "x2"]
  },
  "results": [
    {
      "status": "estimated",                       // or "failed" + "failure"
      "estimator": "ipw", "estimate": 1.42, "units": "outcome_units",
      "treated_mean": 3.11, "control_mean": 1.69, "sample_size": 348,
      "model_specification": {…}, "fold_row_counts": [...], "truncation": null,
      "uncertainty": {
        "status": "available", "method": "bootstrap_percentile", "level": 0.95,
        "standard_error": 0.11, "ci_lower": 1.21, "ci_upper": 1.63,
        "bootstrap": {"reps_requested": 500, "reps_succeeded": 500, "seed": 123, "refit_nuisance_models": true, …},
        "assumptions": [ "…independent observations…", "…every replicate refits…" ]
      },
      "diagnostics": {
        "balance": {"covariates": [{"column": "x1", "smd_unweighted": 0.66, "smd_weighted": 0.02, …}]},
        "overlap": {"propensity_summary": {…}, "extremes": {…},
                    "effective_sample_sizes": {…}, "warnings": […], "scope_note": "…"}
      },
      "warnings": [ … ]
    }
  ],
  "comparison": {"estimates": {…}, "max_pairwise_difference": 0.04, "interpretation": "…", "shared_analysis": "…"},   // compare only
  "defaults_applied": [ … ],
  "reproducibility": {
    "dataset_fingerprint_sha256": "…", "graph_id": "…", "graph_revision": 3,
    "graph_spec_fingerprint_sha256": "…", "treatment_mapping": {…}, "cohort": {…},
    "missing_data_policy": "complete_case", "cross_fitting": {…},
    "uncertainty": {…, "resolved_seed": 901234567}, "propensity_truncation": null,
    "software_versions": {…}, "limits": {…}
  },
  "scope_note": "The estimate is an average treatment effect computed from this dataset…",
  "run_id": "run-…", "created_at_utc": "…"
}
```

When a result cannot be produced, its entry is
`{"status": "failed", "estimator": "aipw", "failure": {"reason": "…", "details": {…}}}`
and the other estimators in the same request are unaffected. When an interval
cannot be constructed, `uncertainty.status` is `"unavailable"` with
`unavailable_reason` and `ci_lower`/`ci_upper` `null` — never a fabricated
interval.

## Error behaviour

* Fingerprint mismatch (client guard) → **409** `infeasible_operation`.
* Gate refusal (post-treatment/unobserved/open backdoor path, unanchored or
  unobserved node, ambiguous treatment encoding, degenerate arms, cohort too
  small, bound exceeded) → **422** with structured `details`
  (`verification.violations`, `unmatched_values_with_counts`, …).
* Unknown estimator or unknown request field → **422**.
* Dataset expired/evicted → **410**; graph of another dataset → **404**.

## Storage and staleness

Runs live in the existing bounded, TTL store (`kind="estimation"`); nothing
about the dataset or graph is mutated by any route. Retrieval re-checks both
fingerprints: either change → `stale: true` with `staleness_reason`. A
layout-only graph edit never changes the fingerprint and never stales a run.
