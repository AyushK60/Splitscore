# S8A API contract — causal graphs

Base: `/api` (FastAPI, OpenAPI at `/api/openapi.json`, schema `1.0.0`).
All bodies are JSON. Errors use the application's single envelope:

```json
{"error": {"code": "...", "message": "...", "details": {...}}}
```

Graph-validation failures return HTTP 422 with `error.code = "validation_error"`
and `error.details.errors` — the structured, per-issue list the future editor
renders. Nothing is stored or mutated when validation fails.

All routes require the dataset to be live in the store. A missing, expired or
evicted dataset yields HTTP 410 `expired_or_evicted`. A valid graph id under a
different dataset yields HTTP 404 `not_found` — cross-dataset access is
refused, never silently redirected.

## Objects

**Node** (`CausalNode`):

```json
{
  "node_id": "tenure",            // ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$
  "label": "Tenure",              // required, <= 120 chars
  "column": "tenure_months",      // optional dataset column
  "observed": true,               // false only when explicitly declared
  "kind": "treatment",            // treatment|outcome|covariate|mediator|effect_modifier|unobserved
  "description": null,
  "layout": {"x": 120.0, "y": 80.0}  // optional, display-only
}
```

**Edge** (`CausalEdge`): `{"source", "target", "rationale?", "reference?"}` —
an *assumed* causal relationship.

**Analysis scope**: `{"treatment": "tenure", "outcome": "churn"}` (both
nullable during editing). One treatment / one outcome for V2's first workflow;
the object exists so multiple exposures/outcomes can be added later.

**Assumption** (`AssumptionRecord`): `{"assumption_id", "category", "status",
"source?", "rationale?"}` with categories `temporal_ordering`,
`causal_relationships`, `unmeasured_confounding`, `consistency`,
`exchangeability`, `positivity`, `selection`, `measurement`,
`target_population` and statuses `declared`, `not_assessed`,
`flagged_for_review`, `unsupported`.

**Limits**: 60 nodes, 240 edges, 64 assumptions, 32 stored graphs per server.
Exceeding a limit is a 422, never a silent truncation.

## Endpoints

| Method & path | Purpose | Failure modes |
|---|---|---|
| `POST /datasets/{id}/causal-graphs` | Create and validate a graph. Body: `{"graph": {spec}}`. `201` returns the full graph payload. | 410 unknown dataset; 422 validation errors (nothing stored). |
| `GET /datasets/{id}/causal-graphs` | List summaries for the dataset. | 410. |
| `GET /datasets/{id}/causal-graphs/{gid}` | Full graph payload (nodes with derived structure, edges, analysis, assumptions, validation). | 410; 404 wrong dataset or unknown id. |
| `PUT /datasets/{id}/causal-graphs/{gid}` | Replace the specification. `200` with the updated payload, revision +1. | 422 invalid spec — **stored graph untouched**. |
| `DELETE /datasets/{id}/causal-graphs/{gid}` | Delete. `200` `{"deleted": true, ...}`. | 410; 404. |
| `GET /datasets/{id}/causal-graphs/{gid}/validation` | Re-validate against the dataset currently in memory. Read-only. | 410; 404. |
| `GET /datasets/{id}/causal-graphs/{gid}/export` | Versioned export envelope (`Content-Disposition: attachment`). | 410; 404. |
| `POST /datasets/{id}/causal-graphs/import` | Import an export file as a **new** graph bound to this dataset. Body: `{"export_file": {...}}`. | 422 not an export / wrong schema version / malformed spec / columns that do not resolve; 410. |

## Example: create

```http
POST /api/datasets/ds-ab12cd34/causal-graphs
```

```json
{"graph": {
  "name": "Retention hypothesis",
  "dataset_id": "ds-ab12cd34",
  "nodes": [
    {"node_id": "tenure", "label": "Tenure", "column": "tenure_months", "kind": "treatment"},
    {"node_id": "churn",  "label": "Churn",  "column": "churn",  "kind": "outcome"},
    {"node_id": "age",    "label": "Age",    "column": "age"}
  ],
  "edges": [
    {"source": "age",    "target": "tenure", "rationale": "age precedes tenure"},
    {"source": "age",    "target": "churn",  "rationale": "age shapes churn risk"},
    {"source": "tenure", "target": "churn",  "rationale": "hypothesised retention effect"}
  ],
  "analysis": {"treatment": "tenure", "outcome": "churn"},
  "assumptions": [
    {"assumption_id": "asmp-population", "category": "target_population",
     "status": "declared", "source": "study card",
     "rationale": "adult subscribers of the 2024 panel"}
  ]
}}
```

`201` response (abridged):

```json
{
  "graph_id": "cgraph-9f2a1b7c44",
  "dataset_id": "ds-ab12cd34",
  "schema_version": "1.0.0",
  "revision": 0,
  "spec_fingerprint_sha256": "…64 hex…",
  "nodes": [
    {"node_id": "tenure", "resolved_column_type": "str",
     "derived_structure": {"parents": ["age"], "children": ["churn"],
       "ancestors": ["age"], "descendants": ["churn"],
       "is_collider": false,
       "on_directed_treatment_outcome_path": true}}
  ],
  "validation": {
    "ok": true, "error_count": 0, "warning_count": 0,
    "errors": [], "warnings": [],
    "derived": {"is_dag": true,
      "has_directed_treatment_outcome_path": true,
      "path_enumeration_bounded": false}
  },
  "validation_scope_note": "A passing validation establishes only that the graph is a well-formed directed acyclic graph…",
  "storage_note": "Causal graphs live in this server's memory alongside the dataset…"
}
```

## Example: rejected update (nothing mutates)

```json
{"error": {
  "code": "validation_error",
  "message": "The causal graph specification failed validation and was not stored.",
  "details": {
    "ok": false,
    "errors": [
      {"code": "directed_cycle", "severity": "error",
       "message": "The graph contains a directed cycle: tenure → churn → tenure.",
       "hint": "Remove one edge from the cycle. Causal DAGs are acyclic."}
    ],
    "warnings": [], "fix": "Resolve the listed errors and resubmit. Nothing was changed."
  }
}}
```

## Lifecycle notes

* Graphs live in the same in-memory, TTL-bounded store family as datasets and
  Study Cards; they expire with their dataset and are pruned when the dataset
  is evicted. Every payload carries this `storage_note`.
* The export envelope contains `export_kind: "splitscope-causal-graph"`,
  `causal_graph_schema_version`, the graph spec and an `origin` block. It never
  contains dataset rows. Import re-validates everything server-side; there is
  no pickle and no executable definition.
* `PUT`/`DELETE` were added to the CORS `allow_methods` list (previously only
  `GET/POST/OPTIONS`) so the S8B editor can call these endpoints from the dev
  origin; the origin list itself is unchanged.
