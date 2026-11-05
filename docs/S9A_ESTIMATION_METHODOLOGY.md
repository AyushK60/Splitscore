# S9A estimation methodology

**Stage:** S9A — Scientific Causal Effect Estimation (regression adjustment, IPW,
cross-fitted AIPW), propensity modeling and numerical verification.
**Branch:** `v2-premium-visual-foundation` · **Starting HEAD:** `0c5bf2d` (S8C)

This document states what S9A computes, under which assumptions the computation
is entitled to a causal reading, and which claims it never makes. It extends —
and never weakens — the S8C scientific contract.

## 1. What S9A establishes

Given a **live dataset**, a **stored, structurally valid causal graph**, and a
**backdoor adjustment set verified by S8C's exact engine against that stored
graph**, S9A computes the **average treatment effect (ATE)** of one binary
treatment on one numeric outcome over one explicit analysis cohort, with three
named estimators, honest uncertainty, and real diagnostics.

The estimand is fixed for this stage: `ate`. There is no ATT, CATE, mediation
or front-door output anywhere in the code, and no endpoint can produce one.

## 2. The identification gate (mandatory, server-side)

Before any number is computed, `service.run_identification_gate` verifies, in
order, and refuses on any failure:

1. **Fingerprint match.** If the client names an expected
   `expected_spec_fingerprint_sha256` that differs from the stored graph's
   scientific fingerprint, the run is refused with **409**, never estimated
   against a graph the client has not seen.
2. **Graph validity.** The stored graph is re-validated against the dataset
   currently in memory (column anchors resolve, dataset fingerprint unchanged).
3. **Node resolution.** Treatment, outcome and every adjustment node must
   exist, be declared observed, and be anchored to a real dataset column.
   Adjustment nodes must differ from the scope pair and from each other's
   columns.
4. **S8C verdict.** The requested adjustment set is evaluated by
   `causal.adjustment.evaluate_adjustment_set` — the exact classical backdoor
   criterion on the stored graph. The client's claim is never trusted; a set
   containing a post-treatment or unobserved variable, or leaving a backdoor
   path open, is a structured 422 with the violations listed.
5. **Column compatibility.** Enforced during preparation: the treatment column
   must admit exactly the two requested values, the outcome must parse as a
   finite number.

A failed or truncated S8C search is not required for estimation when the
client names a specific set — the *evaluation* of that set is exact regardless
of whether a full search would be exhaustive. What estimation requires is that
the named set passes; nothing else.

## 3. Supported scope and data assumptions

* One binary treatment with an explicit two-value mapping (`treated`,
  `control`); ambiguous encodings are refused with the unmatched values
  listed. Arm minima are enforced (10 rows per arm, 20 total).
* One numeric outcome. A binary outcome (exactly two distinct values) is
  supported and every estimate is documented as a **probability difference**
  for the coded-1 value; the coding is recorded in the payload.
* Observed covariates, numeric or categorical, typed value-based exactly per
  the Model Lab convention (fully numeric → continuous; ≥80% unparsable →
  categorical with ≤12 levels; anything else refused).
* Explicit analysis cohort: all prepared rows, or exactly one named partition
  of one named split assignment (`cohort.split_assignment_id` +
  `cohort.partition`). A predictive holdout is never silently combined with
  its fit partition — model evaluation and causal estimation answer different
  questions, and the payload records which rows the estimand is defined on.

## 4. Missing-data policy

Two policies, recorded in every payload:

* `complete_case` (default): rows missing any required value are excluded,
  with per-column counts and a sample of excluded row ids. The payload states
  that substantial complete-case exclusion can itself bias the analysis.
* `median_mode`: numeric values are median-imputed and categorical values take
  an explicit missing level, **fitted inside each training fold** (leakage-safe
  for cross-fitting and bootstrap). The payload states that imputation does
  not remove missing-data bias.

Rows are never silently dropped: every exclusion carries a reason, a count,
and (where applicable) sample row ids; rows before and after every stage are
reported.

## 5. What S9A does not establish

* **Identification is not exchangeability.** A verified adjustment set
  licenses estimation *under the drawn graph*. No unmeasured confounding,
  consistency, and positivity remain assumptions; no diagnostic verifies them.
* **Balance is not proof.** Standardized mean differences are descriptive;
  no SMD threshold tests exchangeability, and the payload says so verbatim.
* **Overlap is not positivity.** The overlap diagnostics describe the fitted
  propensity distribution in this sample; the population assumption cannot be
  verified by any dataset.
* **Estimates are not validated by agreement.** Estimator disagreement is
  reported as a specification/instability signal, never resolved by picking a
  winner, and never combined into a single score.
* **No p-values.** No hypothesis test is computed anywhere in S9A.

## 6. Reproducibility and staleness

Every payload carries: dataset id and fingerprint, graph id, revision and
scientific fingerprint, treatment/outcome/adjustment columns and mapping,
cohort selection, missing-data policy, cross-fitting design, uncertainty
method with resolved seed, propensity truncation settings, effective sample
sizes, software versions, and the stage's computational limits.

Stored runs are re-checked against the current dataset and graph fingerprints
on retrieval: either change marks the run **stale** with a stated reason. Node
layout coordinates are excluded from the graph fingerprint, so rearranging the
canvas never invalidates a causal estimate — exactly the S8A rule.
