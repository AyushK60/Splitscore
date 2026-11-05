# S9A scientific validation

How the estimators were verified. Every expected value in the test suite comes
from a data-generating process (DGP) written next to the test or from an
independent reference formula — never from the implementation under test.
Files: `backend/tests/test_causal_estimation.py` (engine, 34 tests),
`backend/tests/test_causal_estimation_api.py` (API, 11 tests).

## 1. Known-effect synthetic fixtures (recovery)

Each DGP fixes a known ATE; tolerances are ≈1.5–2 sampling standard errors for
the given `n` (a finite-sample estimate is not required to equal its
parameter), and intervals are required to cover the truth.

| Case | Design | n | True ATE | Requirement |
|---|---|---|---|---|
| 1 | Randomized treatment, constant effect, empty adjustment set | 1000 | 2.0 | all three estimators recover; empty set passes the gate; CI covers |
| 2 | Observational, two measured Gaussian confounders | 900 | 1.5 | all three recover |
| 3 | No effect | 900 | 0.0 | estimate near 0; CI covers 0 |
| 4 | Strong measured confounding | 1200 | 1.0 | naive difference visibly biased; all three recover |
| 5 | Treatment imbalance (≈85/15) | 1200 | 0.8 | all three recover |
| 6 | Poor overlap (near-deterministic assignment) | 1200 | 1.0 | explicit overlap warnings; ESS shrinks; estimate reported with warnings, not hidden |
| 8 | Three measured confounders | 1200 | 1.2 | all three recover |
| 14 | Categorical confounder (3 levels) | 1200 | 1.0 | one-hot coding reported; level-level balance rows; all three recover |
| — | Binary outcome (logistic DGP) | 1500 | prob. diff. | `outcome_task="logistic"`, `units="probability_difference"`, coding recorded, positive effect of plausible magnitude |
| — | Group-aware cross-fitting (120 entities × 5 rows) | 600 | 1.0 | `group_kfold` strategy; recovers |

## 2. Gate refusals (no estimation without identification)

| Case | Scenario | Expected |
|---|---|---|
| 7 | Empty set with open backdoor paths | 422, `open_backdoor_path` |
| 9 | Mediator in the adjustment set | 422, `post_treatment_variable` |
| 10 | Unobserved confounder (`u → t`, `u → y`) | 422 for every proposed set |
| 19 | Client fingerprint ≠ stored fingerprint | 409 `infeasible_operation` |
| 20 | Mapping misses column values / identical values | 422 with unmatched values listed / contract-level refusal |
| 15 | Constant treatment | 422, arm minimum |
| — | Node not column-anchored; unknown node | 422 |

## 3. Missing data and row accounting

* Missing treatment (12 rows), missing outcome (12), missing covariate (16):
  each excluded with its own reason and count; counts sum exactly to the
  dataset total (Case 11/12/23).
* Complete-case vs `median_mode` (Case 13): complete-case drops the 16
  covariate-missing rows; imputation keeps them (within rounding) and both
  analyses recover the effect.

## 4. Honest failure states

* RA + `influence_function` → `uncertainty.status="unavailable"` with a reason
  naming the bootstrap; no fabricated interval (Case 21).
* AIPW with 10 folds and exactly 10 treated rows → per-estimator
  `status="failed"` with the fold shortness reason, while IPW in the same
  comparison still estimates (Case 21).
* Cohort below the 20-row minimum → 422 before any fitting.

## 5. Independent reference cross-checks (not our own oracle)

1. **statsmodels OLS vs RA.** For the linear DGP, g-computation with OLS must
   equal the T coefficient of the covariate-adjusted OLS regression
   (`sm.OLS(y ~ const + t + x1 + x2)`) to `1e-8` — an entirely independent
   formula and implementation (`test_regression_adjustment_matches_statsmodels_ols_reference`).
2. **Hájek arithmetic vs documented formula.** The IPW estimate and its
   influence-function SE are recomputed in the test from the returned
   propensities with plain numpy, agreeing to `1e-10`
   (`test_ipw_hajek_combination_matches_documented_formula`).
3. **AIPW SE vs pseudo-outcome arithmetic.** The payload SE equals
   `std(ψ, ddof=1)/√n` recomputed from the returned pseudo-outcomes
   (`test_aipw_interval_matches_pseudo_outcome_arithmetic`).
4. **Hand-computed SMDs.** A four-row example with hand-derived unweighted
   and weighted SMDs (`test_balance_smd_hand_computed_arithmetic`).
5. **Cross-fit leakage detection (Case 24).** Folds rebuilt independently;
   per-complement propensity refits must reproduce the estimator's
   out-of-fold values exactly, and the leaky in-sample fit must differ —
   the check can fail if leakage is introduced.

## 6. Reproducibility, uncertainty, comparison

* Fixed seed → bit-identical estimates across runs; the point estimators are
  seed-independent; bootstrap intervals vary by seed only (Case 17).
* Bootstrap payloads record `refit_nuisance_models: true`, reps requested/
  succeeded/failed, seed, and percentile method; CIs cover the truth on the
  recovery DGPs; a 90% IF interval is strictly narrower than the 95% one on
  the same fit (Case 22).
* Comparison runs all three estimators on one shared cohort with one analysis;
  the payload states disagreement is reported, not resolved (no combined
  score, no winner selection).
* Weighted balance collapses after IPW on the confounded DGP (SMDs near 0
  post-weighting vs large pre-weighting).

## 7. API-level validation (Case 25 and lifecycle)

Real upload path → graph creation → validate/run/compare → run storage and
retrieval; 404 cross-dataset, 410 expiry (typed `expired_or_evicted`), 409
fingerprint conflict, 422 structured gate/schema refusals; staleness flips
only on structural edits (layout drags never stale a run).
