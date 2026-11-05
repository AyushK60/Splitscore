# S8B test results

Every number below is from an executed command on the final S8B tree
(branch `v2-premium-visual-foundation`, Windows, project venv + Node 20).

## Commands and exact results

```bash
# Backend (unchanged by S8B; regression check)
cd backend
../.venv/Scripts/python.exe -m pytest -q
# 406 passed, 3 warnings in 11.79s

# Synthetic oracle
../.venv/Scripts/python.exe scripts/evaluate_synthetic.py
# 41 case(s), 41 passed, 0 failed, 0 error(s) | 61 check(s), 0 failed
# exit 0: all expectations matched

# Frontend typecheck / lint / unit / build
cd frontend
npm run typecheck      # clean (tsc -b + tsconfig.app.json --noEmit)
npm run lint           # clean, --max-warnings 0
npm test               # 13 files, 136 passed (104 S7 baseline + 32 new)
npm run build          # clean; only the pre-existing >500 kB main-chunk advisory
                       # (the Causal Lab is a separate 232 kB lazy chunk)

# Browser journeys — production build served by the real FastAPI backend
export PATH="/e/Splitscore V2/.venv/Scripts:$PATH"
SPLITSCOPE_E2E_PORT=8197 npx playwright test
# 25 passed (49.7s)  — 22 existing journeys + 3 new S8B journeys
```

## New frontend unit tests (32)

**`tests/CausalLabState.test.ts` (17)** — pure reducer/adapter contracts:
payload→draft round-trip with layout intact; dirty/clean transitions around
save; `toSpec` matching the S8A body contract; self-loop/duplicate-edge/
duplicate-node refusal without mutation; node-deletion cascade (edges +
analysis scope); stable directional edge keys; schema-valid unique id
slugification; undo/redo ordering; saved-vs-draft separation; auto-position
adapters; issue indexing; and all three teaching examples satisfying the S8A
schema (unique ids, defined endpoints, synthetic labelling).

**`tests/CausalLabView.test.tsx` (15)** — view integration with the API
boundary mocked at the documented S8A shapes and React Flow stubbed: first-graph
load and restore; create via POST with the exact spec contract; hypothetical
variable; keyboard-method edge creation reaching the saved spec; scope setting;
assumption registry vocabulary (no "verified" option) and persistence in the
spec; 422 rejection showing the backend's structured errors while preserving
the draft; validate/export/import flows; 410 expiry message; two-step delete
confirmation; Escape clearing the inspector; undo.

## New Playwright journeys (3, real backend, no mocks)

`e2e/s8-causal-lab.spec.ts`:

1. **Authoring loop** — dataset selection → Causal Lab → labelled teaching
   example → new graph → three observed variables → two directed edges via the
   keyboard-accessible connect select → treatment/outcome scope → graph name +
   assumption record → Save (revision appears) → Validate ("Structurally valid
   DAG") → node inspector with backend-derived facts → drag a node, save,
   leave and re-enter the route → graph, edges and the dragged graph-space
   position restored → Export download with the backend's filename.
2. **Invalid structure** — draw customer_id → tenure_months → churned →
   customer_id; the backend returns 422; the alert names the directed cycle;
   the draft keeps 3 nodes/3 edges with Save re-enabled; the cycle is broken by
   deleting a node through the confirm flow (cascading edges); the retry saves.
   The intentional 422 is registered through the fixtures' `allowFailure`.
3. **Responsive** — 768 px and 390 px: inspector overlays instead of squeezing
   the canvas, no horizontal overflow at 390 px, panel toggle hides/shows the
   rail, controls remain reachable.

Screenshots captured by journey 1 and 3 are listed in
`docs/S8B_VISUAL_VERIFICATION.md`.

## Regression verification

* Existing 22 Playwright journeys: **all pass**, including the S6 nav-order
  contract test, which was updated for the intended new stage order (Causal
  Lab inserted as step 7; Compare becomes 8) — an intentional product change,
  not a concealment.
* Backend 406 and oracle 61 checks: unchanged from the S8A baseline.
* No existing frontend unit test was modified.

## Not run / environmental notes

* Firefox/WebKit: not run (Chromium-only project convention, unchanged).
* GitHub-hosted CI: not run (no remote authorized).
* Port 8123 remained occupied by an unrelated process (S7 note); 8197 was used.
* The venv on `PATH` is required because Playwright starts `python -m app.main`.
