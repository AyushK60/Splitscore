# S6 numerical validation

**Statistical oracles:** `backend/tests/test_models_statistics.py` (11 tests).
**Predictive oracles:** `backend/tests/test_models_prediction.py` (11 tests).
**Full backend suite:** 363 passed, 3 warnings.

```bash
cd backend
../.venv/Scripts/python.exe -m pytest tests/test_models_statistics.py -q
../.venv/Scripts/python.exe -m pytest tests/test_models_prediction.py -q
```

The expectations are recomputed from stored predictions, row ids and
independently built design matrices. The predictive tests do not import the
production metric helpers. Average precision and Wilson intervals are
recomputed by hand, not by the scikit-learn functions used in production.

## Statistical workbench oracles

### Oracle 1 — OLS normal equations

Fixture: 60 rows, two continuous predictors, a fixed seed. The test solves

```
β = (XᵀX)⁻¹ Xᵀy            (numpy)
σ² = RSS / (n − p)
SE(β) = sqrt(diag(σ² (XᵀX)⁻¹))
t = β / SE,  p = 2 · t.sf(|t|, n − p)
CI = β ± t.ppf(0.975, n − p) · SE
```

and compares every coefficient, standard error, interval, statistic and p-value
with the API result. R² is recomputed from residuals and SST.

**Tolerances:** coefficient 1e-8, standard error 1e-8, statistic and intervals
1e-7, p-value 1e-9, R² 1e-10.

The test also checks that residual diagnostics reconcile exactly
(`residual = observed − fitted`, tolerance 1e-9) and that no odds ratio is
attached to an OLS term.

### Oracle 2 — OLS without an intercept

The design is rebuilt by hand with only the two predictors and solved with
numpy; the module's no-intercept coefficients must match. The intercept model is
asserted to differ, so the flag is not merely cosmetic.

### Oracle 3 — logistic reference implementation

Fixture: 400 rows, one continuous and one binary predictor, seeded Bernoulli
outcome. The test fits `statsmodels.Logit` directly on the same design and
compares coefficients (1e-6), standard errors (1e-5), odds ratios (relative
1e-9), log-likelihood (1e-8) and McFadden pseudo-R² (1e-9). Orientation is
asserted: a positive coefficient must have OR > 1 and correspond to the
generative direction. The test also asserts that `r_squared` is absent from the
logistic fit statistics.

### Oracle 4 — categorical coding

A three-level category with a declared reference `b`:

* terms contain `cat[a]` and `cat[c]` and never `cat[b]`;
* the coding record returns reference `b` and levels `[a, b, c]`;
* the formula records `C(cat, Treatment('b'))`;
* a hand-built dummy matrix solved with numpy reproduces both dummy
  coefficients within 1e-8;
* the recovered group offset is close to the generative value (0.15 tolerance,
  reflecting sampling noise).

### Guardrail tests

Each asserts a structured refusal (not a silent alteration):

* single-class logistic outcome;
* two-level outcome without an explicit positive level (levels listed);
* constant outcome;
* constant predictor;
* exactly collinear predictors (rank deficiency, duplicate-term candidates);
* duplicate predictor and unknown outcome column;
* fewer rows than the minimum for the parameter count;
* more than 12 categorical levels;
* complete-case `fail` policy with excluded-row counts.

Missingness is separately tested: 3 excluded rows are counted, analysed rows are
`24 − 3 = 21`, and per-column counts are exactly `{x1: 2, y: 1}`.

### Reproducibility

Two fits on the same dataset and specification return identical coefficients and
an identical diagnostic sample.

## Predictive engine oracles

### Hand-computed confusion matrix and classification metrics

The test rebuilds the confusion matrix from the stored row predictions and
recomputes accuracy, per-class precision, recall, F1 and balanced accuracy with
numpy. Predictions cover every test row exactly once, and the matrix totals
equal the reported test `n`.

### PR/AP, calibration counts and calibration summaries

Using the stored positive-class probabilities and observed labels, the test
first sorts scores descending and merges tied scores. It then computes average
precision directly as

```
AP = Σ_n (recall_n − recall_{n−1}) · precision_n
```

with `recall_{-1} = 0`. This is asserted to equal both `metrics.average_precision`
and `metrics.pr_auc` within 1e-12. It does **not** call
`average_precision_score`, so a swapped or mis-scaled stored score would fail.

The same test independently rebuilds the ten equal-width calibration bins with
`np.digitize`, checks every bin count and observed rate, confirms empty bins have
null rates, checks total bin rows equal the test `n`, and recomputes Brier score
and ECE from the stored probabilities. It also verifies each Wilson interval
contains its observed rate.

### Preprocessing boundary

A fixture has a deliberate test-only feature shift and missing values. The
learned numeric median is asserted to equal the median of the **fit rows** and to
differ from the global median. The result records that preprocessing was fitted
on the fit partition. This catches an imputer silently fitted before the split.

### Sealed selection

Candidates contain only validation information. The selected family is
recomputed as the maximum validation score, the selected score equals that
maximum, `test_evaluations == 1`, and the refit row count equals fit +
validation. Partitions sum to the full dataset.

### Reproducibility

Two complete runs on the same dataset and specification produce identical
metrics, row predictions, learned preprocessing and split metadata.

### Regression metrics, Q–Q and OLS influence

From stored test predictions, the test recomputes MAE, RMSE, R², residual
summary, and checks `n`. It also verifies:

* Q–Q sample coordinates equal the sorted residuals;
* theoretical quantiles equal `norm.ppf((i − 0.5)/n)` from SciPy;
* the reference line intercept and slope equal the residual mean and sample SD;
* for the OLS refit, `XᵀX` is rebuilt with an intercept, and leverage and Cook's
  distance are recomputed from the normal equations and residual MSE;
* `max_leverage`, `max_cooks`, the largest-Cook row values and coefficient
  terms/intervals agree with the API result.

The stored payload is also serialized with `json.dumps(..., allow_nan=False)`.

### Subgroup denominators and uncertainty

The test verifies:

* group counts sum exactly to the test rows and each row's denominator equals
  its `n`;
* each reported `share` equals `n / test_rows`;
* positive and negative counts sum to `n` and `outcome_mean` equals the
  positive-class rate;
* the subgroup accuracy CI equals an independently computed Wilson interval from
  `correct` and `n`;
* every row below 20 rows or 5% of the test partition carries a small-subgroup
  warning;
* the comparison note states that intervals are unadjusted and differences are
  not causal.

Numeric subgroup bins are separately tested for an empty bin (`n = 0`, null
metric and interval) and for rows outside the declared range.

### Single-class held-out partition

A fixture has both classes in training but only the negative class in the test
partition. The test asserts that prevalence and positive count are zero, PR/AP
and ROC are `null` rather than invented, no PR curve is emitted, and
`metrics.undefined` explains that both classes are required.

### Guarded refusals and group isolation

The predictive tests also cover structured refusals (invalid family, duplicate
or missing predictors, too little data, subgroup mistakes) and verify that a
generated group split keeps entity sets disjoint.

## What this does **not** validate

* Only classical standard errors are tested; robust/cluster SEs do not exist.
* No formal normality or heteroskedasticity test is implemented; the Q–Q plot is
  a visual diagnostic and is checked numerically, not as an inference procedure.
* Influence formulas are checked on an OLS fixture, not on every possible design;
  unsupported models are asserted to return an inapplicable state.
* Permutation importance is checked for partition, finiteness and a positive
  signal, not for a population-level causal ranking.
* Subgroup intervals are checked for arithmetic, not for coverage under
  multiplicity or dependence.
* Fixtures are generated inside the test modules from fixed seeds rather than
  committed as CSVs; they are deterministic and reproducible.
* Synthetic fixtures establish that the described estimator is computed
  correctly, not that a real dataset satisfies its assumptions.
