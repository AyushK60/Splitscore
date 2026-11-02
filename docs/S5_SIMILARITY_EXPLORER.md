# S5-C — Similarity Explorer (F07)

**Date:** 2026-11-03

## Method

`backend/app/explore/similarity.py` implements the exploration half of the
near-duplicate method (SS-NEAR-001), stated in full on every response:

1. **Columns.** Only numeric feature-style columns (≥ 80 % of non-missing
   values parse as finite numbers). Non-numeric columns are listed as
   excluded, never silently skipped.
2. **Split.** The explorer audits the split confirmed in the Data stage —
   read from the session's study record, seeded from a demo's declared
   manifest where one exists, never inferred. Without a split it returns a
   typed error naming what to confirm.
3. **Rows.** Rows missing more than half of the included columns are excluded
   and counted. Rows are never invented; unparsable cells stay excluded.
4. **Imputation.** Remaining gaps are filled with the column median over the
   pooled train+test rows, so imputation does not depend on split membership.
5. **Scaling.** Robust (median / IQR) over the same pooled population;
   constant columns and undefined-IQR columns are excluded openly. The scaler
   is diagnostic only and is never exported.
6. **Distance.** Normalised Chebyshev (L∞): the maximum absolute scaled
   difference over the included columns — one readable number per pair.
7. **Pairs.** Only cross-split pairs, swept in chunks with a bounded
   worst-first list: exactly the K nearest pairs survive, ties broken by row
   position (never by chance). Re-running the request reproduces the same
   pairs byte for byte.
8. **Summary.** Every analysed test row's nearest-neighbour distance feeds a
   20-bin histogram and exact min/median/p90/max — an overlap density view
   computed from real distances, not an illustration.

## Bounds and honesty

- At most 100 pairs per request (UI offers 10 / 25 / 50); the response states
  how many pairs the sweep compared and whether the list is truncated.
- Combined rows above 4000 take a seeded proportional sample (seed 11) and
  the sampling note is carried verbatim into the UI.
- Pair records carry only immutable row ids, the distance, the top differing
  columns (scaled Δ plus both raw values) and a bounded display-value map.
  The Pair Inspector resolves the two ids through the same rows endpoint the
  Row Evidence inspector uses — what you read is the file's own text.

## Integration

- **Shared identifiers.** Pair rows are `row-000001`-style ids, the same
  contract audit evidence and the explorer use.
- **Linked charts.** Hovering a pair highlights its train row in every linked
  chart through the shared `highlightedId`; the inspector says so and names
  the highlighted id.
- **Scorecard / audit.** The explorer is an exploration: its response and the
  UI both state that a close pair is a candidate for human inspection, not a
  finding of leakage, and link the method to SS-NEAR-001.

## UI

A new **Split similarity** tab in the Visual Explorer (`SimilarityExplorer`):

- nearest-pairs list with distance, both row ids, and the top-3 scaled diffs;
- nearest-neighbour histogram + exact summary facts (test rows analysed,
  median nearest distance, scaling description, dropped rows);
- Pair Inspector: train/test columns side by side with `=` / `≠` / `∅`
  markers, top differing columns with raw values, distance and method, and
  the limitations one disclosure away;
- honest error state when no split is confirmed (what to do, no guessing).

## Verification

- `backend/tests/test_plans_similarity.py` — 15 tests: exact fold
  construction for all three plan kinds, every feasibility gate, per-fold
  audit aggregation, total-fold bound, nearest-pair ordering (with a
  hand-computed tie set), NN summary arithmetic, deterministic repeat runs,
  open exclusion of non-numeric columns, and the typed no-split error.
- Determinism: two identical requests return identical pair lists and
  distances (asserted in-test).
