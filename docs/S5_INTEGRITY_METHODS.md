# S5-B — Integrity V2 methods (F04 + F06)

**Date:** 2026-11-03
**Scope:** expanded leakage-assurance checks (F04) and the category risk
scorecard (F06). The five original checks (F03) are untouched: same rule ids,
definitions, severities, denominators and tests (`pytest -q`: 292 → 325
passing; the synthetic oracle still matches 41/41 cases, 61/61 checks).

## The declaration principle

Three of the new capabilities evaluate things a CSV cannot know: when a
predictor becomes known, how long after the training cutoff the evaluation
predicts, and where a scaler was fitted. For all three the user's declaration
is the only honest input, so the product treats **undeclared** as **NOT
EVALUATED**, never as passed. Nothing is inferred from a column name, a type
or a cardinality.

## New checks

### SS-AVL-001 — Feature availability ledger

Declared per feature in the audit config: `before_prediction`,
`at_prediction`, `after_prediction` (future-only) or `unknown`. Derived
features may declare dependencies.

- `after_prediction` predictors → **high** finding.
- Derived feature whose declared dependencies include a future-only column →
  **medium**.
- `unknown` declarations → **info** (an explicit gap, not a pass and not a
  finding of leakage).
- No declarations at all → NOT EVALUATED, with the reason naming exactly what
  is missing.

### SS-TGT-002 — Target proxy candidates (heuristic screen)

Bounded, single-column screen; **always info severity** because a candidate is
a question for the data owner, not proof:

- *categorical feature, class-like target (≤ 12 distinct values)*: majority
  class share (purity) of one feature value; flagged at purity ≥ 0.98 with
  value coverage ≥ 2 % and ≥ 3 rows.
- *numeric feature, binary target*: best single-threshold separation (decision
  stump), computed exactly over per-level class counts (ties included);
  flagged at weighted purity ≥ 0.98.
- Continuous targets (as class-like definitions go) → `unsupported`, stated
  rather than guessed.
- Each candidate carries the method, the dominant value/threshold, the purity,
  the coverage and the rows behind it. At most 5 candidates listed; the count
  reports truncation.

### SS-ENT-002 — Identifier-like feature reuse

Screens **feature** columns (the declared entity column belongs to
SS-ENT-001). A column is identifier-like when its distinct-value ratio over
non-missing cells is ≥ 0.9 — an observed property, stated with its evidence.
Predominantly non-integer numeric columns are treated as continuous
measurements and excluded: they are usually all-distinct without carrying
identity, so screening them would report coincidences. Cross-split value
overlap is reported with real counts (shared values, affected test rows, both
denominators) and a bounded example. No overlap → evaluated, no finding, with
the identifier-like column count still in the metrics.

### SS-CHR-002 — Declared prediction horizon (lookahead gap)

Requires a timestamp column and `temporal_horizon_days > 0`. Definitions:
gap = earliest valid test timestamp − latest valid train timestamp; affected =
test rows timestamped before `latest_train + horizon`. Severity high when ≥
10 % of ordered test rows are affected, else medium. Without a declared
horizon → NOT EVALUATED (the horizon is intent metadata a CSV cannot supply);
non-positive horizons → unsupported; unparsable timestamps are counted and
excluded per the SS-CHR-001 boundary conventions.

### SS-PPF-001 — Preprocessing fit boundary (declared)

The scientific constraint: a raw CSV cannot establish where a scaler was
fitted, and SplitScope does not instrument preprocessing execution. So:

- no declaration → NOT EVALUATED (the reason says plainly that this is not a
  pass and what a declaration would record);
- declared steps judged on `fit_context`: `full_dataset` → **high**;
  `unknown` / `not_recorded` → **medium**; `train_only` → clean *as declared*.
- Only an actual pipeline execution in a future version can upgrade "declared
  train-only" to "verified isolation"; the rule's vocabulary never claims it.

### SS-VRU-001 — Validation reuse (session)

Reads the session's in-memory run store — the only evaluation history the
application actually has. Split identity: dataset id + split kind, plus
(column, train value, test value) for existing splits or achieved sizes for
generated ones. ≥ 3 prior runs of the same split → **info** finding naming the
runs. History not supplied (e.g. the evaluation harness) → NOT EVALUATED with
the explicit sentence that this is *not* evidence that no reuse happened. An
empty history is a real observation and evaluates cleanly with the count in
the metrics.

## F06 — Category risk scorecard

`app/audit/scorecard.py` derives, from one audit's rule outcomes only:

| Category | Rules |
|---|---|
| Duplicate / Similarity | SS-DUP-001, SS-NEAR-001 |
| Entity | SS-ENT-001, SS-ENT-002 |
| Time | SS-CHR-001, SS-CHR-002 |
| Target | SS-TGT-001, SS-TGT-002 |
| Pipeline | SS-PPF-001 |
| Validation Reuse | SS-VRU-001 |
| Availability | SS-AVL-001 |

Per category: explicit status (`finding_present`, `evaluated_no_finding`,
`error`, `not_applicable`, `not_checked`), finding count, worst severity, a
best-effort affected-rows figure (largest rows-unit count per finding, with
the exact counts and denominators left in the linked findings), and per-rule
state including each not-evaluated reason. There is deliberately **no numeric
score**, and the note on the scorecard itself says absence of findings is not
proof of safety. The Results view renders it (`.scorecard`) with "Open
evidence" links resolving the exact finding rows.

## Configuration surface

`AuditConfig` gains `feature_availability`, `derived_feature_dependencies`,
`temporal_horizon_days`, `temporal_horizon_note` and `preprocessing`. The
Data stage's "Audit settings (advanced)" editor renders the ledger, the
horizon fields and a preprocessing-step list. The frontend merges any
recommended config over its defaults, so a response from an older backend can
never leave the editor reading undefined structures.

## Numerical validation

Every check has positive, negative and ambiguous/unsupported fixtures with
hand-written expectations in `backend/tests/test_integrity_v2.py` (32 tests),
plus the untouched suites for the original five. Aggregate numbers are in
`docs/S5_NUMERICAL_VALIDATION.md`.
