# S9B — API integration

The studio consumes only the S9A estimation routes and the existing S8A causal
graph routes. No endpoint was added; the one payload addition is the bounded
propensity histogram described at the end.

## Routes consumed

| Purpose | Request |
|---|---|
| Saved graphs for the dataset | `GET /api/datasets/{dataset_id}/causal-graphs` |
| Load a saved graph (nodes, edges, scope, fingerprints, validation) | `GET /api/datasets/{dataset_id}/causal-graphs/{graph_id}` |
| S8C identification (advisory in the UI; the backend gate is authoritative) | `POST …/causal-graphs/{graph_id}/identification` with `{treatment, outcome}` |
| Adjustment-set verdict for the current set | `POST …/causal-graphs/{graph_id}/adjustment-set` |
| Create the demonstration graph (demo only) | `POST /api/datasets/{dataset_id}/causal-graphs` |
| Observed treatment values | `GET /api/datasets/{dataset_id}/column-values?column=…&limit=40` |
| **Readiness probe (estimates nothing, stores nothing)** | `POST …/causal-graphs/{graph_id}/estimation/validate` |
| **One estimator** | `POST …/causal-graphs/{graph_id}/estimation/run` |
| **Three-estimator comparison** | `POST …/causal-graphs/{graph_id}/estimation/compare` |
| Run history | `GET /api/datasets/{dataset_id}/estimation-runs` |
| Stored run (staleness re-checked by the backend) | `GET /api/datasets/{dataset_id}/estimation-runs/{run_id}` |

`frontend/src/api/client.ts` wraps these in `estimationApi` (`validate`, `run`,
`compare`, `runs`, `runDetail`); graph calls use the existing `causalApi`.

## Request body sent (strict S9A schema)

```json
{
  "request": {
    "estimand": "ate",
    "treatment_node": "treatment",
    "outcome_node": "outcome",
    "adjustment_nodes": ["age", "baseline_score", "region"],
    "treatment_mapping": { "treated": "1", "control": "0" },
    "cohort": { "split_assignment_id": null, "partition": null },
    "missing_data_policy": "complete_case",
    "cross_fit": { "splits": 5, "group_column": null },
    "uncertainty": { "method": "bootstrap", "level": 0.95, "reps": 500, "seed": null },
    "propensity_truncation": null,
    "expected_spec_fingerprint_sha256": "<current graph scientific fingerprint>"
  },
  "estimator": "aipw",
  "label": ""
}
```

- `run` adds `estimator`; `compare` omits it and runs all three.
- Adjustment nodes are sorted before sending, so two equivalent selections
  produce one request identity.
- The cohort object is always explicit; a partition is only sent together with a
  split-assignment id.
- Truncation is `null` unless the user enables it; the studio then sends the
  lower/upper bounds as entered (the backend validates the range).
- The seed is `null` when empty, which means "draw and record one". The resolved
  seed is displayed from the response.
- `expected_spec_fingerprint_sha256` is the fingerprint of the graph currently
  loaded. A different server-side graph yields HTTP 409 and the studio says so.

Nothing unsupported by the backend is offered: no ATT/CATE, no matching, no
alternative uncertainty methods, no cohort filter that has no route.

## Readiness response used by the setup panel

`validate` returns the graph envelope plus:

| Field | Use |
|---|---|
| `readiness: "ready"` | Enables the run only when the response signature equals the current request signature. |
| `gate.adjustment_set_verification.valid / violations / interpretation / interpretation_note` | Shown in the methodology view and in the blocked panel. |
| `gate.caveat` | Repeated verbatim in the methodology limitations. |
| `cohort_preview.rows_final / treated_rows / control_rows / exclusions` | "N rows would be analysed (x treated, y control)" and exclusion count. |
| `limits` | Displayed as hard bounds in the methodology disclosure. |
| `note` | "Nothing was estimated and nothing was stored." |

A refusal (409 structural change, 410 dataset expiry, 422 invalid configuration)
becomes a named blocked state with the backend's message and structured details,
not a silent disabled button.

## Result payload → screen

| Payload field | Screen |
|---|---|
| `results[]` (`status`, `estimate`, `mu1`, `mu0`, `units`, `sample_size`, `uncertainty`, `model_specification`, `warnings`, `failure.reason`) | Effect summary dots/intervals and comparison table; methodology estimator list |
| `results[].uncertainty.status/unavailable_reason` | "interval unavailable" — never replaced by invented bounds |
| `results[].diagnostics.balance.covariates[].smd_unweighted / smd_weighted / kind / level` | Love plot and balance table |
| `results[].diagnostics.balance.weighted` | Whether post-weighting values exist at all |
| `results[].diagnostics.balance.diagnostic_imputation` (when present) | Balance imputation disclosure |
| `results[].diagnostics.overlap.propensity_summary.quantiles_*` | Overlap quantile strip and central 99% window |
| `results[].diagnostics.overlap.propensity_histogram` | 20-bin overlaid histogram and its table |
| `results[].diagnostics.overlap.extremes` | Extreme-score chips and weight table |
| `results[].diagnostics.overlap.effective_sample_sizes` | Raw vs ESS bars, retained fractions |
| `results[].diagnostics.overlap.weight_summary` | Maximum weight and total-weight quantiles |
| `results[].diagnostics.overlap.warnings / truncation` | Warning list, truncation disclosure |
| `comparison.estimates / max_pairwise_difference / interpretation` | "Reading the comparison" block (reported, never resolved into one number) |
| `analysis.*` (rows, exclusions, covariates, outcome task/units, policy) | Methodology cohort accounting and the interpretation sentence |
| `reproducibility.*` (fingerprints, graph revision, mapping, cohort, cross-fitting, uncertainty, seed, truncation, software versions, limits) | Methodology provenance and every figure's caption; staleness comparison |
| `defaults_applied[]` | "Defaults the server applied" disclosure |
| `scope_note`, `gate.caveat` | Scientific caveats under figures and in methods |
| `run_id`, `created_at_utc`, `stale`, `staleness_reason` | Result meta line, history and stale alert |

## Staleness handling

The frontend computes named reasons by comparing `reproducibility` with the
current study:

`server_stale` (backend flag), `dataset_changed`, `graph_switched`,
`graph_changed`, `treatment_changed`, `outcome_changed`, `adjustment_changed`,
`mapping_changed`, `cohort_changed`, `missing_policy_changed`,
`crossfit_changed`, `uncertainty_method_changed`, `uncertainty_level_changed`,
`reps_changed`, `seed_changed` (only for a specified seed that differs from the
resolved one), `truncation_changed`.

Graph **layout** coordinates are not part of `spec_fingerprint_sha256`, so a
drag never produces a reason. The stored-run route additionally re-checks
staleness server-side (`mark_staleness`) and can return `stale: true` with
`staleness_reason`; that reason is displayed verbatim.

## Propagated errors

| Status | Studio behaviour |
|---|---|
| 404 | Named failure ("graph/dataset/run not found") with the backend message. |
| 409 | "The graph changed on the server" with the instruction to reload and re-probe; no retry loop. |
| 410 | "The dataset is no longer available", explanation of the bounded store, and a **Reload the dataset** button. |
| 413 | Backend message in the run alert (cohort too large). |
| 422 | Readiness blocked or run alert with `verification.violations`, `unmatched_values_with_counts`, `missing_columns`, `fix` and `reason` details flattened into a readable list. |
| Network/unknown | Alert with the message; the running state always resolves to ready, failed or dismissed — no indefinite spinner. |

## Bounded backend extension: the propensity histogram

S9A exposed quantiles but no per-group distribution, and the S9B specification
forbids inferring per-observation distributions from aggregate quantiles. The
smallest justified extension was added in
`backend/app/causal/estimation/diagnostics.py`:

```json
"propensity_histogram": {
  "bin_edges": [0.0, 0.05, …, 1.0],
  "bin_count": 20,
  "treated_counts": [ … 20 integers … ],
  "control_counts": [ … 20 integers … ],
  "treated_share": [ … within-arm relative frequencies … ],
  "control_share": [ … ],
  "definition": "Counts of fitted propensity scores in 20 fixed bins …"
}
```

- Fixed 20 bins of width 0.05 over [0, 1]; a bin edge is stable across runs so
  figures are comparable.
- Counts and within-arm shares only. No row identifiers, no raw covariate rows,
  no per-observation scores, no kernel density and no extrapolation.
- The count vectors are bounded by the number of rows already permitted in the
  estimation payload; the response grows by at most 40 integers and 40 rounded
  floats.
- Registered by `HISTOGRAM_BINS = 20`; `__all__` exports the function so it can
  be tested directly.
- Independent tests in `backend/tests/test_s9b_diagnostics.py` verify bin edges,
  count preservation, shares summing to one per non-empty arm, the empty-arm
  case, scores in the extreme bins, and the overlap payload wiring.

The figure labels the bars as fitted propensities and the table publishes the
same counts so the chart has an accessible numeric equivalent.
