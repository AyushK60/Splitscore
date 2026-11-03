# S6 predictive ML evaluation contract (F10)

**STATUS: CONTRACT ONLY — NOT IMPLEMENTED.**

No scikit-learn estimator is trained by SplitScope in this checkpoint. There are
no predictive metrics, no baseline-vs-model comparison and no ML diagnostics in
the UI. This document exists so that the next agent implements F10 against a
fixed, testable contract rather than inventing one. Nothing here may be
advertised as working until the acceptance tests at the end pass.

## 1. Task definition

* `classification` — binary or multiclass outcome.
* `regression` — numeric outcome.

The outcome must be selected explicitly. Classification requires a user-chosen
positive class for binary tasks; multiclass class ordering must be recorded.
Class support and the full class list are reported with every metric set.

## 2. Evaluation design

Every run declares, before fitting:

* the split source: existing split column, or a generated assignment stored by
  S5 (`SplitPlan` / assignment ids), including seed and strategy;
* train / validation / test membership as **immutable row id lists**;
* whether group or temporal constraints apply;
* the preprocessing configuration and the estimator configuration;
* the random seed(s).

Rules:

1. Split membership is established **before** any preprocessing is fitted.
2. The test partition is sealed: it is not read for imputation, scaling,
   encoding vocabularies, feature selection, threshold selection or
   hyperparameter tuning.
3. Hyperparameters are chosen with training/validation or cross-validation on
   training only. A single final test evaluation is recorded, with the number of
   test evaluations performed.
4. If no valid held-out partition exists (too few rows, one class in test, group
   leakage that cannot be prevented), the run is refused or reported as
   `not_evaluable` — never silently evaluated on training rows.
5. A random split is not automatically valid for repeated entities or temporal
   data. Group and chronological plans from S5 are preferred when the roles are
   declared.

## 3. Preprocessing isolation (non-negotiable)

All learned transformations live inside a scikit-learn `Pipeline` /
`ColumnTransformer` fitted on training data only:

* imputation statistics,
* scaling and centering,
* one-hot vocabularies and target/ordinal encodings,
* feature selection,
* any resampling (e.g. class weighting must not resample the test partition).

A deliberate leakage fixture must demonstrate that a naive global
preprocessing implementation receives a different (better) test score than the
pipeline implementation, and that the pipeline is the one reported. Tests must
assert the **fit boundary**, not only that metrics exist.

## 4. Model families (initial, validated only)

Classification: dummy prior/most-frequent baseline, logistic regression,
random forest, one regularised linear model.
Regression: dummy mean/median baseline, linear regression, ridge/lasso,
random forest.

No model may be listed in the UI until it has a passing numerical oracle. Model
names without validated computation are prohibited.

## 5. Metrics

Classification: accuracy, per-class precision/recall/F1 with support, confusion
matrix, ROC-AUC for valid binary probabilistic setups, PR-AUC where appropriate,
calibration diagnostics when probabilities exist. Undefined metrics (absent
class, no positive predictions, multiclass ROC unsupported) are reported as
`undefined` with the reason — never as zero.

Regression: MAE, RMSE, R² where defined, residual distribution and
residual-versus-fitted diagnostics.

Every metric set carries: task, partition (`validation` or `test`), sample size,
class counts, estimator class and hyperparameters, seed, preprocessing summary
and run id. Training metrics are labelled as training metrics.

## 6. Comparison

Side-by-side comparisons require identical task, evaluation population and
partition. Incompatible comparisons are refused and explain why. A larger
metric does not establish scientific validity, and the UI must say so.

## 7. Provenance and export

The run record includes dataset fingerprint, target, predictor set,
future-only/excluded features declared by the study, split plan and row-id
membership, seed, preprocessing, estimator class and hyperparameters, library
versions, warnings, run id and timestamps. Export produces JSON plus a
human-readable summary; figures must be derived from the stored predictions.

## 8. Resource bounds

Bounded rows, predictors, estimators, folds and stored runs. No unbounded
processing and no execution of user-supplied code or formulas.

## 9. Acceptance tests for the future implementation

* Known linear fixture: model coefficients and metrics reproduce an independent
  scikit-learn computation within stated tolerances.
* Known classification fixture: confusion matrix counts reconcile exactly to
  evaluated row ids; precision/recall/F1 recomputed independently.
* Preprocessing leakage fixture: pipeline test metric differs from the naive
  global-preprocessing metric; the reported one is the pipeline's.
* Group/temporal fixture: a random split yields an invalid/optimistic result
  while the constrained split is used for the reported evaluation.
* Sealed test: changing a hyperparameter after final evaluation requires a new
  run id, and the test metric used for selection is recorded as a violation.
* Dataset replacement clears all previous predictions.
* A single-class or too-small test partition is refused with an explanation.

Until these exist and pass, SplitScope has a **statistical** workbench, not a
predictive ML engine.
