# S9B — Visual design and scientific figure system

The studio extends the existing SplitScope V2 identity rather than inventing a
second one: paper-and-ink background, copper accent, editorial serif headings,
monospace numerals, restrained rules, no decorative animation.

## Structure

```
Effect Estimation Studio
├── header: title, dataset · graph · revision · fingerprint, causal trail,
│           readiness chip, Open Causal Lab
├── demo banner (bundled causal demo only): generating story + known effect
├── stale alert / run error (when present)
├── body
│   ├── aside — Analysis setup (sticky on desktop, inline on tablet/mobile)
│   │      graph · scope · mapping · adjustment set · estimator · missing data
│   │      · uncertainty · seed · advanced design · Run · readiness detail
│   └── main — Run history, result meta, five-view tab strip, active figure,
│              comparison table, interpretation
└── footer from the shell
```

**One primary visualization per view.** The five views are not a dashboard of
equal-weight cards; each is a full-width publication figure with its own title,
description, legend, export toolbar and scientific footnote, followed by at most
one supporting table.

| View | Primary figure | Supporting content |
|---|---|---|
| Effect summary | Horizontal dot-and-interval plot, one row per estimator, zero reference, labelled units | Estimator comparison table, comparison reading, export of the figure |
| Covariate balance | Love plot: unweighted circles, weighted diamonds, 0 reference, ±0.1 heuristic lines | Sortable covariate table, weighting applicability note, imputation disclosure |
| Overlap | Overlaid per-arm histograms over [0, 1] with a quantile strip and overlap window | 20-bin count/share table, extremes, truncation and warning notes |
| Weights | Raw vs effective sample size per arm with retained fractions | Weight summaries, truncation disclosure, instability warnings |
| Methodology | None (deliberately textual) | Estimand/scope, cohort accounting, adjustment set, estimation and uncertainty, provenance, limitations, defaults |

## Figure anatomy

`FigureFrame` owns the shared chrome: eyebrow, title, description, aside chips,
export group (SVG / PNG / CSV / JSON), legend slot, the plot itself and a
footnote block. Each view owns only its geometry and its export metadata. This is
why a figure cannot drift from the numbers it was drawn from: the SVG that is
exported is the SVG on screen, and the CSV/JSON are built from the same payload
fields and audit trail used for the drawing.

Charts are hand-built SVG. The project already used custom SVG for its research
figures; no charting dependency was added, so the landing-page bundle is
unchanged and the estimation workspace stays a lazy chunk.

## Visual decisions and their reasons

- **Horizontal intervals, not bars.** A dot-and-interval plot shows sign,
  magnitude and uncertainty without implying that bar length is a comparable
  quantity across methods.
- **Zero line always drawn**, labelled "no effect". Negative and positive
  effects share one numeric domain computed from every reported estimate *and*
  interval bound, so no interval is clipped.
- **Two encodings in the Love plot** (circle = unadjusted, diamond = weighted)
  plus separated rows per categorical level, because collapsing levels into one
  column hides the level that actually differs.
- **Within-arm shares in the overlap histogram**, not raw counts: 349 treated and
  851 control rows would otherwise look like a distribution difference that is
  only a group-size difference.
- **Quantile strip** under the histograms, using the backend's per-arm quantiles,
  so a reader can see the central 99% overlap interval without estimating it
  from bars.
- **Effective sample size as paired bars** (raw rows vs Kish ESS), with the
  retained fraction printed, because the number that matters is how much
  information survives weighting, not the weight value itself.
- **Colour is redundant with shape/labels.** Estimators are named in every row;
  the two arms are distinguished by fill *and* position/legend; the heuristic
  line is dashed and labelled as a heuristic.
- **Readiness chip changes tone, not just text**: neutral (not checked), busy
  (checking), blocked (not ready), ok (ready with row count). The run button is
  always accompanied by the reason it is disabled, in its title and in the
  status block.

## Responsive behaviour

| Width | Layout |
|---|---|
| ≥ 1281 px | Two columns: setup 380 px with internal scroll; main column for results. Five tabs in a 5-column grid with hints. |
| 1025–1280 px | Setup 300 px; main column narrower. Tables wrap their headers instead of forcing a horizontal scrollbar. |
| ≤ 1024 px | Setup becomes a full-width inline panel; methods cards stack. |
| ≤ 820 px | Figures reduce padding; legends and export chips left-align; hint text under tabs is hidden and the tab strip becomes horizontally scrollable with fixed minimum widths. |
| ≤ 560 px | Trail and headings shrink; definition lists stack label over value; split fields become one column; stale/error panels stack their action. |

No page-level horizontal overflow at 1440, 1024, 768 or 390 (asserted in the
Playwright responsive journey). Wide tables and the tab strip scroll *inside*
their own region, which is keyboard reachable.

## Accessibility

- Every view is a `section` with an accessible name; every figure is an `img`
  with a text alternative that states the plotted quantities and, where
  relevant, the overlap window.
- Plotted marks are focusable (`tabIndex=0`) with `aria-label`s; focus updates a
  live detail line, so hover information has a keyboard equivalent.
- Export buttons are a labelled group; download completion is announced in a
  polite live region.
- Error, stale and readiness states use `role="alert"`/`role="status"` and are
  visible text, not colour alone.
- Tables have captions and scoped headers; the comparison table is a labelled
  scroll region with `tabIndex=0`.
- Focus styles come from the existing global tokens; no custom control removes
  the outline.
- `prefers-reduced-motion` removes the studio's transitions; no figure relies on
  animation to be understood.

## Visual defects found in screenshot inspection and fixed

1. **Fifth tab dropped to its own row.** The tab strip was a wrapping flex row;
   "Methodology" wrapped alone and looked like a broken second-level navigation.
   Replaced with a five-column grid, and a horizontal scroll strip below 820 px.
2. **Horizontal scrollbar inside the comparison table at laptop widths.** Header
   cells were globally `white-space: nowrap`, so the table exceeded its column.
   Added an `esttable--wrap` variant for studio tables: headers may wrap, long
   warning text wraps inside its cell.
3. **A button nested inside a `<label>`** in the "no saved graph" hint produced a
   bogus composite accessible name for the whole label. The wrapper is now a
   `div`; the graph select keeps its own `aria-label`.

Screenshots live in `docs/screenshots/s9b/` and are listed with the verification
run in `S9B_VERIFICATION.md`.
