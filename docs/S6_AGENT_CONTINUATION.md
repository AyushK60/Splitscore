# S6 agent continuation

**Written:** 2026-11-04. This file is the durable handoff; do not assume any chat
context is available.

## Repository and exact state

* **Authoritative repository:** `E:\Splitscore V2`
* **Branch:** `v2-premium-visual-foundation`
* **Starting HEAD:** `3867199` (S6-C). The S6-D/E completion is the commit that
  adds this revision; its parent is `3867199`.
* **S6 status:** PASS for the approved S6-D/E exit gate. S7 has not started.
* **Uncommitted work:** none after the S6-D/E commit, apart from pre-existing
  untracked files that must be preserved and are not S6:
  `docs/screenshots/s3/_preview/`, `docs/screenshots/s5/_preview/`,
  `import requests.txt`, `scripts/_patch_s3_hero.py`.
* **Stash:** one pre-existing `stash@{0}: S3 checkpoint: all S3 work staged,
  pre-verification`. Do not apply or drop it blindly.

**Critical:** the editor workspace may open `E:\Splitscore`, which is a stale
pre-S3 copy. Work in `E:\Splitscore V2`.

## Environment and commands that actually work

```bash
cd "/e/Splitscore V2"
export PATH="/e/Splitscore V2/.venv/Scripts:$PATH"   # REQUIRED for Playwright

cd backend
python -m pytest -q                                    # 363 passed, 3 warnings
python -m pytest tests/test_models_prediction.py -q    # 11 passed
cd ..
python scripts/evaluate_synthetic.py                   # 41/41 cases, 61/61 checks

cd frontend
npm test -- --run                                      # 90 passed (9 files)
npm run typecheck && npm run lint && npm run build
SPLITSCOPE_E2E_PORT=8194 npx playwright test           # 21 passed
```

Why the `PATH` line: the Playwright `webServer` runs `python -m app.main`, and
`statsmodels`/`scikit-learn` are installed only in the repository `.venv`.
Port 8123 is held by an unrelated process; `8180`–`8194` were used successfully.

Python 3.11.9 · pandas 3.0.6 · numpy 2.4.6 · scikit-learn 1.9.1 · scipy 1.17.1 ·
statsmodels 0.15.0 · Node 24.22.0.

## What is complete and verified

**S6-A — all four user-reported defects: PASS.** Scatter height is stable and
loop-free (measured 2174→2930 px before, constant 1396 px after); header hover
contrast ≥ 4.5:1; audit is stage 3 with breadcrumb and next steps; parallel
coordinates has progressive guidance and reconciled counts.

**S6-B — F09 statistical workbench: PASS for its declared scope.**
statsmodels OLS/logistic with coefficients, intervals, p-values, odds ratios,
fit statistics, VIF/condition diagnostics, residual plot, coding, population,
warnings, bounded run storage and export. 11 numerical oracles.

**S6-C — F10 predictive engine: PASS.**
`backend/app/models/prediction.py` implements typed configuration, split
resolution, a validation carve, leakage-safe `Pipeline`/`ColumnTransformer`,
one sealed test evaluation after validation selection, candidate comparison,
classification/regression metrics with undefined states, confusion/per-class/
ROC/calibration/error-cohort/residual/subgroup diagnostics, provenance, run
storage and strict-JSON export.

**S6-D/E — F11 prioritised diagnostics and F15 preliminary uncertainty: PASS.**

* Binary PR curve and average precision, with AP defined as step-wise
  `Σ (R_n − R_{n−1})P_n`; prevalence and positive/negative counts.
* Ten-bin calibration/reliability with Wilson 95% intervals, Brier, ECE and MCE;
  empty-bin and one-bin states honest.
* Regression Q–Q of test residuals and fitted-vs-residual.
* OLS leverage/Cook's distance, thresholds, counts, top rows and classical
  coefficient 95% intervals only for a selected unpenalised linear model, on the
  fit+validation refit design (in-sample).
* Test-partition permutation importance, five fixed-seed repeats, descriptive;
  never used for selection.
* Subgroups with Wilson/normal-approximation 95% intervals, exact denominators,
  support counts, empty/undefined states and unadjusted-comparison caveat.
* `frontend/src/components/PredictiveDiagnostics.tsx` and dedicated unit tests;
  three Playwright predictive journeys; six new screenshots.
* Backend **363 passed**; frontend **90 passed**; Playwright **21 passed**;
  synthetic oracle **41/41 cases, 61/61 checks**; typecheck/lint/build clean.

Key files:

* `backend/app/models/prediction.py` — diagnostics and importance.
* `backend/tests/test_models_prediction.py` — 11 independent predictive oracles.
* `backend/tests/test_models_prediction_api.py` — HTTP/strict-JSON regression.
* `frontend/src/views/PredictiveLabView.tsx` — wiring and captions.
* `frontend/src/components/PredictiveDiagnostics.tsx` — reusable charts/tables.
* `frontend/tests/PredictiveDiagnostics.test.tsx` — 8 component tests.
* `frontend/e2e/s6-prediction.spec.ts` — 3 journeys.
* `docs/S6_{MODEL_DIAGNOSTICS,NUMERICAL_VALIDATION,VISUAL_QA,VERIFICATION,HANDOFF}.md`.

## What is NOT implemented (do not claim otherwise)

* Learning curves.
* Threshold exploration/table; the classification threshold is fixed at 0.5 and
  no test-set threshold tuning exists.
* Breusch–Pagan/White heteroskedasticity tests and robust/cluster SEs.
* Partial dependence and local explanations.
* Multiclass ROC/PR/calibration.
* Multiplicity-adjusted subgroup intervals or formal heterogeneity tests.
* Cross-validation, repeated holdouts, nested tuning or hyperparameter search.
* Causal CATE/heterogeneity analysis.
* S7: not started, by instruction.

These are later-scope capabilities. They are not S6 gate blockers under the
approved prioritised F11 scope (A: PR/AP + calibration; B: Q–Q/residual +
supported OLS influence/uncertainty; C: test-partition permutation importance).

## Exact next action for a new agent

1. If asked to continue S6 polish, add only the deferred diagnostics above,
   each with an independent oracle before display. Do not rewrite the predictive
   engine or move preprocessing outside the training-fitted pipeline.
2. If asked to start S7, begin the causal DAG/identification stage. Do not reuse
   predictive coefficients as causal effects, and do not convert subgroup error
   differences into treatment-effect heterogeneity.
3. Before any commit, rerun the verification block above and inspect
   `git status`; preserve the pre-existing untracked files and stash.

## Architecture decisions to preserve

* All preprocessing is learned inside the training-fitted pipeline. Never fit an
  imputer, encoder or scaler on the full frame.
* Candidates compare on validation. The selected model is refitted on
  fit + validation and evaluated once on test. Never tune on test.
* A statistical fit and a predictive evaluation are different products and stay
  visually separate.
* Influence and OLS coefficient intervals are in-sample on the refit rows and are
  never labelled held-out or causal.
* PR/AP are binary-only. AP is step-wise average precision, not trapezoidal area.
* Permutation importance is computed after the single test evaluation, on the
  stated test partition, and is descriptive only.
* Subgroup intervals are unadjusted; small/empty groups are flagged, not
  presented as discoveries.
* Refuse rather than silently alter a specification. Count every exclusion.
* Undefined metrics are named with a reason, never defaulted.
* Strict JSON: no NaN/infinity in a stored or exported payload.
* Demo manifests seed roles and split labels when Model Lab is opened directly;
  this is documented configuration, not inference.
* Model results clear when the dataset identity changes.
* Keep the S6-A chart rule: a measuring chart must not derive its container
  height from the SVG it sizes.
* Navigation order (Start 1, Data 2, Audit results 3, Study 4, Explore 5, Model
  Lab 6, Compare 7, Export 8) is asserted in `e2e/s6-ui-repairs.spec.ts`.

## Browser QA findings

* Real Chromium journeys: classification diagnostics/export, clean regression
  unsupported states, and signal-bearing regression influence/importance pass.
* Fixed during review: PR label collision; oversized diagnostic charts; subgroup
  warning clipping at 1366; ambiguous importance baseline wording; missing
  one-bin calibration caveat; mid-scroll captures.
* Captures: `docs/screenshots/s6/after/diagnostics-{pr-1920,calibration-1366,
  subgroups-1366,influence-1920,importance-1920}.png`,
  `docs/screenshots/s6/mobile/diagnostics-pr.png`.
* Not covered: Firefox/WebKit, forced-colours, screen readers.

## Known warnings / non-failures

* `pytest` reports 3 warnings: two numpy divide warnings from the deliberate
  singular-design correlation probe, one Starlette/httpx deprecation.
* `npm run build` warns that the bundle exceeds 500 kB; the build exits 0.
* `git` emits LF→CRLF notices on Windows; harmless.
