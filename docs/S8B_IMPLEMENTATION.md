# S8B implementation — the Causal Lab

**Status: COMPLETE.** The Causal Lab is a functioning interactive causal DAG
editor built directly on the S8A backend. This document describes what shipped,
the frontend architecture, and the API integration contract.

## 1. What shipped

A dedicated workspace at route `#/causal` (nav stage 7, shown once a dataset is
loaded, lazy-loaded code chunk):

* **One dominant graph canvas** (`@xyflow/react` v12): paper-toned canvas with
  a dot grid, node cards with label/column/kind chips, directed edges with
  closed arrowheads, zoom/pan, fit-view, minimap above 10 nodes.
* **Left rail (collapsible)**: dataset identity, the dataset's saved graphs
  (with validation badges), New/Delete graph, a searchable observed-variable
  palette (columns already in the graph are marked), and an Add hypothetical
  variable action.
* **Right contextual inspector** — opens only when something is selected:
  * *Node*: label, conceptual role (backend vocabulary), description,
    set-as-treatment/outcome, the keyboard edge-creation select, backend-derived
    structural facts (parents/children/ancestors/descendants/collider/on-path,
    labelled "derived from the drawn edges only"), and confirm-gated delete.
  * *Edge*: source→target, rationale, optional reference, confirm-gated remove.
    The panel states that the edge records an assumption and carries no
    strength or confidence value.
  * *Graph settings*: name, description, the one-treatment/one-outcome scope,
    and the assumption registry (all nine S8A categories, the four backend
    statuses — no "verified" state exists in the UI).
  * *Validation*: blocking errors and scientific warnings with hints; selecting
    an issue focuses the affected node.
* **Toolbar**: Save (dirty indicator), Validate, status chip
  (`Not validated yet` / `N blocking errors` / `Structurally valid DAG · N
  warnings`), Undo/Redo (draft-level, Ctrl+Z / Ctrl+Shift+Z), Fit view,
  Export, Import, Graph settings, Clear selection (Esc).
* **Empty state**: the five-step workflow and three synthetic teaching examples
  (chain, fork, collider), explicitly labelled as teaching structures whose
  edges are assumed, not learned from data.
* **Keyboard support**: all authoring via the rail and inspector is
  keyboard-operable; Delete/Backspace removes the selected node/edge; Escape
  clears selection; Ctrl+Z/Y undo/redo. React Flow's own delete machinery is
  disabled — deletion runs through the reducer with its cascade semantics.
* **Responsive**: rails overlay as drawers at ≤1024 px (inspector) and
  ≤760 px (rail); toolbar wraps; no horizontal overflow at 390 px; reduced
  motion respected.

## 2. Frontend architecture

```
frontend/src/causal/
  CausalLabState.ts    pure reducer: draft / saved / validation, undo history
  adapter.ts           draft ↔ React Flow view models; teaching examples
  CausalCanvas.tsx     React Flow wrapper; selection owned by the app
  CausalInspector.tsx  node / edge / graph / validation panels
  VariableRail.tsx     dataset, graph list, variable palette
  CausalLabView.tsx    composition, server flows, toolbar, keyboard shortcuts
frontend/src/styles/s8.css   visual layer (S7 tokens, copper selection)
```

Load-bearing state distinctions (per the brief):

* **draft** — the user's working copy. A failed save or validation never
  mutates it; a 422 keeps every edit and shows the backend's structured errors.
* **saved** — the last server-confirmed revision. "Dirty" is a JSON comparison
  against it; the Save button shows a copper dot and is disabled when clean.
* **validation** — the backend's verdict, whether from a successful
  save/validate or a rejected one. Never computed in the browser.
* **Undo/redo** operates on the draft only; saving is not an undoable edit.

Selection is owned by the application rather than React Flow: RF's internal
selection state re-fires empty-selection events on every store update, which
cleared non-canvas selections and could loop against a controlled draft
(React error #185). Clicks route through `onNodeClick` / `onEdgeClick` /
`onPaneClick`; RF's `elementsSelectable` and `deleteKeyCode` are disabled and
deletion is handled by the view with the reducer's cascade semantics.

Edge clicks need a hit area: each custom edge renders an invisible
22 px-wide interaction path under the visible stroke.

Layout coordinates live in `node.layout` and are display state — the S8A
scientific fingerprint intentionally excludes them, and the journey proves
positions round-trip through save and remount.

## 3. API integration

All eight S8A routes are exercised through `causalApi` in
`frontend/src/api/client.ts`, with payload/response types in
`frontend/src/api/types.ts` mirroring the S8A contract:

| UI action | Endpoint |
|---|---|
| Open the lab / pick a graph | `GET /api/datasets/{id}/causal-graphs`, `GET .../{gid}` |
| New graph → first save | `POST /api/datasets/{id}/causal-graphs` |
| Save changes | `PUT /api/datasets/{id}/causal-graphs/{gid}` |
| Validate | `PUT` first when dirty, then `GET .../{gid}/validation` |
| Export | `GET .../{gid}/export` (Content-Disposition download) |
| Import | `POST /api/datasets/{id}/causal-graphs/import` |
| Delete current | `DELETE /api/datasets/{id}/causal-graphs/{gid}` |

* No second graph storage exists anywhere in the frontend; the draft is
  transient working state and the S8A registry remains authoritative.
* A 422 from create/update is parsed into a `CausalValidation` from the error
  envelope's details and rendered like any validation result, with the alert
  "The backend refused this graph. Your draft is unchanged."
* A 410 (dataset expired/evicted) surfaces the backend's actionable message;
  re-entering the lab after reloading data recovers cleanly.
* Import reads a user-selected JSON file (FileReader fallback for jsdom),
  posts the envelope, and loads the returned *new* graph.
* Autosave is deliberately not implemented: explicit Save with a dirty
  indicator, exactly as the brief prefers.

## 4. Scientific boundaries preserved

No causal discovery, identification, d-separation beyond S8A's structural
derivations, effect estimation, or any numeric causal output exists in the
frontend. The scope note under the canvas states: *a structurally valid DAG is
not a scientifically justified causal model*. Node styling distinguishes
declarations (treatment/outcome tags, user-chosen kind chip) from derived
facts, which are only shown in the inspector with their provenance note.
Conceptual annotations never restyle a node as a "proven confounder".

## 5. Defects found and fixed during the visual pass

| Defect | Fix |
|---|---|
| React #185 update loop from RF selection events vs. controlled draft | App-owned selection; guard removed entirely with RF selection disabled |
| Edges invisible (no handles on the custom node) | Left/right `Handle` components, subtly styled |
| Canvas measured 0 px tall — RF needs a real container height | `.clab__canvas` absolute-positioned inside the stage |
| A fit issued for the first node zoomed to maxZoom, stranding later nodes | Debounced refit (120 ms) whenever the node count settles, with `minZoom: 0.55` so small graphs stay readable |
| Warnings painted edges error-red via a CSS selector that also hit the interaction path | Errors-only canvas marking; selector restricted to the visible stroke |
| **Pre-existing (all views):** at ≤760 px the context band stretched to ~860 px because `.app-crumb__next`'s `flex: 0 1 860px` basis applies to *height* once the crumb goes column | `.app-context .app-crumb__next { flex: 0 1 auto }` in the ≤760 px media query (app.css) — benefits every workspace |

## 6. Files added / modified

* Added: `src/causal/{CausalLabState,adapter,CausalCanvas,CausalInspector,VariableRail,CausalLabView}` (6 files), `src/styles/s8.css`,
  `tests/CausalLabState.test.ts`, `tests/CausalLabView.test.tsx`,
  `e2e/s8-causal-lab.spec.ts`.
* Modified: `src/api/types.ts` (S8A contract types), `src/api/client.ts`
  (`causalApi`), `src/lib/router.ts` (`causal` view), `src/main.tsx` (lazy
  route, nav step 7, breadcrumb guidance), `src/styles/app.css` (pre-existing
  mobile context-band fix), `package.json` + lockfile (`@xyflow/react`),
  `e2e/s6-ui-repairs.spec.ts` (pinned nav order gains Causal Lab at step 7).
