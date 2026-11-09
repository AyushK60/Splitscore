# Evaluation of the audit engine

`scripts/evaluate_synthetic.py` runs the leakage rules against synthetic cases
whose correct answers are known, and checks statuses, severities, counts,
metrics and evidence row ids. It shows that the rules implement their stated
definitions. It says nothing about accuracy on real data.

```bash
python scripts/evaluate_synthetic.py                    # summary; exit 0/1/2
python scripts/evaluate_synthetic.py --output-dir out/  # also writes evaluation_results.json
python scripts/evaluate_synthetic.py --list             # case ids
python scripts/evaluate_synthetic.py --case tgt_exact_copy
```

Exit codes: `0` every expectation matched, `1` at least one mismatch, `2` a case
could not be evaluated or the command was invoked incorrectly.

## Cases

Cases live in `backend/app/evaluation/cases.py`.

1. **Hand-built fixtures.** Every row is written out in source and every
   expectation (status, severity, counts, metrics, evidence ids, distances) is
   computed by hand from the rule definition, never by running a detector.
2. **Demo datasets.** The bundled CSVs are audited with their recommended
   roles. Expected outcomes come from `backend/app/evaluation/oracles.py`,
   which enumerates all matches independently of the rule code. The generator's
   `planted_cases` metadata is descriptive only, because shuffling can create
   extra matches.
3. **Generated-split cases.** Fixtures without a split column, audited under a
   generated assignment. Split sizes, temporal ordering and class counts are
   recomputed independently with pandas and compared with the rule metrics.

Every generated split is also checked for these invariants: each row is
assigned exactly once, both sides are non-empty, the input frame is unchanged,
the same seed reproduces the assignment, and entity overlap and chronology
agree with an independent recount.

Outcomes such as not evaluated, insufficient data, unsupported and disabled are
asserted together with their reasons, so a check that did not run cannot be
mistaken for one that passed.

## Count definitions

* **SS-DUP-001:** the denominator is the number of distinct signatures in the
  test split, not test rows. If test rows carry signatures A, A, A, B, D and
  A and B also occur in train, the count is 2 of 3 signatures, and 4 of 5 test rows.
* **SS-ENT-001:** affected test rows over all test rows, including unlabelled ones.
* **SS-TGT-001:** matches over comparable rows only (feature and target both present).
* **SS-NEAR-001:** a pair is one (train row, test row) combination whose scaled
  Chebyshev distance is at or below the threshold.
* **Chronological cut with a tie:** the cut moves so a tied timestamp stays on
  one side. With 10 rows, Jan 1-6 once each and Jan 7 four times, a 0.3 test
  fraction gives train 6 and test 4.
* **Stratified allocation:** 6 A and 4 B at fraction 0.5 gives 3 A and 2 B on each side.

No aggregate precision or recall is reported. The rules count different units
(signatures, entities, columns, row pairs), so one pooled score would not mean
anything.

## Limitations

* Fixtures are small and synthetic, typically 4 to 360 rows.
* Findings show a capped number of examples (`max_examples`). Counts and
  metrics are always complete.
* Near-duplicate findings are candidates at a chosen threshold, not proof of leakage.
* Concurrency, very large datasets and real-world corpora are not covered.
* The random split case checks properties that hold for any draw. It does not
  claim that random splitting separates entities or balances classes.
* Infeasible split requests (single class, too few rows, unparsable timestamps)
  are covered by `backend/tests/test_splits.py`.
