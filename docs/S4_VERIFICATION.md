# S4 verification — Scientific Visual Explorer

Run 2026-11-03 against the production build (`python -m app.main` serving
`frontend/dist`) on branch `v2-premium-visual-foundation`, Windows, Python
3.13 venv, Node 24. Every number below is from an actual run of the final
code; nothing is projected.

**Verdict: PASS** against the S4 acceptance gate, with the boundaries listed
at the end.

## 1. Gates

| Gate | Command | Result |
| --- | --- | --- |
| Backend tests (incl. 40 new explore tests) | `cd backend && ../.venv/Scripts/python -m pytest -q` | **292 passed** (252 baseline + 40) |
| Synthetic oracle harness (V1 preservation) | `python scripts/evaluate_synthetic.py` | **41 cases / 61 checks — 0 failed, exit 0** |
| Frontend typecheck | `cd frontend && npm run typecheck` | exit 0 |
| Frontend lint (zero warnings) | `cd frontend && npm run lint` | exit 0 |
| Frontend unit tests | `cd frontend && npm run test` | **82 passed** (8 files; 70 baseline + 12) |
| Production build | `cd frontend && npm run build` | exit 0 — 90.8 kB CSS / 391.5 kB JS |
| Playwright E2E (full suite) | `SPLITSCOPE_E2E_PORT=… npx playwright test` | **11 passed** (5 pre-existing + 1 S3 + 5 new S4) |
| Explorer behavioural capture | `node scripts/capture-s4-explorer.mjs` | 20/20 checks |
| Suite behavioural capture | `node scripts/capture-s4-suite.mjs` | 13/13 checks |
| Export inspection | `node scripts/capture-s4-exports.mjs` | 15/15 checks |

## 2. E2E journeys (new, `e2e/s4-explorer.spec.ts`)

Real backend, real browser, no mocks:

1. **Brush journey** — load demo → explorer → assert real axis names, honest
   sampling caption, full population; drag a brush → exact "80 selected of
   240"; row evidence resolves `row-0000NN` ids with the file's own values;
   brush rectangle and copper highlights present; Clear selection restores
   240 everywhere.
2. **Correlation → scatter** — Pearson/Spearman matrix with coefficient
   cells and ±1 legend; clicking a cell opens the scatter of that exact
   pair; a box brush there feeds the same shared selection the inspector
   shows.
3. **Linked filtering** — a PC brush overlays the distribution view ("active
   selection (80 rows, same bins)") and the missingness view (selected-scope
   percentages next to whole-dataset numbers); returning to PC keeps the
   selection — one engine across tabs.
4. **Exports** — SVG/PNG/JSON downloads inspected on disk: SVG contains
   polylines, the caption block with "Active selection" and the sha256; the
   manifest has a 64-hex fingerprint, the predicate list and
   `raw_rows_embedded: false`; PNG > 10 KB.
5. **V1/S3 workflows intact** — after using the explorer, the Study Card
   opens, the Data dictionary tab shows the computed columns, the original
   audit runs from Results, and the explorer returns without stale state.
6. **Responsive** — 390×844: stacked layout, horizontal overflow ≤ 1 px.

## 3. Numerical oracles (detail in `S4_NUMERICAL_VALIDATION.md`)

Pearson and Spearman match scipy to 1e-12 (including pairwise-complete
cases and ties); ranks are hand-verified; histogram counts and Tukey box
statistics are hand-calculated; selection id sets are hand-listed; the demo
dataset's correlation matrix is cross-checked against an independent
pandas+scipy read of the committed CSV. Undefined correlations remain
`null` with warning codes — never zero.

## 4. Performance (Chromium, dev machine — indicative, not a benchmark)

| Measurement | 3,000 rows | 10,000 rows (server cap) |
| --- | --- | --- |
| Upload + admit | 58 ms | 105 ms |
| First parallel-coordinates render | 325 ms | 835 ms |
| Brush → exact count round trip | 430 ms | 445 ms |
| Correlation matrix | 643 ms | 1,377 ms |
| Missingness view | 223 ms | 257 ms |
| SVG export | 164 ms | 136 ms |

At 10k rows the canvas draws 1,112 of 10,000 rows (every 9th row) and says
so in its caption. DOM cost stays bounded because unselected lines collapse
into one path per colour group.

## 5. Acceptance-gate mapping

- **Visual**: landing refined (S4-A) with before/after evidence; explorer
  reads as the same product as the Study workspace (shared tokens); large
  canvas + focus mode; responsive at 390/1024/1440. ✔
- **Functional**: PC (reorder/brush/multi-brush/reset/counts/legend/sampling
  caption), correlation heatmap, missingness view, scatter + matrix,
  distributions, ≥3 views sharing real selection state (PC, scatter,
  distribution, missingness, inspector), row evidence resolving correct ids,
  figure exports. ✔
- **Scientific**: statistics reconcile with independent oracles; denominators
  and missingness are honest; undefined stays undefined; samples are
  reproducible; no causal claims anywhere (correlation view carries the
  caveat); nothing fabricated. ✔
- **Engineering**: all suites pass; routing intact (new `#/explore` deep
  link); Study/provenance/audit/reporting unchanged; no new persistence of
  raw data; git history checkpointed at each sub-stage. ✔

## 6. Known limitations (honest scope)

- Violin plots and high-dimensional embeddings not implemented (see
  `S4_VISUAL_ARCHITECTURE.md`).
- Scatter-matrix panels colour by the group variable only at the overview
  level; per-panel legends are simplified (counts shown per panel).
- The missingness display matrix draws the whole dataset up to 400 grid
  rows; beyond that it is a documented render sample (aggregates stay exact).
- Export PNGs rasterise at 2× screen DPI; print-DPI controls are later F22.
- Performance numbers are one dev machine's timings, not a benchmark.
