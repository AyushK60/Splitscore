# S8C API contract — causal identification

Base: `/api` (FastAPI, OpenAPI at `/api/openapi.json`). Extends the S8A
contract; all S8A rules carry over: the single error envelope

```json
{"error": {"code": "...", "message": "...", "details": {...}}}
```

dataset liveness (missing/expired/evicted → HTTP 410 `expired_or_evicted`),
cross-dataset access refused with 404 `not_found`, and graph-validation
failures as 422 `validation_error` with a per-issue `details.errors` list.

**Every route here is read-only.** No identification operation mutates or
stores the graph or the dataset; a dedicated test asserts revision and
fingerprint are unchanged after calling all four.

## Provenance block

Every success payload begins with the block that makes staleness detection
possible:

```json
{
  "graph_id": "cgraph-…",
  "dataset_id": "ds-…",
  "revision": 3,
  "spec_fingerprint_sha256": "…64 hex…",
  "schema_version": "1.0.0",
  …
}
```

## Endpoints

| Method & path | Body | Purpose |
|---|---|---|
| `POST /datasets/{id}/causal-graphs/{gid}/d-separation` | `{"x", "y", "conditioning": []}` | Exact graphical independence test. |
| `POST /datasets/{id}/causal-graphs/{gid}/adjustment-evaluation` | `{"treatment?", "outcome?", "adjustment_set": []}` | Classical backdoor verdict on one proposed set. |
| `POST /datasets/{id}/causal-graphs/{gid}/adjustment-search` | `{"treatment?", "outcome?"}` | Bounded search for inclusion-minimal observed sets. |
| `POST /datasets/{id}/causal-graphs/{gid}/identification` | `{"treatment?", "outcome?", "method": "backdoor"}` | Structured identification status + rule-based explanations. |

`treatment`/`outcome` default to the graph's saved analysis scope. POST is
used throughout because these are structured analytical queries with JSON
bodies.

## d-separation example

```http
POST /api/datasets/ds-ab12cd34/causal-graphs/cgraph-9f2a1b7c44/d-separation
{"x": "age", "y": "churn", "conditioning": ["tenure"]}
```

```json
{
  "graph_id": "cgraph-9f2a1b7c44",
  "spec_fingerprint_sha256": "…",
  "x": "age", "y": "churn", "conditioning": ["tenure"],
  "d_separated": false,
  "interpretation": "Under the assumed DAG, 'age' and 'churn' are d-connected given the conditioning set.",
  "algorithm": {"name": "bayes-ball-reachability", "version": "1.0.0",
                "reference": "Koller & Friedman (2009), Algorithm 3.1 (Reachable)"},
  "interpretation_note": "d-separation is a property of the assumed graph… It is not an empirically established independence in the dataset…"
}
```

Query errors (unknown node, identical endpoints, endpoint inside the
conditioning set) are HTTP 422 with `details.errors[0].code` ∈
`unknown_node | same_node | conditioning_contains_endpoint`.

## Adjustment evaluation example

```http
POST …/adjustment-evaluation
{"adjustment_set": ["satisfaction", "u_service"]}
```

```json
{
  "treatment": "tenure", "outcome": "churn",
  "adjustment_set": ["satisfaction", "u_service"],
  "valid": false,
  "violations": [
    {"code": "post_treatment_variable", "node_id": "satisfaction", "message": "…"},
    {"code": "unobserved_variable", "node_id": "u_service", "message": "…"}
  ],
  "open_backdoor_paths": [],
  "path_listing_bounded": false,
  "interpretation": "This set does not satisfy the classical backdoor criterion…",
  "interpretation_note": "Backdoor admissibility is a property of the assumed graph…"
}
```

Violation codes: `unknown_variable`, `adjustment_contains_scope`,
`unobserved_variable`, `post_treatment_variable`, `open_backdoor_path`.

## Adjustment search example

```json
{
  "treatment": "tenure", "outcome": "churn",
  "search_status": "incomplete",
  "sets": [{"set": ["age"], "verification": "verified_canonical_candidate",
            "inclusion_minimal": true}],
  "forbidden_variables": ["tenure", "churn", "satisfaction"],
  "eligible_candidates": ["age", "month_index", "…"],
  "candidates_considered": 3,
  "bounds": {"max_exhaustive_candidates": 14, "max_candidate_evaluations": 200000,
             "max_search_seconds": 10.0},
  "status_reason": "The graph has 15 eligible observed candidates, above the exhaustive-enumeration bound of 14… the list is NOT exhaustive…"
}
```

`search_status` is `complete` or `incomplete`. A `complete` search with empty
`sets` carries a fixed `status_reason` stating the result is specific to the
backdoor criterion and is not a general non-identifiability proof.

## Identification status example

```json
{
  "identification_version": "1.0.0",
  "status": "backdoor_adjustment_available",
  "treatment": "tenure", "outcome": "churn",
  "explanations": [
    {"code": "confounder_needs_adjustment", "title": "…", "body": "…",
     "node_ids": ["age"]}
  ],
  "caveats": ["Adjusting for the reported set is licensed by the drawn graph only…"],
  "search": { …adjustment-search payload… },
  "interpretation_note": "Identification here is graphical…"
}
```

Statuses: `backdoor_adjustment_available`, `no_eligible_backdoor_set`,
`search_incomplete`, `invalid_graph`, `invalid_scope`,
`missing_dataset_variables`, `unsupported_identification_method`. An
unsupported `method` is reported **in-band** (HTTP 200 with the refusal
status), because the query was answerable — the answer is "no".

## Lifecycle notes

* Results are addressed to an exact `spec_fingerprint_sha256`; the frontend
  additionally keys results to a client-side scientific signature (edges,
  scope, observed status) so a layout drag never invalidates a result while a
  structural edit always does.
* Graphs live in the same in-memory, TTL-bounded store family as datasets;
  every identification route resolves the dataset through the same typed 410
  path and prunes orphaned graphs exactly as the S8A routes do.
