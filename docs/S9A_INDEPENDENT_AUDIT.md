# S9A independent scientific audit

**Auditor role:** independent causal-inference / numerical-verification review
of the completed S9A implementation (commit `158c833`), performed before S9B.
**Result:** 4 confirmed defects (3 HIGH, 1 MEDIUM) — all reproduced, repaired,
and covered by permanent regression tests. Final verdict in
`S9A_FINAL_VERIFICATION.md`.

## 1. Audit scope and method

* Line-by-line re-derivation of every estimator formula from the code, against
  the definitions (g-computation, Hájek IPW, the AIPW estimating equation,
  ratio-estimator influence functions, percentile bootstrap).
* An **independent audit harness** (`backend/tests/test_causal_estimation_audit.py`,
  16 tests) that re-implements the estimators with numpy + statsmodels only —
  `np.linalg.lstsq` g-computation, a from-scratch Hájek routine, and a fully
  independent statsmodels-GLM/OLS cross-fitted AIPW pipeline — and compares
  production output on known-effect DGPs. The harness never calls production
  estimator helpers to produce a reference.
* An **adversarial suite** (`backend/tests/test_causal_estimation_adversarial.py`,
  15 tests) attacking degenerate and hostile inputs, plus API-level bypass
  attempts and a no-500 sweep.
* Targeted reproduction scripts (run outside the test suite) for each suspected
  defect before any code was changed.

Starting state: branch `v2-premium-visual-foundation`, HEAD `158c833` (the S9A
implementation commit), working tree containing only unrelated screenshot
mtime churn and pre-existing scratch files — all preserved.

## 2. Mathematical audit findings (by estimator)

### A. Regression adjustment / g-computation — verified correct

* Potential-outcome predictions set the treatment feature to 1 and 0 for every
  cohort row; observed treatment values are never reused in the counterfactual
  predictions (verified by reading `_potential_outcome_predictions` and by the
  statsmodels-equality test: OLS g-computation equals the adjusted T
  coefficient exactly, 1e-8).
* Averaging is over the full prepared cohort (`rows_final`), the correct study
  population for the ATE.
* Treatment mapping is explicit; ambiguous encodings are refused with the
  unmatched values listed. Categorical confounders are one-hot encoded
  with a documented reference-level convention, cross-checked against a
  hand-built indicator encoding (`test_a5_...`).
* Binary outcomes are detected, explicitly recoded 0/1, and reported as
  probability differences; a `y = 2t` fixture is *correctly* classified as
  binary (the audit harness initially mis-flagged this as a bug — it is the
  documented behavior).
* No accidental use of the observed treatment in counterfactual predictions.

### B. IPW (Hájek) — verified correct

* Weights `T/e`, `(1−T)/(1−e)`; normalized arm means; ATE = difference.
  Recomputed independently from returned propensities to 1e-10.
* Influence-function SE re-derived: `φᵢ = n·wᵢ(Yᵢ−μ)/Σw` per arm, difference
  across arms — matches the standard ratio-estimator form; verified against a
  plain-numpy recomputation.
* Truncation is off by default; when requested it is counted, disclosed, and
  described as a biased trade. The machine-epsilon guard against division by
  zero is distinct from truncation and is now commented as such.
* No silent clipping anywhere; extremes are reported and warned.

### C. AIPW — verified correct

* Term-by-term check of `ψᵢ = m̂1 − m̂0 + T(Y−m̂1)/ê − (1−T)(Y−m̂0)/(1−ê)`
  against the estimating equation: correct, and demonstrably not the average
  of RA and IPW (`test_a3` agreement with a fully independent statsmodels
  cross-fit pipeline; the SEs also agree in magnitude).
* Treatment-specific outcome nuisances are fitted on the treated/control
  subsets of each *training* fold and predict out-of-fold; the propensity
  model likewise. Leakage re-verified by the original independent
  fold-rebuilding test, which also asserts the leaky in-sample fit differs.
* Fold construction is deterministic (seeded shuffled KFold, or GroupKFold
  with the group-count guard added by this audit).
* Small/imbalanced groups: per-fold arm minima raise a structured refusal
  (verified: 10 treated rows × 10 folds → `failed`, other estimators
  unaffected); single-class propensity folds now also refuse structurally
  (this audit's repair D3).

## 3. Confirmed defects, reproduction, and repairs

| ID | Severity | Defect | Reproduction | Repair + regression test |
|---|---|---|---|---|
| D1 | **HIGH** | A covariate containing a non-finite value (`inf`) passed the numeric parse (only NaN counted as unparsable), reached scikit-learn, and raised a raw `ValueError` → HTTP 500. | 300-row fixture, `x1[3]=inf`, run IPW → `ValueError: Input X contains infinity`. | `preparation.py`: non-finite parsed numeric covariate values are excluded under every policy with reason `invalid_covariate_value` and per-column counts. Test: `test_adversarial_inf_covariate_is_excluded_not_a_crash`. |
| D2 | **HIGH** | `GroupKFold` with fewer distinct groups than `cross_fit.splits` raised sklearn's `ValueError` → HTTP 500. | 3 groups, splits=5, AIPW → `ValueError: Cannot have number of splits...`. | `estimators.py::_crossfit_folds`: pre-check raises `EstimationFailure` with counts and a fix hint; surfaced as a per-estimator `failed` result. Test: `test_adversarial_too_few_groups_is_a_structured_failure`. |
| D3 | **HIGH** | A cross-fitting *training fold* containing a single treatment class (possible when groups align with treatment) crashed the propensity fit with a raw `ValueError` → HTTP 500. | Groups aligned with treatment, 2 folds → `ValueError: This solver needs samples of at least 2 classes`. | `estimators.py::estimate_aipw`: per-fold class guard raises a structured `EstimationFailure`. Additionally, `service.run_estimation` converts any residual library `ValueError` from the estimator layer into a per-estimator `failed` result — a data-driven degeneracy can never become a 500. Tests: `test_adversarial_single_class_propensity_fold_is_structured`, `test_api_adversarial_no_500_on_any_degenerate_input`. |
| D4 | **MEDIUM** | Under `median_mode`, balance SMDs were computed on the raw (NaN-carrying) frame and all reported `null`, even though the estimators used imputed values — a misleading diagnostic absence. | `median_mode` + one NaN covariate → `smd_unweighted: null`. | `service.py::_diagnostic_frame`: diagnostics run on median/missing-level imputed values mirroring the fitted pipelines; the payload carries a `diagnostic_imputation` disclosure; raw missingness is still reported per covariate. Test: `test_adversarial_median_mode_balance_is_defined`. |

No CRITICAL defects were found: no estimator formula error, no identification
bypass, no cohort mixing, no leakage.

## 4. Independent reference comparisons (16 harness tests, all passing)

1. Randomized known ATE (1.75): production RA == `lstsq` g-computation (1e-8);
   production IPW ≈ Hájek with the *true* e = 0.5; all three recover.
2. Randomized zero ATE: estimates near 0; CIs cover 0 (or are honestly
   unavailable for RA under the IF method).
3. Confounded known ATE (1.2): production AIPW vs the independent statsmodels
   cross-fit pipeline — estimates within 0.15, SEs within a factor 2; RA ==
   independent OLS reference.
4. Multiple confounders (0.9): all three recover.
5. Categorical confounder (1.0): all three recover; the hand-built
   indicator-encoding g-computation agrees.
6. Small deterministic example (24 rows): hand-derived exact value 2.0
   reproduced by all three estimators to 1e-5.
7. Severe imbalance (~89% treated, effect 0.8): all three recover, finite.
8. Near-positivity violation (separation): explicit warnings, extreme
   propensity summary, finite estimate.
9. Constant outcome: all estimates exactly 0, SE exactly 0 (where defined),
   no NaN anywhere (payload serialized with `allow_nan=False`).
10. Missing outcome/covariate rows: exclusion counts exact, rows reconcile,
    effect still recovered.
11. Strong association without a valid set: refused (`open_backdoor_path`).
12. Post-treatment (mediator) adjustment: refused with the structured
    violation.
13. Unobserved confounder: every proposed set refused.
14. Bootstrap: same seed → bit-identical CI; different seed → different;
    `refit_nuisance_models: true`; replicate failures counted.
15. Cross-fitted AIPW: same seed → identical estimate and SE.
16. Uncertainty arithmetic: `_z_critical` matches `scipy.stats.norm.ppf`; the
    90%/95% interval widths are in exact z-ratio; bootstrap percentile
    behavior verified against the mean of a known distribution.

## 5. Uncertainty, leakage, diagnostics, identification — audit results

* **Uncertainty.** Method–estimator pairing enforced (RA + IF → explicit
  unavailable state, never an invented interval); bootstrap refits every
  nuisance model per replicate; seeds resolved once, recorded
  (`resolved_seed`), and honored; confidence levels applied via exact z
  quantiles / percentile order statistics; zero variance → zero-width CI, not
  NaN; failed replicates counted and explained. The IPW IF treats the
  propensity as fixed — documented, typically conservative; the bootstrap is
  the alternative. Independence is assumed and stated in every payload;
  clustered inference is explicitly unsupported.
* **Leakage.** All preprocessing lives inside sklearn pipelines fitted only on
  fitting rows; AIPW nuisance predictions are out-of-fold by construction and
  verified by an independent fold-rebuilding test; `median_mode` imputation is
  fold-fitted; grouped cross-fitting is supported with the new group-count
  guard; the payload warns when shuffled folds are used without a group
  column. No leakage found. The original leakage-audit engine is untouched
  (oracle: 41/41 cases, 61 checks).
* **Diagnostics.** SMD denominators re-derived (population-form pooled
  variance, applied identically pre/post — now stated verbatim in the payload
  note); ESS (Kish) recomputed; propensity quantiles/extremes recomputed;
  weighted-vs-unweighted SMD collapse verified on a confounded DGP; low SMDs
  are never described as proof of exchangeability in any payload.
* **Identification integration.** No bypass exists: the gate re-evaluates the
  named set with S8C's exact criterion server-side (fingerprint mismatch →
  409; post-treatment/unobserved/open-path sets → 422 with violations; cyclic
  graphs cannot be stored at all, so estimation can never see one; expired
  datasets → typed 410; cross-dataset graph references → 404). A truncated
  (incomplete) adjustment *search* does not block estimation of a separately
  verified named set — verified end-to-end on a 15-candidate graph
  (`search_status: incomplete`, estimation proceeds). Layout-only edits never
  stale a stored run; structural edits do.

## 6. Residual limitations (documented, not defects)

* Nuisance models are fixed, named, L2-regularized linear/logistic pipelines;
  no hyperparameter search or semiparametric learners.
* The AIPW augmentation divides by `ê` clipped only at machine epsilon;
  extreme fitted scores therefore produce extreme influence values — by
  design, and flagged by the overlap diagnostics. Explicit truncation remains
  opt-in and biased.
* IPW/AIPW intervals assume independent observations; clustered/longitudinal
  standard errors are out of scope (group-aware *folding* is supported).
* SMDs use the population-form variance convention (now documented in the
  payload); other software may use the n−1 form, giving slightly different
  magnitudes for small samples.
* Duplicate rows are not deduplicated or warned about in estimation (the
  platform's duplicate auditing is a separate, pre-existing feature).

## 7. Conclusions

Justified: the three estimators compute the estimands their documentation
claims, under the verified adjustment sets, with honest uncertainty and
diagnostics; identification cannot be bypassed; failures are structured.

Not justified (and never claimed): any causal interpretation without
exchangeability/consistency/positivity; positivity verification from data;
balance thresholds as confounding tests; any p-value.
