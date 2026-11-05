# S8A handoff

**Status: COMPLETE for the S8A exit gate.**
**Branch:** `v2-premium-visual-foundation` · **Starting HEAD:** `e100d53` · **Implementation commit:** see the Git line recorded at the end of this file and in `S8A_VERIFICATION.md`.

S8A delivers the causal-graph backend foundation. S0–S7 behaviour, contracts
and visual identity are preserved; the full backend suite passes (406 tests,
up from 373) and the synthetic oracle is unchanged (41/41, 61/61).

## What shipped

* **`backend/app/causal/`** — new domain package:
  * `schema.py` — versioned Pydantic specification (`CausalGraphSpec`, nodes,
    edges, `AnalysisScope`, `AssumptionRecord`), size limits, canonical JSON
    and the content-addressed `spec_fingerprint_sha256` (layout excluded).
  * `validation.py` — blocking structural errors (cycles, self-loops,
    duplicates, dangling endpoints, unknown columns, invalid scope, wrong
    schema version) plus 12 non-blocking scientific warnings, and
    structure-derived properties (ancestors/descendants/colliders/on-path)
    computed from the drawn edges only. Iterative cycle detection; bounded
    path enumeration with disclosure.
  * `registry.py` — bounded, thread-safe registry; dataset ownership on every
    operation; validation-before-mutation; API read models.
  * `io.py` — versioned JSON export/import envelope, server-validated,
    marker-checked, no executable content.
* **`backend/app/api/routes_causal.py`** — 8 REST endpoints: create, list,
  read, update, delete, validate, export, import, all dataset-scoped with
  structured errors and lifecycle pruning of orphaned graphs.
* **Wiring:** `AppContext.causal_graphs`; router included in `app.main`;
  CORS `allow_methods` extended with `PUT`/`DELETE` (S8B needs them; origins
  unchanged).
* **Tests:** `backend/tests/test_causal_graphs.py` — 33 tests through the real
  HTTP path covering all 20 scenarios the S8A brief required.
* **Docs:** `S8A_ARCHITECTURE.md`, `S8A_SCIENTIFIC_CONTRACT.md`,
  `S8A_API_CONTRACT.md`, `S8A_VERIFICATION.md`, this handoff; one tracker line
  added to `STATUS.md`'s header list.

## Not done (by design)

* No visual editor, canvas, node inspector or route to it (S8B).
* No identification, backdoor reasoning, d-separation, adjustment sets or any
  effect estimation; no endpoint stubs that could fake them (S8C).
* No new navigation entry, no landing-page copy change, no visual changes of
  any kind.
* No persistence beyond the existing in-memory TTL store; durability is the
  export/import contract only.
* NetworkX was deliberately not added (not a dependency; algorithms small and
  deterministic). S8C may revisit.

## Remaining limitations

* A stored graph's `unknown_column` safety relies on dataset immutability in
  the store; the `dataset_schema_drift` warning covers the re-import /
  fingerprint-change case.
* One treatment / one outcome per analysis scope (object is designed to widen).
* Backend only: the OpenAPI schema documents the routes, but no frontend
  contract types exist yet — S8B adds them.

## S8B readiness

Ready. The editor can be built entirely against `graph_payload` (nodes with
`layout` + derived structure, edges, scope, assumptions, validation) and
`PUT` create/update with structured 422 error lists that preserve stored
state. Positions are excluded from the scientific fingerprint, so layout
editing cannot masquerade as scientific change.

## S8C readiness

Ready. `validation.derived` already exposes parents/children/ancestors/
descendants, collider flags and bounded treatment→outcome path enumeration
with an explicit completeness flag. S8C's d-separation and backdoor logic can
consume the same `CausalGraphSpec` after `validate_spec` — no data-model
change expected.

## Verification digest

| Suite | Result |
|---|---|
| `backend` full pytest | **406 passed**, 3 pre-existing warnings |
| `tests/test_causal_graphs.py` | **33 passed** |
| `scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks, exit 0** |

Frontend suites not run — no frontend file changed (rationale in
`S8A_VERIFICATION.md`).

## Git

* Branch: `v2-premium-visual-foundation`
* Implementation commit: the commit that adds the S8A files, including this
  handoff (see `git log` for its hash; the final S8A response records it).
* Pre-existing untracked material (`docs/screenshots/s3/_preview/`,
  `docs/screenshots/s5/_preview/`, `import requests.txt`,
  `scripts/_patch_s3_hero.py`, stash@{0}) was preserved and is not part of
  the commit.
