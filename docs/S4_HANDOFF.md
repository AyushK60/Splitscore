# S4 handoff — Scientific Visual Explorer

## State

S4 delivered and verified: the landing colour refinement (S4-A), the Visual
Explorer foundation (S4-B), the scientific visualization suite with linked
selection (S4-C), and figure exports, tests, E2E and documentation (S4-D).
S5 has **not** been started.

Result details and exact command output live in `docs/S4_VERIFICATION.md`.

## Where things are

```
backend/app/explore/{sampling,stats,schema,selection,aggregates}.py
                  bounded, deterministic exploration services
backend/app/api/routes_explore.py
                  /api/datasets/{id}/explore/{schema,series,selection,rows,
                                             correlation,distribution,missingness}
backend/tests/test_explore.py          40 tests (scipy oracles + hand fixtures)
frontend/src/explore/ExploreState.tsx  THE shared selection engine
frontend/src/explore/figureExport.ts   SVG/PNG/JSON figure machinery
frontend/src/components/explore/*.tsx  ParallelCoordinates, CorrelationHeatmap,
                                       ScatterFocus, ScatterMatrix, Distributions,
                                       MissingnessView, RowEvidence, FigureExport
frontend/src/views/ExploreView.tsx     #/explore workspace
frontend/src/styles/explore.css        workspace styling (.rs token scope)
frontend/e2e/s4-explorer.spec.ts       5 browser journeys
frontend/scripts/{capture-s4-*,s4-performance}.mjs   re-runnable evidence
docs/S4_*.md, docs/screenshots/s4/
```

## Decisions a future stage must respect

1. **One selection engine.** `ExploreState` owns selection; charts call
   `applyPredicates` and never keep private filters. S5's similarity
   explorer must read/write this same engine, not build a second one.
2. **Server-side aggregates.** The frontend never recomputes a statistic the
   backend produced. New S5+ views should follow the `explore/` pattern:
   typed request models, bounds, `ValidationFailure` on bad input,
   deterministic methods, honest denominators.
3. **Immutable row ids are the join key.** `Dataset.row_ids`
   (`row-000001…`) connect charts, the inspector and audit evidence.
4. **Axis scales cover the full population; render samples are systematic
   grids** and every payload carries the sampling description verbatim.
5. **Copper = user selection; teal = workbench; group hues exclude copper.**
6. **Exports are live-state, provenance-carrying, and embed no raw rows**
   (`privacy.raw_rows_embedded: false`).

## Known gaps (next stages)

- Violin plots, faceted distributions, high-dimensional projections (optional
  F08 items) are not built.
- Time-axis distributions: timestamps render as categorical/text today; a
  proper time distribution view is future work.
- Scatter-matrix panel colouring is simplified (no per-panel mini legends).
- F22 print-DPI controls, table exports, dossier integration: open.
- The six bundled demos cover multivariate + train/test scenarios; a
  dedicated *structured-missingness* demo fixture would strengthen the
  missingness view demonstration (the view works on uploads with empty
  cells; none of the six demos has many).

## Recommended S5 entry point

1. Read `docs/S4_LINKED_SELECTION.md` and `backend/app/explore/selection.py`
   — the similarity/integrity work should reuse `population_mask` so S5
   findings can be brushed from and into the same explorer views.
2. Bind audit evidence to selections: the row inspector already resolves
   ids; S5 can add "open the covering finding" deep links from inspector
   rows to `#/evidence`.
3. Add the structured-missingness demo fixture before building S5 views so
   demonstrations stay bundled and reproducible.

## Running it locally (Windows PowerShell)

```powershell
# from the repository root
cd backend
$env:SPLITSCOPE_PORT = "8000"
..\.venv\Scripts\python.exe -m app.main
# http://127.0.0.1:8000/            landing
# http://127.0.0.1:8000/#/explore   Visual Explorer (load a demo first)
```

```powershell
cd frontend
npm run test        # component/unit tests (82)
npm run test:e2e    # browser journeys (11; rebuilds dist first)
node scripts/capture-s4-explorer.mjs   # behavioural capture (needs backend up)
node scripts/s4-performance.mjs        # timing probe
```

All verification commands and their outputs: `docs/S4_VERIFICATION.md`.
