# S9B — Handoff

**Status:** COMPLETE. Premium Causal Effect Estimation Studio shipped on
`v2-premium-visual-foundation`; all verification gates pass. S9C (sensitivity,
subgroup/CATE analysis) has not been started.

## What a successor inherits

- A working `#/estimation` stage (step 8) that consumes the audited S9A engine
  and never estimates implicitly.
- A reusable figure system (`figureFrame.tsx`): `FigureFrame`,
  `useMeasuredWidth`, `LegendItem` and the export helpers. New analytical views
  should use it rather than inventing another chart shell, so provenance,
  export and accessibility stay uniform.
- A tested model layer (`estimationModel.ts`) for request construction,
  signatures and staleness. Any new request field must be added there **and** to
  the reproducibility comparison, otherwise a stale result can look current.
- An established honesty vocabulary in the UI: failed ≠ zero, unavailable
  interval ≠ invented bounds, balance ≠ exchangeability, agreement ≠ validity.
  Keep it.

## Files

New backend:

- `backend/app/synthetic/generators.py` — `build_causal_effect()` and demo entry.
- `datasets/causal_effect.csv`, `datasets/manifest.json` — 1,200-row demo.
- `backend/app/causal/estimation/diagnostics.py` — fixed 20-bin histogram.
- `backend/tests/test_s9b_diagnostics.py`; updates to `test_demos.py` and
  `test_api.py`.

New frontend:

- `src/estimation/` — `EstimationView`, five views, `estimationModel`,
  `estimationExport`, `downloadRun`, `figureFrame`, `format`.
- `src/styles/s9.css`.
- `tests/estimationFixtures.ts` and the eight S9B test files (60 tests).
- `e2e/s9b-estimation.spec.ts` (journeys A–D).

Modified frontend:

- `src/api/types.ts`, `src/api/client.ts` — estimation contracts/`estimationApi`.
- `src/lib/router.ts`, `src/main.tsx` — route, nav step, labels, lazy chunk.
- `src/views/LandingView.tsx`, `src/views/OverviewView.tsx` — evidence/copy
  corrections (seven demos, estimation now exists).
- `src/styles/app.css` — nav step badges hidden ≤1040 px (nine stages no longer
  fit beside the wordmark); active stage centred in the scrollable nav.

Docs: this file, `S9B_IMPLEMENTATION.md`, `S9B_VISUAL_DESIGN.md`,
`S9B_API_INTEGRATION.md`, `S9B_VERIFICATION.md`; `STATUS.md` updated.

## Decisions worth not re-litigating

- **Hand-built SVG, no chart dependency.** Keeps the bundle unchanged and gives
  exact control over scientific marks and exports.
- **Readiness probe is separate from the run.** `validate` computes the cohort
  and gate but stores nothing; only an explicit run stores a result. Do not make
  the panel auto-run.
- **Staleness is deterministic and named.** Layout-only graph edits do not
  invalidate results because layout is excluded from the scientific
  fingerprint. An empty seed means "server-drawn", so it is not compared; a
  specified seed that differs from the resolved seed is stale.
- **Comparison is reported, never resolved.** There is deliberately no "winner"
  or pooled estimate.
- **One bounded backend addition.** The 20-bin histogram is counts/shares only.
  Quantiles alone were insufficient for an honest distribution figure; row-level
  scores remain unexposed.
- **No S7 dossier change.** A causal-effect report section needs a schema
  decision in the report backend, so the studio exports figure/run artifacts
  instead of forcing an incompatible dossier mutation.

## Known gaps / natural next steps

1. **S9C:** ATT, CATE/subgroup analysis, sensitivity analysis (E-value or
   negative-control style), matching/weighting alternatives. The engine, not the
   studio, must define these; the studio's job would be another view set with the
   same fail-honest rules.
2. **Cohort selection:** an assignment/partition picker needs a route that lists
   this session's assignments; today the field is optional and defaults to all
   rows.
3. **Report integration:** add a causal-estimation section to the S7 dossier
   behind a versioned schema change, reusing `estimationExport` values.
4. **Persistent history:** runs are bounded in-memory (≈1 hour). A project store
   would need a real persistence decision.
5. **Figure interaction:** no zoom/brush; static SVG is deliberate.

## Environment / runbook

- Start backend: `cd backend && ..\.venv\Scripts\python -m app.main` (port 8000
  by default); or `npm run dev` in `frontend/` for the UI.
- Estimation demo: open the `causal_effect` dataset, go to **Causal Lab** →
  create/save a graph (the studio offers **Create the demonstration DAG**), then
  **Effect estimation** → **Run comparison**.
- Playwright needs the venv first on `PATH` because its webServer runs bare
  `python`:
  `PATH="/e/Splitscore V2/.venv/Scripts:$PATH" npx playwright test`.
- Full gate: backend `pytest`; `npm run typecheck`, `npm run lint`, `npm test`,
  `npm run build`, Playwright.

## Handoff checklist

- [x] No fabricated estimates/intervals; failed methods shown as failed.
- [x] Readiness gate, explicit run, stale results named.
- [x] Real-backend journeys A–D; all earlier journeys still pass.
- [x] 536 backend tests, 205 frontend unit tests, 33 browser journeys.
- [x] Synthetic oracle 41/41 (61 checks).
- [x] Docs and STATUS updated.
- [ ] S9C — intentionally not started.
