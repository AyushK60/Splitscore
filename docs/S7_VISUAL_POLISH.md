# S7 visual polish

S7 keeps the warm paper / ink / teal / copper system. It changes hierarchy,
mark visibility and the amount of permanent vertical space, not the product's
identity.

## Compact workspace chrome

Before S7 the brand, tagline and nine stage controls occupied two persistent
rows, and the breadcrumb panel was part of the same sticky block.

Now:

* `.app-topbar__primary` is one 58 px row (52 px at ≤760 px): brand and primary
  stages share one band. The tagline is present at wide widths and hidden below
  1500 px; it is not allowed to wrap into a second row.
* The breadcrumb and next-action guidance moved into `.app-context`, a pale
  paper band *outside* the sticky topbar. It scrolls away, so orientation is
  available at the top of a page without permanently consuming chart height.
* Stage buttons keep an explicit transparent background rather than inheriting
  the global light hover surface; the active stage uses celadon, hover uses a
  readable pale rule, disabled stages dim, and focus uses a celadon outline on
  the dark band.
* The document keeps one normal vertical scrollbar. The rail no longer creates
  a nested scroll area that hides export actions under a tall editorial intro.
* At ≤1040 px the stage list scrolls horizontally inside the topbar rather than
  wrapping to a second sticky row.

Route changes now use `behavior: 'instant'` for the top reset. `auto` was
deferring to the app-wide `scroll-behavior: smooth` and animating through the
previous page, which read as a delayed/half-loaded new view.

## Scatter marks

`frontend/src/explore/scatterMarks.ts` is the shared display-rule module.

| Rule | Value / behaviour |
|---|---|
| Stroke width | 3.1 px for ≤500 drawn rows, 2.55 px for 501–1200, 2.15 px above 1200 |
| Opacity | 0.86 / 0.78 / 0.70 by the same sample tiers; 0.20 for unselected marks while a selection is active |
| Halo | Paper-coloured stroke, +2.6 px, 62% of mark opacity, so marks separate from grid lines without changing values |
| Palette | Eight-token palette; group levels cycle within that bound rather than inventing colours |
| Selection | A single copper path with a paper halo; all other marks recede, so the selection cue is unambiguous |
| Density | The caption states drawn rows, filtered population, stride and valid-pair count |

### Discrete-axis jitter

A numeric axis is treated as discrete only when it has at least 8 drawn values
and at most 12 distinct values. Both `month_index` (six levels here) and
similarly bounded numeric codes qualify; `tenure_months` and other continuous
axes do not.

Qualifying axes receive a deterministic offset derived from the immutable row ID
and axis, bounded at **4.2 px**. It is stable across renders, selections and
colour changes. It applies only to display coordinates: underlying values,
brushes, counts and correlation are unchanged. The offset is disclosed in the
figure sub-caption, the export notes and the matrix note. No random jitter is
used.

The focus scatter and the matrix share the same jitter function, stroke tiers
and opacity function, so a row looks the same in both.

## Scatter matrix

The previous matrix claimed “coloured by” a grouping column but rendered one
teal path.

Now:

* Panels are a real 3 × 2 gallery at workstation width (`repeat(3, 238px)`,
  centred) rather than five across plus an orphan. At ≤760 px they become one
  column.
* Each panel draws one path per group level, using the shared palette. The
  matrix legend names the grouping column and its levels.
* Every panel states **Pearson r** computed from the same drawn render sample,
  plus the valid-pair count and whether its axes use the ≤4px offset. The note
  says the coefficient is descriptive, not a finding or causal claim.
* Panels are keyboard-operable buttons: `Enter`/`Space` opens the pair in the
  focus scatter. Hover/focus feedback make that affordance visible.
* Panel SVG height is fixed (`218`), so the x-axis label is not clipped when the
  CSS grid stretches a cell.

## Dossier paper

The in-app dossier uses the same editorial paper language as the export:

* dark ink cover with serif dataset title, provenance meta and a wrapped
  contents strip;
* 42 px paper gutters, serif section headings, mono labels and dense evidence
  tables;
* large primary numbers for findings / evaluated / not evaluated / model runs;
* a two-column findings/cautions block that collapses to one column on phones;
* copper severity badges and restrained red/amber/blue category states;
* no shadow, border, chrome, rail, archive or runtime block in print.

`overflow: clip` (not `hidden`) keeps the cover inside the paper's corners
without creating a new scroll container. Section anchors therefore move the
document, not an invisible inner box.

## Screens reviewed

All captures are in `docs/screenshots/s7/` and are produced by
`frontend/e2e/s7-report-studio.spec.ts`:

* `s7-chrome-1920.png` — one-row sticky masthead and scrolling context band.
* `s7-scatter-1920.png` — `month_index × tenure_months`, visible marks, groups
  and the disclosed discrete offset.
* `s7-matrix-1920.png` — 3 × 2 matrix with grouped paths and per-panel r.
* `s7-model-lab-1920.png` — a real OLS fit used as the dossier's model source.
* `s7-report-1920.png`, `s7-report-1366.png` — studio and paper at desktop widths.
* `s7-report-tablet-834.png`, `s7-report-mobile-390.png` — stacked composition.
* `s7-report-paper-tablet-834.png`, `s7-report-paper-mobile-390.png` — the paper
  itself at tablet/phone widths.
* `s7-print-1440.png` — print media with chrome/rail/archive removed.
* `s7-generated-dossier-1440.png` — the downloaded HTML opened directly.

## Honesty boundaries

Jitter does not change values, brush ranges, counts or correlations. Matrix r is
computed from the drawn sample, not the full population, and is labelled as
descriptive. Colour reduces a level to a token; missing grouping values become a
visible “(missing)” bucket rather than disappearing. No visual feature adds a
finding, ranking or safety score that the server did not produce.
