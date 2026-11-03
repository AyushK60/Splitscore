# S6 numerical validation

**Test module:** `backend/tests/test_models_statistics.py` (11 tests, all pass).
**Run:** `cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_models_statistics.py -q`.

The expectations are computed independently of the production code. No test
calls `fit_statistics` to derive its own expected values.

## Oracle 1 — OLS normal equations

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

## Oracle 2 — OLS without an intercept

The design is rebuilt by hand with only the two predictors and solved with
numpy; the module's no-intercept coefficients must match. The intercept model is
asserted to differ, so the flag is not merely cosmetic.

## Oracle 3 — logistic reference implementation

Fixture: 400 rows, one continuous and one binary predictor, seeded Bernoulli
outcome. The test fits `statsmodels.Logit` directly on the same design and
compares coefficients (1e-6), standard errors (1e-5), odds ratios (relative
1e-9), log-likelihood (1e-8) and McFadden pseudo-R² (1e-9). Orientation is
asserted: a positive coefficient must have OR > 1 and correspond to the
generative direction. The test also asserts that `r_squared` is absent from the
logistic fit statistics.

## Oracle 4 — categorical coding

A three-level category with a declared reference `b`:

* terms contain `cat[a]` and `cat[c]` and never `cat[b]`;
* the coding record returns reference `b` and levels `[a, b, c]`;
* the formula records `C(cat, Treatment('b'))`;
* a hand-built dummy matrix solved with numpy reproduces both dummy
  coefficients within 1e-8;
* the recovered group offset is close to the generative value (0.15 tolerance,
  reflecting sampling noise).

## Guardrail tests

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
`24 − 3 = 21`, and the per-column counts are exactly `{x1: 2, y: 1}`.

## Reproducibility

Two fits on the same dataset and specification return identical coefficients and
an identical diagnostic sample.

## What this does **not** validate

* No predictive model has been trained, so no train/test metric has an oracle
  yet (see `S6_ML_EVALUATION_CONTRACT.md`).
* Only classical standard errors are tested; robust/cluster SEs do not exist.
* The logical fixtures are small by design. They establish that the described
  estimator is computed correctly, not that a real dataset satisfies its
  assumptions.
* Synthetic fixtures 3–5 required by the S6 brief (preprocessing leakage,
  group/temporal split, subgroup error) are **not** built, because F10/F15 are
  not implemented. Building them without the engine would be theatre.
* Fixtures 1 and 2 exist as generated test data inside the test module, not as
  committed CSVs in `datasets/`; they are deterministic and reproducible from
  the seed in the test.
