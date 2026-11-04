# S6 verification

**Date:** 2026-11-04 (final verification after the last code and test change)
**Branch:** `v2-premium-visual-foundation`
**Starting HEAD:** `3867199` (S6-C)
**Checkpoints:** S6-A `52a2ef9`; S6-B `aec75e9`; S6-C `3867199`; this S6-D/E
completion is the commit that adds this revision.

**Overall status: PASS for the approved S6 exit gate.** F09 remains intact; F10
predictive modelling is preserved; F11's prioritised diagnostics (binary PR/AP,
calibration, Q–Q, fitted-vs-residual, OLS influence and coefficient uncertainty,
test-partition permutation importance) are implemented with independent tests;
and S6-scoped F15 subgroups now carry explicit uncertainty and denominators. The
full F11 blueprint also lists learning curves, threshold exploration,
heteroskedasticity tests and local explanations; those are deferred and are
**not** claimed as delivered. Their status is recorded below.

## Automated verification (final code)

| Check | Command | Result |
|---|---|---|
| Backend tests | `../.venv/Scripts/python.exe -m pytest -q` in `backend` | **363 passed**, 3 warnings (2 deliberate numpy divide warnings in the singular-design test, 1 pre-existing Starlette/httpx deprecation) |
| Predictive tests | `pytest tests/test_models_prediction.py -q` | **11 passed** |
| Synthetic audit oracle | `../.venv/Scripts/python.exe scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks**, exit 0 |
| Frontend unit tests | `npm test -- --run` | **90 passed** (9 files, including 8 new predictive-diagnostic component tests) |
| TypeScript | `npm run typecheck` | clean |
| ESLint | `npm run lint` (`--max-warnings 0`) | clean |
| Production build | `npm run build` | clean; non-failing chunk-size warning (>500 kB) |
| Playwright E2E | `SPLITSCOPE_E2E_PORT=8194 npx playwright test` | **21 passed** (18 previous + 3 S6 predictive journeys) |

The Playwright `webServer` runs `python -m app.main`, so E2E needs the repository
virtual environment on `PATH`:

```bash
export PATH="/e/Splitscore V2/.venv/Scripts:$PATH"
cd frontend
SPLITSCOPE_E2E_PORT=8194 npx playwright test
```

Port 8123 is held by an unrelated process; the committed default is unchanged.
Port 8194 was used for the final run.

## F11 acceptance

| Requirement | Status | Evidence |
|---|---|---|
| Binary precision–recall curve from held-out labels and scores | **PASS** | `metrics.pr_curve` from the sealed test probabilities; curve and AP rendered only when binary and both classes present |
| Average precision / PR-AUC with exact definition | **PASS** | `average_precision`, `pr_auc` and `pr_auc_definition`; documented as `Σ (R_n − R_{n−1})P_n`, not trapezoid; independently recomputed by hand in the test |
| Positive-class prevalence and sample counts | **PASS** | `prevalence`, `positive_count`, `negative_count`; checked against stored labels |
| Calibration/reliability plot | **PASS** | Ten equal-width bins; mean predicted probability, observed rate, count and Wilson 95% interval; empty bins retained as empty |
| Calibration metrics | **PASS** | Brier, ECE and MCE computed from stored probabilities; independently reconstructed |
| Single-class / insufficient-sample handling | **PASS** | PR/ROC emitted as `null` with a stated reason; a dedicated single-class test partition test asserts no curve is fabricated |
| Regression Q–Q | **PASS** | Ordered raw test residuals vs `(i − 0.5)/n` normal positions; sample size, plotted count and method stated; not shown for dummies without residuals variance |
| Fitted-vs-residual | **PASS** | Stored held-out fitted values and residuals; sampled rows with stated stride |
| Leverage and Cook's distance where supported | **PASS** | Unpenalised OLS selected model only; refit design; formula, thresholds, counts and top rows stored; inapplicable for dummy/ridge/tree |
| Coefficient/uncertainty visualization | **PASS** | OLS refit coefficients, classical SE, 95% t intervals, statistic and p-value, with an explicit in-sample label |
| Inferential vs predictive distinction | **PASS** | Separate statistical and predictive tabs, separate partitions and captions; influence labelled in-sample |
| Test-partition permutation importance | **PASS** | Sealed test, 5 fixed-seed repeats, mean RMSE increase or balanced-accuracy drop, SD; never used for selection; descriptive warning |
| Diagnostics identify model, partition, population, method, exclusions and limitations | **PASS** | Stored fields plus UI context/captions for each panel; unsupported states state a reason |
| No fabricated plots or quantities | **PASS** | Every panel is rendered from returned arrays; tests recompute the numbers; hardcoded images are absent |
| Learning curves | **Deferred** | Not part of the prioritised exit-gate core; requires repeated refits and a larger runtime/UI budget |
| Threshold exploration | **Deferred** | Classifier threshold remains fixed at 0.5; no validation-frozen threshold table or test-set tuning |
| Heteroskedasticity checks / robust SE | **Deferred** | Classical SE only; VIF and condition number are not error-structure tests |
| Partial dependence / local explanations | **Deferred** | Explicitly later scope in the blueprint; not simulated |
| Multiclass ROC/PR and calibration | **Deferred** | Curves are binary-only; unsupported states are explicit |

## F15 preliminary acceptance

| Requirement | Status | Evidence |
|---|---|---|
| Valid subgroup uncertainty | **PASS (preliminary)** | Accuracy: Wilson 95% interval; regression MAE: normal-approximation 95% interval; single-row interval left undefined |
| Explicit sample-size warnings | **PASS** | Flag below 20 rows or 5% of test; warning text names both thresholds |
| Correct class/support denominators | **PASS** | `n`, `metric_denominator`, `share`, `positive_count`, `negative_count`, `outcome_mean`; tested to sum to test rows |
| Small, empty and undefined subgroups | **PASS** | Empty categorical levels/numeric bins retained with `n=0` and null metrics; outside-bin count; undefined interval reason |
| Comparison limitations | **PASS** | Stored note states intervals are unadjusted for multiplicity and differences are not causal |
| Synchronized with selected model | **PASS** | Subgroups are computed from the selected model's stored test predictions, not a parallel fit |
| Causal CATE / heterogeneity inference | **Not attempted** | Explicitly out of S6; no causal claim is made |

## Independent numerical oracles

The tests recompute values from stored predictions and independently built
design matrices. They do not import the production metric helpers.

| Oracle | What is independently checked |
|---|---|
| Confusion/metrics | Matrix rebuilt by hand; accuracy, per-class precision/recall/F1 and balanced accuracy recomputed |
| PR/AP | Scores sorted by hand with tied scores merged; AP computed as `Σ (R_n − R_{n−1})P_n`, not with `average_precision_score` |
| Calibration | Bins rebuilt with `np.digitize`; counts, observed rates, empty bins, Brier and ECE recomputed |
| Subgroup uncertainty | Wilson interval recomputed from `correct` and `n`; denominators and outcome support reconciled |
| Preprocessing boundary | Learned median equals fit-row median and differs from the global median under a test-only shift |
| Sealed selection | Candidates carry validation only; selected score is the best validation score; refit rows = fit + validation; one test evaluation |
| Reproducibility | Two runs give identical metrics, predictions, learned preprocessing and split |
| Regression/Q–Q/influence | MAE/RMSE/R² recomputed; Q–Q quantiles rebuilt; leverage and Cook's distance rebuilt from `XᵀX`, residuals and MSE |
| Single-class test | PR/AP/ROC are null with an explicit reason and no invented curve |
| Group split | Published split reproduced; train/test entity sets disjoint |
| Refusals | Structured errors for invalid specifications |
| Strict JSON | Stored payloads serialize with `json.dumps(..., allow_nan=False)`; HTTP export round-trips |
| HTTP route | Demo load → prediction without visiting Study; stored run; strict export |

## Actual held-out results

### Clean control — classification

`clean_control.csv`, 240 rows, confirmed chronological split, 25% test;
partitions fit 144 · validation 36 · test 60. Selected model: **dummy prior**
because the fixture's features are independent of `label`.

| Quantity | Actual value |
|---|---|
| Test accuracy | 0.4000 |
| Balanced accuracy | 0.5000 |
| ROC-AUC | 0.5000 |
| Average precision (PR-AUC) | 0.6000 |
| Prevalence | 0.6000 (36 positive, 24 negative) |
| Confusion matrix | `[[24, 0], [36, 0]]` for classes `0`, `1` |
| Brier score | 0.2523 |
| ECE / MCE | 0.1111 / 0.1111 |
| Non-empty calibration bins | 1 (all 60 rows in 0.4–0.5, observed rate 0.600, Wilson 47.4%–71.4%) |

The one-bin calibration result and AP equal to prevalence are the honest
consequences of a constant dummy prediction, not a rendering defect; the UI
states that a single bin cannot describe calibration shape.

Subgroups by `segment`: alpha 25 rows, accuracy 0.320 (Wilson 17.2%–51.6%);
beta 15 rows, accuracy 0.333 (15.2%–58.3%, small-group warning); gamma 20 rows,
accuracy 0.550 (34.2%–74.2%). Denominators sum to 60.

### Clean control — regression

`x1 ~ x2 + x3 + segment`; selected **dummy mean**, constant prediction 0.2419.
Test MAE **0.9501**, RMSE **1.1171**, R² **−0.0633** over 60 rows. Q–Q is
available for the 60 finite test residuals. Influence and permutation importance
show explicit “not applicable” states because the selected model is a dummy.
The negative R² is real and displayed.

### Signal-bearing regression — `chronology_violation`

`sensor_a + sensor_b → throughput`, existing seed split, 360 rows; partitions
fit 210 · validation 52 · test 98. Selected **linear regression** by validation
−RMSE (−25.1687); refit on 262 rows.

| Quantity | Actual value |
|---|---|
| Test MAE / RMSE | 18.9967 / 23.3255 |
| Test R² | 0.4905 |
| Q–Q | 98 residuals, 98 plotted points |
| Influence partition | fit + validation, n=262, p=3, residual df=259 |
| Leverage above 2p/n / 3p/n | 11 / 2 |
| Cook's D above 4/n / above 1 | 6 / 0 |
| Max leverage / max Cook's D | 0.03998 / 0.06117 |
| Coefficients (95% CI) | const 353.90 [350.70, 357.10]; sensor_a 11.93 [8.25, 15.61]; sensor_b 19.44 [15.76, 23.12] |
| Permutation importance | sensor_b +12.58 RMSE (SD 0.565); sensor_a +3.10 (SD 0.624); 98 test rows, 5 repeats |

Influence is explicitly in-sample on the refit design. Importance is explicitly
descriptive on the sealed test partition and was computed after the single test
evaluation.

## Browser journeys and visual QA

`frontend/e2e/s6-prediction.spec.ts`:

1. **Classification journey** — PR curve/AP, calibration table, subgroup
   intervals, export. Assertions include positive counts, PR/curve consistency,
   Wilson bounds, subgroup denominators summing to test n and strict export.
2. **Clean regression journey** — MAE/RMSE/R², Q–Q and residual plots, explicit
   unsupported influence/importance states.
3. **Signal-bearing regression journey** — real OLS influence values, coefficient
   intervals and permutation-importance rows on the test partition.

The full Playwright run also covers the Scatter infinite-growth regression,
header hover contrast, audit stage navigation, parallel-coordinates brushing,
S5 audit/similarity workflows, uploads, error recovery and the statistical Model
Lab. **21 passed.**

Screens reviewed at 1920, 1366 and 390 px:
`docs/screenshots/s6/after/diagnostics-pr-1920.png`,
`diagnostics-calibration-1366.png`, `diagnostics-subgroups-1366.png`,
`diagnostics-influence-1920.png`, `diagnostics-importance-1920.png`,
`docs/screenshots/s6/mobile/diagnostics-pr.png`.

Defects found and fixed during visual review: PR label collision; oversized
diagnostic charts; subgroup warning clipping at 1366; ambiguous permutation
baseline/column wording; a one-bin calibration curve lacking a caveat; captures
taken mid-scroll.

## Defects found and fixed during S6-D/E

| Defect | Found by | Fix |
|---|---|---|
| PR curve had no plotted AP/prevalence/counts | Initial diagnostic implementation review | Added PR plot and stored prevalence/count fields; AP identity stated |
| Calibration lacked uncertainty and only used raw bins | Numerical review | Added Wilson per-bin intervals, Brier/ECE/MCE and empty-bin states |
| Regression had no Q–Q or influence | F11 gap review | Added Q–Q, OLS leverage/Cook's and coefficient intervals with applicability guards |
| Importance wording did not name the metric direction | Screenshot review | Labels now say baseline RMSE and “Mean RMSE increase” (or balanced-accuracy drop) |
| One-bin calibration could imply a full curve | Screenshot review | Added an explicit one-bin limitation caption |
| Subgroup warning column clipped at 1366 px | Screenshot review | Fixed-layout table with wrapped warning cells |
| Export could hide non-finite Q–Q/influence values | Strict-JSON audit | Finite guards plus `allow_nan=False` assertions |

## Honest limitations

* One split per run; no cross-validation, repeated holdouts or nested tuning.
* Classification threshold is fixed at 0.5. No threshold selection or threshold
  table is implemented (deferred; would require validation-only selection and a
  frozen test threshold).
* Categorical predictors use most-frequent imputation and one-hot encoding;
  unknown test levels are ignored. No target encoding, interactions or splines.
* Influence and coefficient intervals apply only to the unpenalised OLS refit;
  they are in-sample and do not describe held-out or causal effects.
* PR/ROC/calibration are binary-only. Learning curves, partial dependence, local
  explanations, multiclass curves, heteroskedasticity tests and multiplicity
  adjustment are deferred; none is simulated or advertised.
* F15 remains predictive and descriptive: unadjusted subgroup intervals, small
  groups flagged rather than modelled, no CATE or causal heterogeneity claim.
* Limits: 10,000 rows, 30 predictors, 30 categorical levels, 20 classes, 2,000
  stored test predictions, 100 ROC/PR points, 200 Q–Q points, 500 influence
  points, 2,000 importance rows and 20 importance predictors.
* Chromium only; forced-colours mode and screen readers were not tested.
* No training on real user data was performed. Demo numbers do not establish
  real-world performance.

## Overall

**PASS for the approved S6-D/E exit gate.** The prioritised F11 diagnostics and
S6-scoped F15 preliminary uncertainty are implemented from genuine held-out
computations, independently tested, browser-verified and documented. The
remaining advanced F11 capabilities are explicitly deferred, are not required by
this S6 checkpoint's prioritised scope, and are not claimed as delivered. S7 has
not been started.
