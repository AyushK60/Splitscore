# SplitScope — Synthetic Evaluation of the Audit Engine (Stages 4c + 4d)

**Date:** 2026-10-17 (4d added)
**Status:** 41/41 cases, 61/61 checks pass. Exit 0 on the default run.

This document describes an engineering evaluation on deterministic synthetic
fixtures. It asks whether the implemented checks detect independently specified
conditions, report accurate counts and evidence, and distinguish "did not run"
from "ran and found nothing". **It is not evidence of real-world detection
accuracy.** Synthetic fixtures are small, clean and deliberately constructed;
real datasets are none of those things.

## Reproduction

```bash
cd /e/Freebuff
python scripts/evaluate_synthetic.py                     # human summary; exit 0/1/2
python scripts/evaluate_synthetic.py --output-dir out/   # + out/evaluation_results.json
python scripts/evaluate_synthetic.py --list              # case ids
python scripts/evaluate_synthetic.py --case tgt_exact_copy   # single case

cd /e/Freebuff/backend
python -m pytest -q                                      # full backend suite
python -m pytest tests/test_evaluation.py -q             # runner tests only
```

Exit codes: `0` all expectations matched; `1` at least one expectation
mismatch (the engine disagrees with specified ground truth); `2` a case could
not be evaluated (invalid/missing fixture or unexpected runtime error), or the
invocation was wrong. Errors outrank failures (2 > 1 > 0).

Reproducibility: two consecutive default runs produce byte-identical JSON
after removing `generated_at_utc` (verified by direct comparison; the JSON now
also carries per-case `split_facts` for generated-split cases).

## What is evaluated

| Rule | Scope | Evaluation unit (finding) | Count units |
|------|-------|---------------------------|-------------|
| SS-DUP-001 | Exact cross-split duplicates | distinct feature signature shared by train and test | rows / signatures |
| SS-ENT-001 | Entity overlap | distinct non-missing entity value in both splits | rows / entities |
| SS-CHR-001 | Chronological boundary | train rows newer than the earliest test timestamp | train rows |
| SS-TGT-001 | Target copy | selected feature column (one finding per matching feature) | comparable rows/values |
| SS-NEAR-001 | Near duplicates (opt-in) | cross-split candidate row pair at or below the threshold | pairs / analysed rows |

Near-duplicate outcomes are treated as **candidate similarity findings**, not
definitive leakage labels; the rule itself caps severity at `medium`.

## Fixtures and the independence of expectations

Two kinds of cases, all in `backend/app/evaluation/cases.py`:

1. **Hand-built fixtures** (31 cases, 4 + 12 + 7 + 7 + 7 + 1 rows-scale): every
   row is written out in source, and every expectation — statuses, severities,
   exact counts, metric values, evidence row ids, hand-calculated distances —
   is written by hand from each rule's documented definition. Nothing in these
   expectations is produced by running a detector.
2. **Committed demos** (6 cases): the six bundled CSVs audited with their
   recommended roles/config. Complete expected outcomes for every evaluated
   check are computed by `backend/app/evaluation/oracles.py`, independent
   ground truth written from the rule definitions, importing no rule code.
   Planted counts from the generator manifest are *not* trusted as the total:
   generated data can contain additional matches, so the oracles enumerate all
   matches (e.g. the `exact_duplicates` demo plants 25 cross-split groups but
   the generator's shuffle can create more; the oracle computes the true
   total). For the near-duplicate demo, all 20 planted pairs must additionally
   appear among the candidate evidence.
3. **Generated-split cases** (4 cases, Stage 4d): fixtures without a split
   column; the split under audit is a generated assignment. Hand-written
   `expected_split_facts` (sizes, temporal ordering, class counts) are checked
   against values the runner recomputes *independently* from the fixture rows
   joined to the assignment (pandas set logic), never from rule output; where a
   fact must agree with a rule metric (entity overlap, chronology), both sides
   are compared explicitly.

Coverage per check (positives, negatives, boundaries, did-not-run paths):

- **Exact duplicates:** cross-split duplicates with multiple records per
  signature; duplicates confined to one split; missing vs literal strings
  (including `missing_tokens` configuration); target and metadata excluded
  from comparison.
- **Entities:** shared, disjoint, within-split-only repetition; missing
  identifiers counted separately per side; group-holdout isolation (generated
  split evaluated through the same audit interface).
- **Chronology:** ordered separation; violation; equal boundary timestamps;
  invalid/missing timestamps and the eligibility policy; chronological split
  with ties; not-applicable intent; insufficient data.
- **Target copies:** exact copy; no match; partial missingness and coverage
  arithmetic; constant target → `insufficient_data`; constant feature and
  below-minimum-sample skips recorded in metrics; majority-class artefact →
  `low` severity.
- **Near duplicates:** hand-calculated raw distances inside/at/outside the
  threshold; robust scaling; constant features and missing-value handling;
  oversize `skip` → `not_evaluated`; oversize `sample` → deterministic seeded
  sample reported in scope; non-numeric → `unsupported`; default off →
  `disabled`.
- **Diagnostics:** a 29:1 imbalanced, distribution-shifted fixture yields zero
  leakage findings — imbalance and shift appear as diagnostics only.
- **Generated splits (Stage 4d):** random (repeated entities, hand-argued
  guaranteed overlap, seed 17 → 9/3 rows), stratified (6 A / 4 B at 0.5 → exact
  3 A / 2 B per side), chronological with distinct timestamps (Jan 1-7 / Jan
  8-10), and chronological with a four-row boundary tie (cut moves left → 6/4).

"Not evaluated / insufficient data / unsupported / disabled" outcomes are
asserted with their reasons, so a check that did not run can never be mistaken
for a check that passed.

### Split-assignment invariants (Stage 4d)

Every case with a generated split (the four new cases plus the existing group
holdout) additionally has these **always-on** invariants, violations of which
fail the case regardless of any pinned expectation:

* every fixture row receives exactly one assignment (train xor test),
  verified on both the masks and the exported row-id lists — no unknown or
  duplicate ids;
* split sizes are recorded and pinned per case from the documented
  rounding contract;
* both partitions are non-empty (each strategy enforces a documented
  minimum, also re-verified by the runner);
* the input frame is unchanged after generation and audit (deep-copy
  comparison);
* regenerating with the same configuration reproduces the assignment
  (all four strategies are deterministic; randomised ones because of their
  explicit seed);
* the independently recounted entity overlap equals the SS-ENT-001
  `shared_groups` metric, and the independently computed chronology status
  equals SS-CHR-001's (chronological cases).

The public comparison orchestration (`compare_splits`) is additionally
covered by a focused integration test generating stratified and chronological
candidates end to end, checking assignment row-id integrity and that the
chronology verdict agrees with temporal facts computed from the original
fixture timestamps.

## Result of the run

41 cases, 41 passed, 0 failed, 0 errors; 61 checks, 0 failed; exit 0.

Assertions are exact: status, finding count, severity, count
(affected, denominator) pairs, metric values, and evidence resolution (every
cited row id exists in the fixture; truncated findings must declare
`examples_truncated` with `example_total` > displayed examples;
untruncated findings must display every example).

### Metrics honesty

The suite reports **exact case/check assertions and count agreement** — no
aggregated precision/recall and no universal accuracy score. Aggregation was
deliberately skipped: the positive units differ per rule (signatures, entities,
feature columns, row pairs), ground truth is complete per case but not defined
over one shared population, and mixing them would produce meaningless numbers.
Per-case TP/FP/FN-style statements are captured implicitly as exact expected
vs. actual counts; no metric is ever inferred from bounded example lists.

### Hand-worked count examples (expectation independence)

Tiny worked examples pinning the ambiguous count definitions. Each is derived
from the documented rule definition and the fixture rows alone.

1. **"signatures present in both" (SS-DUP-001)** — denominator is the number
   of *distinct signatures observed in the test split*, not test rows. Fixture
   `dup_cross_split_multi`: test rows carry signatures A, A, A, B, D → 5 rows,
   3 distinct test signatures; A and B are shared with train → count
   (2, 3). Affected *rows* are counted separately: 4 of 5 test rows.
2. **Entity share (SS-ENT-001)** — affected test rows over *all* test rows
   (unlabelled rows included in the denominator). `ent_shared_entities`: 2
   shared-entity rows of 3 test rows → 2/3 ≈ 66.7% ≥ 10% → high.
3. **Target-copy coverage (SS-TGT-001)** — matches over *comparable* rows
   only (feature and target both non-missing). `tgt_partial_missingness`:
   20 rows, 5 feature-missing → 15 comparable; 14 match → 14/15 ≈ 0.933.
4. **Near-duplicate pair (SS-NEAR-001)** — a pair is one (train row, test
   row) combination at scaled Chebyshev distance ≤ threshold. In
   `near_threshold_boundaries` (raw units, threshold 0.25): train a=1.0 meets
   test a=1.125 at 0.125 (inside) and test a=1.25 at exactly 0.25 (included),
   while 1.375 is outside.
5. **Chronological cut with a tie** (`split_chronological_boundary_tie`) —
   10 rows: Jan 1-6 once each, Jan 7 four times. Requested test rows =
   round(0.3 × 10) = 3 → raw cut at sorted position 7, which falls inside the
   Jan 7 tie; the documented policy moves the cut so the whole tie stays on
   one side → train = 6 rows, test = 4 rows.
6. **Stratified allocation** (`split_stratified_class_preservation`) — 6 A /
   4 B, fraction 0.5: requested test = 5; proportional allocation is exactly
   integer (6 × 0.5 = 3, 4 × 0.5 = 2) → both sides hold A=3, B=2.

## Triage of the six initial mismatches

(The six items below are the *original* first-run mismatches from Stage 4c.
The four Stage 4d split-strategy cases passed on their first run and required
no triage.)

The first full run failed 6 of 37 cases. Each was traced to a cause; **no
detector bug was found**, and no expectation was changed just to match
output — each correction below was justified first from the rule definition
and the fixture arithmetic:

1. **`dup_cross_split_multi`** — expectation arithmetic errors (mine): the
   denominator of "signatures present in both" is *distinct test signatures*
   (3, not 5 test rows) and train rows were doubled (8 → 4);
   `distinct_feature_signatures` is 4 (A, B, C, D), not 5. Corrected against
   hand-counted fixture rows. *Cause: expectation.*
2. **`ent_group_holdout_isolation`** — expectation was arithmetically
   impossible: the fixture has 3 entities, so "2 in train and 2 in test" can
   never hold. Corrected to assert the isolation property
   (`shared_groups = 0`, `entity_overlap_test_share = 0.0`), which is what a
   group holdout guarantees. *Cause: expectation.*
3. **`ent_missing_identifiers`** — the fixture was rejected by role
   validation with `degenerate_groups` (only 1 distinct non-missing entity
   value; documented product behavior, not a rule failure). Fixture extended
   to 3 non-missing entities while keeping the missing-identifier semantics;
   counts recomputed by hand. *Cause: fixture.*
4. **`tgt_constant_feature_and_small_sample`** — the "sparse" column had only
   one distinct non-missing value, so the rule correctly classified it as
   constant (checked *before* the comparable-rows minimum); the
   below-minimum-rows metric therefore never fired. Fixture changed so the
   column varies ("0"/"1" on 5 rows, missing on 7): 2 distinct values,
   5 comparable rows < 10 → skipped as below-minimum. A second copying
   feature regression ("copy" was accidentally made constant) was caught by
   the same run. *Cause: fixture.*
5. **`tgt_majority_artefact_low`** — the fixture's feature was accidentally
   constant (all 25 rows "yes"), which the rule skips by design: a constant
   feature cannot copy a varying target. Fixture now uses two values
   ("yes"/"other") so coverage is 23/25 = 0.92 ≥ 0.90 while sitting below the
   0.92 majority baseline + 0.05 margin → expected `low` finding confirmed.
   *Cause: fixture.*
6. **`near_sample_oversize`** — the expectation assumed candidate pairs that
   the seeded 2-by-2 draw of the old fixture did not contain (0 pairs →
   evaluated with no finding is correct behavior there). Fixture redesigned
   so every possible draw contains a guaranteed near pair (two close values
   per side + one far value, raw-unit threshold), keeping the expectation
   (sampled rows, bounds, one aggregated medium finding) hand-verifiable
   regardless of the seed's draw. *Cause: expectation + fixture.*

Runner/adapter defects found and fixed during bring-up: signature mismatches
between `build_cases`/`_demo_cases`, use of non-existent `ColumnRoles`
attributes in the demo-case adapter, a broken `EvalCase` rebinding, and a
test-side string-join bug.

## Known limitations and unsupported cases

- **Synthetic only.** Fixtures are engineered and tiny (typically 4–360
  rows). Passing them shows the rules implement their stated definitions on
  controlled inputs — nothing about prevalence, noise, or blind spots in real
  data.
- **No precision/recall over a population**, for the reasons above.
- **Bounded evidence.** Findings display a capped number of examples
  (`max_examples`); the runner asserts cap-consistency, never that displayed
  examples equal all detected cases. Counts and metrics are the complete
  numbers.
- **Near duplicates** are candidate similarity findings at a chosen
  threshold; no fixture pretends they prove leakage.
- **Not covered:** concurrency, very large datasets (row/column limits), and
  any real-world corpus.
- The demo generators' own `planted_cases` metadata is *descriptive*, not
  asserted as ground truth where it disagrees with complete enumeration
  (documented generator quirks: `exact_duplicates` planted-case lists sample
  only 5 of the shared groups; near-duplicate `item_id` fields in planted
  cases can be stale after the shuffle).
- Split-strategy coverage: random/stratified/chronological/group assignments
  are verified end to end on small hand-built fixtures only. The random case
  pins invariants that hold for any draw (overlap ≥ 1, all test rows in shared
  entities); it does not attempt to predict which permutation the seed produces
  and does not claim random splitting guarantees entity separation or class
  balance. Infeasible-strategy rejections (single class, one-row class, too few
  test rows for every class, unparsable timestamps) are covered by the existing
  unit tests in `tests/test_splits.py`, not duplicated in the evaluation suite.

## What this does and does not establish

Directly tested: rule logic against stated definitions, count/metric
accuracy, evidence integrity, did-not-run separation, deterministic
reproducibility, and the runner's own failure modes (17 focused tests).

Assumed, not tested: that the documented definitions are the right ones for
detecting leakage in general, behavior on realistic data at realistic scale,
and any statistical error rate on unseen datasets.