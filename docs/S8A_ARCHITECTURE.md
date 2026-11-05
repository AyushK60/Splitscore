# S8A architecture — causal intelligence foundation

**Status: implemented and verified on branch `v2-premium-visual-foundation`.**
S8A delivers the backend foundation for the interactive Causal Lab: a versioned
causal-graph domain model, a structural validation engine, an assumption
registry, dataset integration and a REST authoring API. No graphical editor
(S8B) and no identification/estimation (S8C) exists yet, and no route pretends
otherwise.

## 1. Domain modules

Everything new lives in one dedicated package, mirroring the layout of
`app/research/`:

| Module | Responsibility |
|---|---|
| `backend/app/causal/schema.py` | Pydantic specification models (`CausalGraphSpec`, `CausalNode`, `CausalEdge`, `AnalysisScope`, `AssumptionRecord`), the schema version constant, size limits, canonical JSON and the content-addressed graph fingerprint. |
| `backend/app/causal/validation.py` | The validation engine: blocking errors, non-blocking scientific warnings, and structure-derived properties (ancestors, descendants, colliders, directed-path status). Iterative cycle detection; bounded path enumeration (`MAX_ENUMERATED_PATHS = 1000`) with explicit disclosure when the bound is reached. |
| `backend/app/causal/registry.py` | `CausalGraphRegistry`: bounded, thread-safe in-memory store of graph records with dataset ownership, revision counting, and the API read models (`graph_payload`, `graph_summary`). |
| `backend/app/causal/io.py` | The versioned JSON export/import envelope (`build_export`, `parse_export`). Server-side validation only; no pickle, no executable definitions. |

Integration points changed outside the package (deliberately minimal):

* `app/api/routes_causal.py` — the REST endpoints.
* `app/api/deps.py` — `AppContext` gains `causal_graphs: CausalGraphRegistry`.
* `app/main.py` — the causal router is included; CORS `allow_methods` gains
  `PUT` and `DELETE`, which the existing method list (`GET/POST/OPTIONS`) did
  not carry and which S8B's editor requires.

NetworkX is **not** used. The project does not depend on it, and the graph
algorithms S8A needs (cycle detection, reachability, bounded path enumeration)
are small, fully deterministic and easier to test as plain Python than as a
dependency boundary. S8C's d-separation can adopt a library later if its
algorithms justify one; the validation engine interface will not change.

## 2. Boundaries the design preserves

SplitScope's architectural separation is extended, not merged:

1. **Dataset integrity / leakage auditing** (`app/audit`) — facts computed from
   data. Never consulted when judging an edge.
2. **Association / predictive modelling** (`app/models`) — statistical fits.
   No causal reading is attached to them here or anywhere else.
3. **User-defined causal assumptions** (`AssumptionRecord`, `spec.assumptions`)
   — claims, recorded with an explicit, user-chosen status. There is no
   `verified` state because the application cannot verify them.
4. **Graph structure and validity** (`app/causal.validation`) — properties that
   follow from the drawn edges alone.
5. **Causal identification** — S8C. No endpoint, no partial implementation, no
   placeholder output.
6. **Causal effect estimation** — later. Explicitly out of scope (see the
   scientific contract).

The module enforces the distinction mechanically: `CausalNode.kind` is the
user's *conceptual annotation* ("I hypothesise this is a mediator"), while
`validation.derived["nodes"][id]` holds what the graph itself supports. When
the two disagree the engine emits a `declared_role_unsupported` warning and
reclassifies nothing.

## 3. Dataset integration and lifecycle

* The dataset workflow remains the single source of truth for columns. Node
  `column` references are validated against `dataset.columns` at every create,
  update and import; a reference that does not resolve is blocking
  (`unknown_column`).
* A graph belongs to one dataset. Every read and write goes through
  `registry.get(dataset_id, graph_id)`, which rejects a valid graph id under
  the wrong dataset with a typed 404 — cross-dataset ownership is impossible.
* Graph lifetime follows dataset lifetime. The dataset store expires entries
  after an hour and evicts least-recently-used ones; the causal route resolves
  the dataset through the store first and prunes graphs whose dataset is no
  longer live (`prune_for_datasets`), so a graph can never outlive its data
  and quietly become orphaned metadata — the same rule Study Cards follow.
* No new persistence is introduced. Durable keeping of a graph is the versioned
  JSON export (`GET .../export`) and its server-validated re-import
  (`POST .../import`), which carries structure, assumptions and layout only —
  never dataset rows. Import always creates a *new* graph bound to the
  receiving dataset and fails with `unknown_column` when the file is imported
  against a dataset whose columns do not match.

## 4. Interfaces reserved for S8B (visual editor)

S8B can be built against these contracts without backend changes:

* **Full round-trip payloads.** `graph_payload` returns nodes (with optional
  `layout` coordinates), edges, analysis scope, assumptions, validation and
  derived structure in one read model. The editor renders from it and writes
  back through `PUT`.
* **Positions are display state.** `layout` is excluded from
  `canonical_scientific_json`, so dragging a node never changes the graph's
  scientific fingerprint or revision semantics; the S8B canvas can persist
  positions without fabricating scientific changes.
* **Invalid updates never lose work.** An update that fails validation returns
  422 with the structured error list; the stored graph is untouched, so the
  editor can keep the user's working state client-side and re-submit a fix.
* **Warnings are typed.** Each warning carries a stable `code` the editor can
  surface per node/edge (`node_id`, `edge_index`, `assumption_id` fields are
  populated where applicable).
* **The scope object.** `AnalysisScope` is one treatment / one outcome by
  design; multiple exposures/outcomes later means extending that object, not
  reshaping the specification.

## 5. Interfaces reserved for S8C (identification)

`validation.derived` already supplies the raw material identification needs:
per-node parents/children/ancestors/descendants, collider flags, and the
treatment→outcome directed-path enumeration (with `path_enumeration_bounded`
disclosure). Backdoor reasoning and d-separation will consume the same
`CausalGraphSpec` after an independent structural validation — no new data
model is expected. The `validation_scope_note` carried in every payload is the
contract S8C must keep: a valid graph is a well-formed DAG, nothing more.
