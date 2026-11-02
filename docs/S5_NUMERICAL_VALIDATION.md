# S5 numerical validation

**Date:** 2026-11-03
**Principle:** every new check has positive, negative and ambiguous/unsupported
fixtures whose expected results are hand-written from the fixture, independent
of the implementation. No expectation is derived by calling the code under
test.

## Suites and counts

| Suite | Cases | What it pins |
|---|---|---|
| `backend/tests/test_integrity_v2.py` | 32 | F04 checks (SS-AVL-001, SS-TGT-002, SS-ENT-002, SS-CHR-002, SS-PPF-001, SS-VRU-001) and the F06 scorecard |
| `backend/tests/test_plans_similarity.py` | 15 | F05 plans and the F07 similarity explorer |
| Original five check suites | unchanged | SS-DUP-001, SS-ENT-001, SS-CHR-001, SS-TGT-001, SS-NEAR-001 definitions, severities, denominators |
| Full backend suite | **340 passed** | everything above |
| `scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks, exit 0** | the audit engine against independent ground truth, unchanged by S5 |

## Hand-checked oracles (examples, full set in the test files)

- **SS-AVL-001**: two features with one declared `after_prediction` → exactly
  one high finding; count (1, 2) columns; `unknown` → info, never clean;
  derived feature depending on a future-only input → medium on top of the
  high; no declarations → NOT EVALUATED.
- **SS-TGT-002**: a categorical value determining the label 6-of-7 times with
  coverage ≥ 2 % → flagged info; 5-of-7 → nothing (below the 0.98 purity
  floor); a numeric column whose single threshold separates a binary target
  perfectly over all parsable rows → flagged via the stump screen; a target
  with 13 distinct values → `unsupported`, never a guess.
- **SS-ENT-002**: 11-row fixture, badge column with distinct ratio 10/11 =
  0.91 → identifier-like; one shared value → medium finding with counts
  (1, 9) values, (1, 4) test rows, (1, 6) train rows; repeating column
  (ratio 2/11) → not screened; continuous float column sharing one value by
  coincidence → excluded, not flagged.
- **SS-CHR-002**: 31-day gap vs 7-day horizon → clean; 1 of 2 ordered test
  rows inside the window → high (50 % ≥ 10 % share bar); no declaration →
  NOT EVALUATED; horizon 0 → unsupported.
- **SS-PPF-001**: `full_dataset` step → high with count (1, 2) declared
  steps; `not_recorded` → medium; all `train_only` → clean *as declared*;
  no declaration → NOT EVALUATED with the raw-CSV sentence.
- **SS-VRU-001**: history not supplied → NOT EVALUATED (never "no reuse");
  2 prior runs of the same split → clean with the count in metrics; 4 → info
  finding; 5 runs of a *different* split (different labels) → no
  accumulation.
- **F05 plans**: group CV on a 6-entity × 2-row panel → every entity's rows
  appear in exactly one fold's test side across the plan (asserted per
  entity); rolling origin with gap 2 on 28 ordered days → train blocks
  strictly increasing and block+test+gap arithmetic pinned; smallest class
  below the fold count → typed infeasibility naming the numbers.
- **F07 similarity**: hand-checked geometry — two pairs tied at the minimum
  (f1 and f2 both differing by exactly 0.1) are both in the result at the
  same distance; the nearest-neighbour summary over 3 test rows has
  min ≤ median ≤ p90 ≤ max and a histogram summing to 3; two identical
  requests return identical pair lists and distances (determinism).

## Determinism and bounds

- The similarity sweep is exhaustive over analysed rows with a seeded
  proportional sample above 4000 combined rows; the sample seed (11) and the
  scope sentence travel with every response.
- Plan audits are bounded: ≤ 10 folds × 3 repeats per plan, ≤ 20 audited
  folds per comparison; the bound raises a typed error instead of silently
  truncating.
- No new check introduces a combined score, and every not-evaluated state
  carries its reason in the payload.

## Regression protection

- Original five checks: all pre-existing suites pass unmodified; oracle
  expectations unchanged (41/41, 61/61).
- Row-id contract: unchanged and exercised through the similarity Pair
  Inspector, Row Evidence and audit evidence in the browser journeys.
- Figure exports (S4) untouched; the export bundle still reflects displayed
  analysis.
