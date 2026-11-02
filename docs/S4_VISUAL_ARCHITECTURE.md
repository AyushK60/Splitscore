# S4 visual architecture — the Scientific Visual Explorer

## Where it lives

```
backend/app/explore/
  sampling.py      deterministic render sampling (systematic grid, documented stride)
  stats.py         numeric parsing, Pearson/Spearman, histograms, Tukey boxes, frequencies
  schema.py        variable catalogue (types, ranges, colour candidates, split info)
  selection.py     brush predicates → exact row-id sets (population_mask, evaluate_selection)
  aggregates.py    correlation matrix, distribution and missingness payloads
backend/app/api/routes_explore.py
                   /api/datasets/{id}/explore/{schema,series,selection,rows,
                                              correlation,distribution,missingness}
backend/tests/test_explore.py    40 tests incl. scipy oracles

frontend/src/explore/
  ExploreState.tsx   dataset schema + THE shared selection engine (context)
  figureExport.ts    standalone SVG builder, PNG rasteriser, JSON manifest
frontend/src/components/explore/
  ParallelCoordinates.tsx   flagship chart (brushing, reorder, highlighting)
  CorrelationHeatmap.tsx    Pearson/Spearman matrix with per-cell evidence
  ScatterFocus.tsx          two-variable scatter with a box brush
  ScatterMatrix.tsx         bounded 4-variable pairwise grid
  Distributions.tsx         histogram / frequency / group overlays / box stats
  MissingnessView.tsx       exact bars + bounded matrix + group breakdown
  RowEvidence.tsx           inspector: predicate, counts, real rows by id
  FigureExport.tsx          SVG/PNG/JSON export group per figure
frontend/src/views/ExploreView.tsx    workspace: controls, tabs, canvas, inspector
frontend/src/styles/explore.css       extends the Study workspace tokens
```

## Workspace layout

One dataset, one shared selection, six coordinated plot modes as tabs over a
single large canvas (parallel coordinates · correlations · scatter · scatter
matrix · distributions · missingness), research controls in one band (dataset
identity with short fingerprint, axes chips, colour grouping, active
population with split context, clear selection, focus mode), and a permanent
row-evidence inspector. Focus mode collapses the inspector so the plot gets
the full width. Below 860 px the inspector stacks under the canvas; nothing
is squashed into tiny cards.

## Rendering rules (the honest-figures contract)

1. **Only numeric columns become axes.** A colour variable (e.g. a boolean)
   may travel in the series payload for grouping but never renders as a rail.
2. **Axis ranges cover the full population**, not the filtered subset — axes
   must not rescale while the user brushes, or committed brushes would drift
   off the rails (this was a real defect found during verification).
3. **Point-level data is a render sample.** The backend draws a systematic
   grid sample (every *k*-th row in file order, `k = ceil(n / cap)`, cap 1200
   by default, hard bound 5000). Every chart states "N of M rows drawn
   (every k-th row)". Sampled density is never presented as the whole dataset.
4. **Missing or unparsable cells break polylines** at that axis and drop
   scatter points — never a coerced zero, never a dropped row silently.
5. **Constant columns render as a mid-rail marked "constant / no spread"**,
   with the reason spelled out.
6. **Aggregate views are computed on the full requested population
   server-side** (correlations, histograms, box stats, missingness). The
   frontend never recomputes a statistic the backend already produced.
7. **Group hues deliberately exclude copper** — copper means "the user's own
   selection" everywhere in the explorer.

## Exports (F22 preliminary)

Each figure carries an Export group: SVG (standalone serialization of the
live chart, computed styles baked in so `var(--rs-*)` resolve to literal
colours, print-safe paper background, caption block), PNG (2× raster) and
JSON (figure manifest). The scatter matrix is JSON-only by design; its
caption points to the focus scatter for vectors. Details:
`docs/S4_FIGURE_EXPORTS.md`.

## Known boundaries

- The explorer analyses the dataset currently in the store; it does not
  persist anything and adds no new persistence path.
- Uploads are still CSV (V1 boundaries: 25 MiB file / 10k rows / 100 cols).
- The explorer does not modify the study role map; it only *reads* it for
  suggestions (colour grouping, split context).
- Violin plots were skipped deliberately: no density estimator with a stated
  sample-size policy exists yet, and the blueprint forbids invented density.
- High-dimensional embeddings (optional in F08) are not implemented.
