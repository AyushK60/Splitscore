# S6 verification

**Date:** 2026-11-03 (final run after the last code change)
**Branch:** `v2-premium-visual-foundation`
**Checkpoints:** S6-A `52a2ef9`; S6-B `aec75e9`; S6-C is the commit that adds
this file.
**Overall status: PARTIAL** — the four S5 defects are repaired, F09 is complete,
F10 predictive modelling is implemented and browser-verified, and genuine model
diagnostics plus preliminary subgroups are implemented. The full F11 workspace
(influence diagnostics, Q–Q, learning curves, permutation importance, PR plot)
and confirmatory F15 analysis remain open. Nothing unimplemented is simulated or
advertised.

## Automated verification (last run, final code)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` (backend) | **360 passed**, 3 warnings (2 numpy divide warnings in the deliberate singular-design test, 1 pre-existing Starlette/httpx deprecation) |
| Synthetic audit oracle | `python scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks, exit 0** |
| Frontend unit tests | `npm run test` | **82 passed** (8 files) |
| TypeScript | `npm run typecheck` | clean |
| ESLint | `npm run lint` (`--max-warnings 0`) | clean |
| Production build | `npm run build` | clean; non-failing chunk-size warning (>500 kB) |
| Playwright E2E | `SPLITSCOPE_E2E_PORT=8188 npx playwright test` | **20 passed** (18 previous + 2 S6-C journeys) |

New backend coverage: 8 engine oracles in `tests/test_models_prediction.py` plus
1 HTTP regression in `tests/test_models_prediction_api.py` (360 = 351 + 9).

The Playwright `webServer` runs `python -m app.main`, so E2E requires the
repository virtual environment on `PATH`:

```bash
export PATH="/e/Splitscore V2/.venv/Scripts:$PATH"
cd frontend
SPLITSCOPE_E2E_PORT=8188 npx playwright test
```

Port 8123 is held by an unrelated process; the committed default is unchanged.

## F10 acceptance (predictive engine)

| Requirement | Status | Evidence |
|---|---|---|
| Split resolved before fitting | **PASS** | Existing confirmed study split, or generated `random`/`stratified`/`group`/`chronological`; the resolved split and partition counts are stored in the run |
| Leakage-safe preprocessing | **PASS** | Median/mode imputation and one-hot encoding live inside a scikit-learn `Pipeline`/`ColumnTransformer` fitted on fit rows only; final refit uses fit + validation |
| Test partition sealed | **PASS** | `test_evaluations = 1`; candidates carry validation scores only; test is read once after selection |
| Baselines and fitted models | **PASS** | Classification: dummy prior, logistic regression, random forest. Regression: dummy mean, linear, ridge, random forest |
| Reproducible comparison | **PASS** | Fixed seeds and settings reported; repeated-run oracle gives identical metrics, predictions, split and learned preprocessing |
| Classification metrics | **PASS** | Accuracy, balanced accuracy, confusion matrix, per-class precision/recall/F1/support, ROC-AUC, PR-AUC where defined |
| Regression metrics | **PASS** | MAE, RMSE, R² (undefined when test outcome has zero variance), residual summary |
| Undefined metrics are honest | **PASS** | `metrics.undefined` lists the metric and reason; nothing is defaulted to zero |
| Diagnostics | **PASS** | ROC curve, ten-bin calibration table, error cohort with probabilities, residual sample and plots, per-class table |
| Preliminary subgroups (F15 scope) | **PASS (preliminary)** | Explicit test denominators, per-group metric, share, outcome mean, small-group warning, outside-bin count |
| Run storage and export | **PASS** | Bounded model-run store; `GET /api/models/runs/{id}` and `/export`; export is strict JSON, identical to the stored payload |
| Refusals, not silent changes | **PASS** | Missing split, missing/incorrect positive class, constant predictor, too few rows/classes, >30 predictors/categories, >20 classes, numeric subgroup without bins, unknown model family, failed candidates |

## Independent numerical oracles

The tests do not reuse production metric helpers.

| Oracle | What is independently checked |
|---|---|
| Confusion/metrics | Matrix rebuilt by hand from stored row predictions; accuracy, per-class precision/recall/F1 and balanced accuracy recomputed |
| Preprocessing boundary | Learned numeric median equals the training-row median and differs from the global median on a fixture with a test-only distribution shift |
| Sealed selection | Candidates contain no test field; selected score equals the best validation score; refit rows = fit + validation; one test evaluation |
| Reproducibility | Two identical runs produce identical metrics, predictions, split and learned preprocessing |
| Regression | MAE, RMSE and R² recomputed with numpy from the stored test predictions |
| Subgroups | Group counts sum exactly to test rows; small-group warning tied to the stated rule |
| Group split | Published split reproduced independently; train/test entity sets are disjoint |
| Refusals | Structured errors for invalid specifications |
| HTTP route | Demo load → prediction without visiting Study; stored run; strict JSON export |

## Actual held-out results on the bundled clean control

`clean_control.csv`, 240 rows, confirmed chronological split, 25% test. A single
validation holdout (20% of training) is carved before fitting.

### Classification: `label ~ x1 + x2 + x3 + segment`

Partitions: fit 144 · validation 36 · test 60.

| Candidate | Validation balanced accuracy |
|---|---:|
| Dummy prior | 0.5000 |
| Logistic regression | 0.4752 |
| Random forest | 0.3901 |

Selected: **dummy prior**. Test accuracy **0.4000**, balanced accuracy
**0.5000**, ROC-AUC **0.5000**, PR-AUC **0.6000**, confusion matrix
`[[24, 0], [36, 0]]` (classes `0`, `1`).

The clean-control features are generated independently of `label` by design, so
a baseline winning is the expected, honest outcome, not a model failure. The
confusion matrix and the 40% accuracy are the actual held-out result.

Preliminary test subgroups by `segment`: alpha 25 rows, accuracy 0.320; beta 15
rows, accuracy 0.333 with a small-subgroup warning; gamma 20 rows, accuracy
0.550. Denominators sum to 60.

### Regression: `x1 ~ x2 + x3 + segment`

Selected: **dummy mean**, constant prediction 0.2419. Test MAE **0.9501**, RMSE
**1.1171**, R² **−0.0633** over 60 rows. The negative R² is real: the predictors
are unrelated to `x1` in this fixture. It is displayed rather than hidden.

## Browser journeys

`frontend/e2e/s6-prediction.spec.ts`:

1. **Classification journey** — classification on `label`, positive class `1`,
   existing split, subgroup `segment`; real confusion matrix, ROC plot, candidate
   comparison and export. The exported run's confusion counts sum to the reported
   test n; predictions contain every test row; candidates have no test field;
   subgroup counts sum to test n.
2. **Regression journey** — regression on `x1`; real MAE/RMSE/R², residual plot
   with 60 plotted rows, export, selected model.

Screens reviewed (not just test output):
`docs/screenshots/s6/after/predictive-classification-1920.png`,
`predictive-classification-1366.png`, `predictive-regression.png`,
`docs/screenshots/s6/mobile/predictive-controls.png`,
`predictive-results.png`.

## Defects found and fixed during S6-C

| Defect | Found by | Fix |
|---|---|---|
| Prediction endpoint returned HTTP 500 | New browser journey | Missing `fit_prediction` import in `routes_models.py`; fixed and covered by an HTTP test |
| Opening Model Lab directly lost the demo split (HTTP 422) | Browser journey after the import fix | Seed the demo's manifest roles and split labels at prediction time, as the Study route does |
| Export returned HTTP 500 | Browser export step | sklearn ROC thresholds start at `+inf`, which strict JSON rejects; publish finite thresholds only; strict-JSON assertion added |
| Candidate settings clipped at 1366 px | Screenshot review | Parameters moved to a disclosure below the comparison table |
| Constant dummy prediction produced colliding min/max labels | Screenshot review | One explicit “constant prediction” label |
| Stage guidance still described only statistical fits | Screenshot review | Guidance now distinguishes statistical vs held-out metrics and denies causation |

## Honest limitations

* One split per run; no cross-validation, repeated holdouts or nested tuning.
  No hyperparameter search is performed.
* Categorical predictors use most-frequent imputation and one-hot encoding;
  unknown test levels are ignored. No target encoding, interactions or splines.
* Classification threshold is 0.5; no threshold analysis. Calibration is a table,
  not a plotted curve; PR-AUC is reported without a PR plot; ROC is binary only.
* No permutation importance, partial dependence, Q–Q, leverage, Cook's distance,
  influence plots or learning curves — these are the remaining F11 work.
* F15 is descriptive: no confidence intervals, multiplicity control or causal
  heterogeneity claim. Small groups are flagged, not modelled.
* Limits: 10,000 rows, 30 predictors, 30 categorical levels, 20 classes, 2,000
  stored test predictions per run.
* Frontend unit tests were not added for the predictive view; it is covered by
  two Playwright journeys plus the typechecker. Predictive 1366/1920 and mobile
  captures exist; the statistical tab still lacks 1366/1920 captures.
* Chromium only; no forced-colours testing.
* No training on real user data was performed. Demo numbers do not establish
  real-world performance.

## Overall

**PARTIAL.** S6-C (F10), the implemented part of S6-D, and S6-E verification are
delivered, committed and documented. The full F11 diagnostic workspace and
confirmatory F15 analysis remain. S7 has not been started.
