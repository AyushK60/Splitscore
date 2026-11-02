# S4 visual QA — real-browser evidence

Driven with Playwright/Chromium against the production build served by the
local backend. Scripts live in `frontend/scripts/` and exit non-zero on any
failed check, so the evidence is re-runnable, not anecdotal.

## What was run

| Script | Checks | Result |
| --- | --- | --- |
| `capture-s4-landing.mjs` | before/after landing captures at 1440/390, overflow, console cleanliness | pass |
| `capture-s4-explorer.mjs` | 20 behavioural checks over the explorer (see below) | **all passed** |
| `capture-s4-suite.mjs` | 13 checks across the six plot modes | **all passed** |
| `capture-s4-exports.mjs` | 15 checks inspecting real downloaded files | **all passed** |
| `s4-performance.mjs` | timing probe at 3k and 10k rows | within bounds |
| `e2e/s4-explorer.spec.ts` (+ 5 pre-existing journeys) | 11 tests | **11 passed** |

## Explorer behaviour checks (selection from the run log)

- demo loads through the UI; explorer route renders the PC canvas with real
  column names (`month_index, tenure_months, monthly_spend, support_tickets,
  avg_session_minutes`); sampling caption states "240 of 240 rows drawn (all
  rows)"; population readout shows the full 240.
- a real pointer drag on the first axis commits a brush: population readout
  switches to "80 selected of 240", the row inspector shows
  "80 of 240 rows selected", the predicate is echoed
  (`month_index ∈ [2.500, 4.250]`), 80 lines highlight in copper, the brush
  rectangle is visible on the axis.
- a second brush accumulates (`tenure_months ∈ [13.70, 28.20]` → 24 selected);
  "Clear selection" restores "240 rows (no filters)" with zero highlighted
  lines.
- accessible axis reordering moves an axis (order asserted before/after);
  focus mode collapses the inspector.
- **no console errors** in any capture.

## Suite checks (linked views)

- a PC brush survives tab switches: the distribution view shows the exact
  "active selection (80 rows, same bins)" overlay with its own copper bars;
  missingness shows the selected-scope percentages next to the whole-dataset
  numbers; returning to PC keeps the selection.
- correlation cells render with coefficients; clicking a cell opens the
  scatter of exactly that pair; a scatter box-brush updates the same shared
  count and the inspector agrees (26 of 240).
- the scatter matrix renders 6 panels for 4 variables; a panel click opens
  the focus scatter.
- distributions: group overlay lists groups with sizes
  ("train — 179 rows · test — 61 rows").

## Screenshots

`docs/screenshots/s4/`:

- `landing-before/`, `landing-after/` — 1440×900 and 390×844 full-page pairs.
- `explorer-overview.png`, `explorer-brushed.png`, `explorer-multi-brush.png`,
  `explorer-focus.png` — the S4-B canvas states at 1440×900.
- `suite-correlation.png`, `suite-distribution.png`, `suite-missingness.png`,
  `suite-scatter-brushed.png`, `suite-scatter-matrix.png` — S4-C modes.
- `explorer-mobile-390.png`, `explorer-tablet-1024.png` — responsive stacking,
  horizontal overflow 0 px at both sizes (also asserted by an E2E journey).
- `exports/sample-parallel-coordinates.{svg,json}` — real export outputs.

## Defects found by the QA loop and fixed

1. **ResizeObserver feedback loop** — the observer wrapped a container that
   included the reorder bar, so the SVG grew every frame (460 → 5777 px) and
   brush drags landed off-viewport. Fixed by observing a plot-only wrapper.
2. **Axis rescaling under filters** — axes originally scaled to the filtered
   population, so committing a brush moved its own bounds off the rails.
   Fixed: axis scales always cover the full population (backend `scale`
   contract documented in `routes_explore.py`).
3. **Impure state commit** — the brush commit ran inside a `setDrag` updater;
   moved to a ref-based commit on pointer-up.
4. **Colour variable rendered as an axis** — a boolean colour column appeared
   as a "constant" rail; fixed by gating axes on `scale.numeric`.
5. **Copper used for both group colours and selection** — group palette
   redefined to exclude copper.
6. **E2E viewport issue** — the default 1280×720 viewport put the scatter's
   lower half below the fold where pointer events cannot start; the S4
   journey uses 1440×950 and documents why.
7. **"every 3th" caption** — ordinal helper added with a regression test.
