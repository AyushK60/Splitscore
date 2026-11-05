# S9A numerical algorithms

Implementation reference for every number S9A produces. Module map:
`app/causal/estimation/` — `contracts.py` (bounds, request schema),
`preparation.py` (cohort, treatment, outcome, covariates), `estimators.py`
(nuisance models + the three estimators), `uncertainty.py` (intervals),
`diagnostics.py` (balance, overlap), `service.py` (gate + orchestration).

## 1. Notation and data

Cohort of `n` rows with: treatment `T ∈ {0,1}` (explicit two-value mapping),
outcome `Y ∈ ℝ` (binary outcomes are explicitly recoded to 0/1 and the coding
recorded), and covariates `X` (the verified adjustment set's columns). Numeric
covariates are parsed to float64; categorical covariates are stripped text
levels (≤12), one-hot encoded with `handle_unknown="ignore"` and an explicit
missing level `__splitscope_missing__`.

## 2. Nuisance models

* **Propensity** `e(x) = P(T = 1 | X = x)`: scikit-learn `LogisticRegression`
  (L2 penalty, `C = 1.0`, lbfgs, `max_iter = 1000`) inside a pipeline.
  With an empty adjustment set the model is intercept-only, so `e` is the
  marginal treated fraction — the correct propensity for a randomized design.
* **Outcome** `m(t, x) = E[Y | T = t, X = x]`: `LinearRegression` for a
  continuous outcome; `LogisticRegression` (same settings) for a binary one,
  predicting the probability of the coded-1 outcome (never the class label).
  AIPW uses treatment-specific models `m1`/`m0` fitted on the treated/control
  subsets of each training fold.
* **Preprocessing** (inside the pipelines, never outside): numeric — median
  imputation then `StandardScaler`; categorical — constant imputation then
  one-hot. Fitted only where the enclosing model is fitted (see §4).

## 3. Estimators (all target the ATE)

**Regression adjustment (g-computation).** Fit `m(t, x)` with the treatment
as a design feature on the whole cohort. Predict `m(1, X_i)` and `m(0, X_i)`
for every cohort row:

    ATE_RA = (1/n) Σᵢ [ m(1, Xᵢ) − m(0, Xᵢ) ]

Reported with both modeled potential-outcome means. The raw T coefficient of
this fit is never presented as the effect. (For a linear outcome with no
interactions, OLS g-computation equals the adjusted regression coefficient —
the property used for the independent cross-check.)

**IPW (Hájek / normalised).** Fit `e(x)`. Weights `w1 = T/e`, `w0 = (1−T)/(1−e)`:

    μ1 = Σ wᵢYᵢ / Σ wᵢ   over T = 1,   μ0 = Σ wᵢYᵢ / Σ wᵢ   over T = 0
    ATE_IPW = μ1 − μ0

Truncation (clipping `e` to a client-specified `[lower, upper]` with
`0.01 ≤ lower ≤ 0.49 < 0.51 ≤ upper ≤ 0.99`) is **off by default**; when
requested it is applied, counted, and labelled as a biased-but-lower-variance
trade. Scores are never clipped silently.

**AIPW (cross-fitted).** K folds (default 5, ≤10): shuffled `KFold` seeded by
the recorded seed, or `GroupKFold` when `cross_fit.group_column` names a
repeated-entity column. On each training fold, fit `e`, `m1`, `m0`; predict
out-of-fold `ê(Xᵢ), m̂1(Xᵢ), m̂0(Xᵢ)` for the held-out fold. The pseudo-outcome
is the AIPW estimating equation itself:

    ψᵢ = m̂1(Xᵢ) − m̂0(Xᵢ) + Tᵢ (Yᵢ − m̂1(Xᵢ))/ê(Xᵢ)
                          − (1 − Tᵢ)(Yᵢ − m̂0(Xᵢ))/(1 − ê(Xᵢ))
    ATE_AIPW = (1/n) Σ ψᵢ

This is not the average of two estimators; double robustness is a property of
this form. A training fold short of either arm raises a structured failure
(never a substitute formula), reported per-estimator while other estimators in
the same comparison still run.

**Double robustness, honestly stated:** consistency of AIPW holds when either
the propensity model or the outcome models are correctly specified, under the
identification assumptions and regularity conditions. It does **not** protect
against unmeasured confounding, positivity failure, or a wrong graph.

## 4. Leakage rules

All preprocessing lives inside sklearn pipelines fitted only on fitting rows.
For AIPW every fold's nuisances are fitted on that fold's training rows only,
so row *i*'s nuisance values come from models that never saw row *i* —
verified by `test_case_24_crossfit_nuisance_predictions_are_out_of_fold`,
which rebuilds the folds independently, refits the propensity on each
complement, and requires equality with the estimator's out-of-fold values
(and asserts the leaky in-sample fit *differs*, so the check can fail).
Bootstrap replicates resample rows and refit every nuisance model; no
transformation is ever fitted on a held-out fold.

## 5. Uncertainty

* **Influence-function (AIPW):** `SE = std(ψ, ddof=1)/√n`; normal-approximation
  interval `ATE ± z_{1−α/2}·SE`. Valid under cross-fitting + regularity.
* **Influence-function (IPW):** ratio-estimator influence function with the
  propensity treated as fixed:
  `φᵢ = n·w1ᵢ(Yᵢ − μ1)/Σw1 − n·w0ᵢ(Yᵢ − μ0)/Σw0`, `SE = std(φ)/√n`.
  Conservative when the propensity model is correctly specified.
* **Bootstrap (any estimator):** percentile interval from `reps` (100–2000)
  replicates, each a *full refit* on a seeded multinomial resample. Replicates
  that fail are counted; below 60% success the interval is returned
  **unavailable** next to the point estimate. Bootstrapping a fixed point
  estimate is never done.
* RA has no closed-form influence function in this implementation; requesting
  one returns an explicit unavailable state. Intervals assume independent
  observations; the payload warns that clustered data need cluster-aware
  inference S9A does not provide. No p-values anywhere.

## 6. Diagnostics

* **Balance.** Per covariate (and per category level for categoricals, via
  binary indicators): SMD = (mean_T − mean_C)/√((var_T + var_C)/2), computed
  unweighted and, when propensity weights exist, Hájek-weighted. Weighted
  variance uses `Σw(x − x̄_w)²/Σw`. Degenerate denominators report `null`,
  never a fake zero.
* **Overlap.** Propensity min/max/quantiles overall and by arm; counts outside
  [0.01, 0.99]; max and quantiles of total weights; Kish ESS per arm
  `(Σw)²/Σw²`; explicit warnings for extremes, near-separation of arm
  distributions, and ESS below 25% of the arm's row count.

## 7. Computational bounds (enforced before fitting)

Max 10 000 cohort rows; min 20 total / 10 per arm; ≤30 covariates; ≤12
categorical levels; ≤300 encoded design columns; bootstrap 100–2000 reps;
cross-fitting 2–10 splits. Exceeding a bound is a typed error (`413` for
limits, `422` for structure), never a silent subsample.
