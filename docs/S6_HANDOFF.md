# S6 handoff

**Status: PASS for the approved S6-D/E exit gate.** S6-A defect repairs, S6-B
statistical workbench and S6-C predictive engine are preserved. F11's prioritised
diagnostics and preliminary F15 subgroup uncertainty are delivered, independently
tested, browser-verified and documented. Advanced diagnostics explicitly listed
below remain deferred and are not claimed.

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
condition diagnostics; bounded run storage and export; Model Lab UI.
11 numerical oracles against numpy normal equations and a direct statsmodels fit.

### 3. S6-C — F10 predictive engine (`3867199`)

* Split resolution from the confirmed study split or generated
  random/stratified/group/chronological holdout.
* Validation set carved from training rows with the same strategy family;
  fit/validation/test disjoint and recorded with row-id digests.
* Leakage-safe pipelines: median/mode imputation and one-hot encoding fitted on
  fit rows only; final refit on fit + validation; test read exactly once.
* Dummy/linear/logistic/ridge/random-forest candidates; no hyperparameter tuning.
* Real metrics, confusion matrix, per-class table, calibration, ROC, error cohort,
  residual sample and preliminary subgroup table.
* Bounded run storage, strict-JSON inspection/export, provenance and versions.

### 4. S6-D/E — F11 diagnostics and F15 uncertainty (this checkpoint)

**Binary classification**

* PR curve from sealed-test labels and positive-class scores.
* Average precision explicitly defined as `Σ (R_n − R_{n−1})P_n`; `pr_auc` kept as
  a compatibility alias. This is not trapezoidal PR area.
* Prevalence and positive/negative counts from actual held-out labels.
* Ten-bin calibration/reliability table with Wilson 95% intervals on observed
  rates; Brier, ECE and MCE.
* Empty bins shown as empty; when only one non-empty bin exists, the UI states
  that calibration shape cannot be assessed.
* Single-class/insufficient cases produce null curves with a reason; no invented
  plot or zero score.

**Regression**

* Normal Q–Q of raw sealed-test residuals with `(i − 0.5)/n` plotting positions,
  sampled points, reference mean + SD × z and explicit non-normality caveat.
* Residual-versus-fitted diagnostics from stored held-out predictions.
* OLS leverage/Cook's distance and coefficient intervals only for a selected
  unpenalised linear model. Computed on the transformed **fit + validation**
  refit design; explicitly in-sample, not held-out or causal.
* Thresholds (`2p/n`, `3p/n`, `4/n`, `1`), counts, maximum influence, top rows,
  rank, residual df and condition number exposed.
* Dummy/ridge/tree selections show “not applicable” rather than influence values.

**Permutation importance**

* Runs on the sealed test partition after the single evaluation.
* Five fixed-seed repeats; mean RMSE increase or balanced-accuracy drop, with SD.
* Partition, row count, baseline metric and repeats stored and shown.
* Never used for selection; explicitly descriptive and non-causal; correlated
  predictors can share or mask importance.

**F15 preliminary subgroups**

* Wilson 95% accuracy intervals for classification; normal-approximation 95% MAE
  intervals for regression (undefined for a one-row group).
* Exact `n`, `metric_denominator`, `share`, positive/negative counts and
  outcome measure; support reconciles to the test partition.
* Empty groups and numeric bins retained with `n=0` and null metrics; outside-bin
  count reported.
* Warnings below 20 rows or 5% of test; unadjusted multiplicity caveat and no
  causal-heterogeneity claim.
* Synced to the selected model's stored predictions.

**UI and tests**

* `PredictiveDiagnostics.tsx` supplies reusable PR, reliability, Q–Q, influence,
  importance and subgroup components.
* Chart sizing, legends, axes, captions, unsupported states and subgroup-table
  wrapping added without redesigning the workbench.
* 8 dedicated frontend unit tests; 3 Playwright predictive journeys.
* Real screenshots at 1920, 1366 and 390 px reviewed.

## Verification ledger (final code)

| Suite | Result |
|---|---|
| Backend pytest | **363 passed**, 3 warnings |
| Predictive module | **11 passed** |
| Synthetic audit oracle | **41/41 cases, 61/61 checks**, exit 0 |
| Frontend vitest | **90 passed** (9 files) |
| TypeScript / ESLint / production build | clean (build emits a non-failing >500 kB chunk warning) |
| Playwright | **21 passed** |

Commands and exact environment notes are in `docs/S6_AGENT_CONTINUATION.md`.

## Deferred — not claimed, not S6 gate blockers

* Learning curves.
* Descriptive threshold exploration / a validation-frozen threshold table. The
  classifier threshold remains fixed at 0.5; no test-set tuning exists.
* Heteroskedasticity checks (Breusch–Pagan/White) and robust/cluster SEs.
* Partial dependence and local explanations.
* Multiclass ROC/PR/calibration.
* Multiplicity-adjusted subgroup intervals and formal heterogeneity tests.
* Cross-validation, repeated holdouts and hyperparameter search.

These are later-scope capabilities. The prioritised S6 F11 core (PR/AP,
calibration, Q–Q, fitted-vs-residual, supported OLS influence/uncertainty,
test-partition importance) and preliminary F15 uncertainty are satisfied.

## Known limitations

One validation holdout per run; categorical mode imputation plus one-hot;
unknown test levels ignored; no interactions, splines, weights or offsets;
classification threshold fixed at 0.5. Influence/coefficient intervals are
in-sample OLS only. PR/ROC/calibration are binary-only. Subgroup intervals are
unadjusted and unstable when small. Metrics describe a split and a fixture, not
real-world validity, and are never causal effects. Limits: 10,000 rows, 30
predictors, 30 categorical levels, 20 classes, 2,000 stored test predictions,
100 curve points, 200 Q–Q points, 500 influence points, 2,000 importance rows,
20 importance predictors.

## Next stage

S6 is accepted for the approved scope. The next stage is S7 (causal DAG and
identification), which has **not** been started. A future agent may add the
deferred diagnostics as later-scope work, but must not present them as S6
deliverables.

**Do not start S7 without an explicit instruction.**
