# S6 handoff

**Status: PARTIAL.** The mandatory S5 defect repairs are complete and verified;
F09 statistical work and F10 predictive modelling are implemented, integrated
and independently validated; core model diagnostics and preliminary subgroups
are delivered. The full F11 diagnostic workspace and confirmatory F15 analysis
remain. Nothing in those areas is simulated or advertised.

## Delivered

### 1. S6-A — the four reported defects (`52a2ef9`)

| Defect | Cause | Repair |
|---|---|---|
| Scatter page grew without bound | ResizeObserver wrote the container height back into the SVG it sized | Definite CSS plot height, read-only observer, equality guard, block SVG; measured 2174→2930 px before vs constant 1396 px after |
| Header hover unreadable | Global `button:hover` painted a light surface behind light text | Transparent nav/brand hover, explicit active+hover, celadon focus ring |
| Navigation implied skipped stages | Study/Explore numbered before Results while Data → Run Audit goes to Results | Audit results is stage 3; breadcrumb and per-stage next actions; optional stages labelled |
| Parallel coordinates opaque | No encoding explanation, count or brush affordance | Reading guide with annotated example, persistent hint, exact selection count, rail labels |

Evidence: `docs/S6_A_UI_REPAIRS.md`, `docs/screenshots/s6/{before,after,mobile,tablet}`,
`frontend/e2e/s6-ui-repairs.spec.ts`.

### 2. S6-B — F09 statistical workbench (`aec75e9`)

Explicit typed specification; statsmodels OLS and binary logistic regression;
coefficients, standard errors, intervals, statistics, p-values, odds ratios,
R²/adjusted R²/F/df/σ, log-likelihood/AIC/BIC/McFadden R², coding reference and
population; complete-case accounting; structured refusals; residual/VIF/
condition diagnostics; bounded run storage and export; Model Lab UI at step 6.
11 numerical oracles against numpy normal equations and a direct statsmodels
fit.

Evidence: `docs/S6_STATISTICAL_METHODS.md`, `docs/S6_NUMERICAL_VALIDATION.md`,
`docs/S6_MODEL_DIAGNOSTICS.md`, `frontend/e2e/s6-model-lab.spec.ts`.

### 3. S6-C — F10 predictive engine and Model Lab tab (this checkpoint)

* Split resolution from the confirmed study split or generated
  random/stratified/group/chronological holdout.
* A validation set carved from training rows with the same strategy family;
  fit / validation / test are disjoint and recorded with row-id digests.
* Leakage-safe scikit-learn pipelines: median/mode imputation and one-hot
  encoding fitted on fit rows only; final refit on fit + validation; test read
  exactly once after selection.
* Dummy baselines plus logistic and random forest (classification); dummy mean,
  linear, ridge and random forest (regression). No hyperparameter tuning.
* Real metrics: accuracy, balanced accuracy, confusion matrix, per-class
  precision/recall/F1, ROC-AUC, PR-AUC; MAE, RMSE, R², residual summary.
  Undefined values are named with a reason.
* Diagnostics: ROC curve, calibration bins, error cohort, residual sample and
  plots, per-class table.
* Preliminary subgroup table with exact test denominators, per-group metric,
  share, outcome mean, small-group warning and outside-bin count.
* Bounded run storage, JSON inspection/export, provenance and versions.
* Predictive tab in the Model Lab: evaluation design, candidate comparison
  (validation only), sealed-test metrics, diagnostics, subgroups and export.

Actual results on `clean_control.csv` (240 rows; fit 144 · validation 36 · test
60) are recorded in `S6_VERIFICATION.md`: the dummy prior wins validation
because the fixture's features are independent of the label; test accuracy is
0.400, ROC-AUC 0.500; regression MAE 0.950, RMSE 1.117, R² −0.063. These
unflattering numbers are reported as computed.

Evidence: `backend/app/models/prediction.py`,
`backend/tests/test_models_prediction.py` (8 oracles),
`backend/tests/test_models_prediction_api.py`,
`frontend/src/views/PredictiveLabView.tsx`,
`frontend/e2e/s6-prediction.spec.ts`,
`docs/screenshots/s6/after/predictive-*.png`.

## Verification ledger (final code)

| Suite | Result |
|---|---|
| Backend pytest | **360 passed** (351 previous + 9 new) |
| Synthetic audit oracle | **41/41 cases, 61/61 checks**, exit 0 |
| Frontend vitest | **82 passed** |
| TypeScript / ESLint / production build | clean (build emits a non-failing >500 kB chunk warning) |
| Playwright | **20 passed** (18 previous + 2 S6-C journeys) |

## Not delivered

* F11 remainder: Q–Q, leverage/Cook's/influence, calibration plot, PR plot,
  threshold analysis, permutation importance, partial dependence, learning
  curves, multiclass ROC.
* F15 confirmatory analysis: confidence intervals, multiplicity control,
  formal heterogeneity tests. Current subgroups are descriptive.
* Cross-validation, repeated holdouts, nested tuning or any hyperparameter
  search.
* Frontend unit tests specific to the predictive view; 1366/1920 captures for
  the statistical tab; Firefox/WebKit; forced-colours mode.

## Known limitations

One validation holdout per run. Categorical mode imputation plus one-hot
encoding; unknown test levels ignored; no interactions, splines, weights or
offsets. Classification threshold fixed at 0.5. Limits: 10,000 rows, 30
predictors, 30 categorical levels, 20 classes. Predictive metrics describe a
split and a fixture, not real-world validity, and are never causal effects.
Subgroups are preliminary and can be unstable when small.

## Next stage

Continue S6-D/F11 with the diagnostics listed above, adding an independent oracle
for each number before showing it. Exact commands, environment gotchas,
scientific constraints and the remaining task list are in
`docs/S6_AGENT_CONTINUATION.md`.

**Do not start S7 (causal DAG/estimation) until the remaining S6 work is accepted.**
