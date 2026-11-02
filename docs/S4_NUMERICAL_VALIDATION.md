# S4 numerical validation

All oracle tests live in `backend/tests/test_explore.py` (40 tests). Expected
values are written independently — scipy or hand-calculated fixtures — never
derived from the implementation under test. No expected value was modified to
make a test pass.

## Correlation — independent oracle: scipy 1.17.1

- **Pearson** matches `scipy.stats.pearsonr` to 1e-12 on a fixed 10-point
  fixture; pairwise-complete handling verified by injecting empty cells and
  comparing against scipy run on the complete pairs only (`n_valid` = 8).
- **Spearman** matches `scipy.stats.spearmanr` on a tied fixture; the rank
  routine itself is verified by hand (`[1, 2, 2, 3] → [1, 2.5, 2.5, 4]`, the
  standard average-rank treatment) and by a monotonic relationship giving
  exactly 1.0.
- **Undefined stays undefined.** A constant column returns
  `coefficient: null, warning: constant_x|constant_y` — never a fabricated
  zero. Fewer than 3 complete pairs → `insufficient_pairs` (2 points always
  give |r| = 1, which would read as a finding). The 3-pair minimum is
  documented in every correlation payload.
- **Unparsable cells are counted, not coerced**: `parse_numeric` reports
  `missing` (empty cells) and `unparsed` separately.
- **Through-the-API cross-check**: the bundled `clean_control` demo's
  x1/x2/x3 Spearman matrix matches an independent pandas+scipy read of the
  committed CSV, cell by cell, with `n_valid` = 240.

## Distributions — hand-calculated fixtures

- Histogram over values 0…9 with 5 bins: edges [0, 9], counts
  `[2, 2, 2, 2, 2]`; sum of counts equals the reported valid count; missing
  and unparsable cells are excluded from bins but counted in denominators.
- Single distinct value → one bin `[v, v]` holding all rows (no fake spread).
- Tukey box on 1…9: q1 = 3, median = 5, q3 = 7 (linear interpolation),
  IQR = 4, whiskers at 1 and 9 (fences −3/13 contain everything), zero
  outliers. Adding 100 → outlier count 1, whisker stays at 9 (whiskers stop
  at the most extreme value *inside* the fences); the definition string is
  carried in every payload.
- Categorical frequencies cap at 30 levels + an honest `other` bucket that
  makes the totals add up (verified on a 35-level fixture).
- Group overlays compute each group's statistics from that group's rows
  only, with the group size reported next to it (tested through the API:
  `even`/`odd` groups, 20 rows each, box n = valid count).

## Selection — hand-listed id sets

- Range predicates return the exact expected row-id lists on a 10-row
  fixture; the union-within-column / intersect-across-columns rule is pinned
  by a fixture where the two rules give different answers.
- Value predicates select the right rows; empty predicate list selects
  everything; impossible ranges select nothing; **missing cells never match
  a numeric range** (they are not numbers).
- Selection-aware overlays: the distribution endpoint returns the population
  histogram AND the selected cohort's histogram on the same bins (40 rows /
  20 selected, `box.n` = 20); missingness returns both the selected
  percentage and the whole-dataset numbers (6 missing cells → 3 in the
  selected half).

## Sampling — deterministic and bounded

- `render_sample(1000, 120)`: stride 9, indices `[0, 9, 18, …]`, 112 rows,
  identical across calls; below-cap populations draw everything (stride 1).
- The API series endpoint returns the same ids for repeated identical
  requests (asserted in the E2E-adjacent API tests) and its `scale` block
  covers the full population regardless of filters, so brushes use real
  data units.
- Ordinal captions ("every 3rd row") have their own regression test.

## Identity and validation

- The explore schema echoes the dataset's sha-256 exactly as the upload
  response reported it (fingerprint consistency asserted).
- Unknown columns, non-numeric correlation inputs, self-grouping, oversized
  requests (>32 series columns, >30 correlation columns, >100 missingness
  columns, >24 predicates) all return structured 422/413 errors — tested.
