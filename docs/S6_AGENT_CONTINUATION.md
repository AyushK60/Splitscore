# S6 agent continuation

**Written:** 2026-11-03. This file is the durable handoff; do not assume any chat
context is available.

## Repository and exact state

* **Authoritative repository:** `E:\Splitscore V2`
* **Branch:** `v2-premium-visual-foundation`
* **HEAD:** the S6-C commit that adds this file. Its parent is `3e1e3fb`
  (S6 handoff), before that `aec75e9` (S6-B) and `52a2ef9` (S6-A).
* **Uncommitted work:** none, apart from pre-existing untracked files that must
  be preserved and are not S6:
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

cd backend && python -m pytest -q                     # 360 passed
cd .. && python scripts/evaluate_synthetic.py         # 41/41 cases, 61/61 checks

cd frontend
npm run test                                          # 82 passed
npm run typecheck && npm run lint && npm run build
SPLITSCOPE_E2E_PORT=8188 npx playwright test          # 20 passed
```

Why the `PATH` line: the Playwright `webServer` runs `python -m app.main`, and
`statsmodels`/`scikit-learn` are installed only in the repository `.venv`.
Port 8123 is held by an unrelated process; `8180`–`8188` were used successfully.

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

**S6-C/S6-D — F10 predictive engine and core diagnostics: PASS.**
`backend/app/models/prediction.py` now implements:

* typed `PredictionConfig`;
* split resolution from the confirmed study split or generated
  random/stratified/group/chronological strategies;
* a validation carve inside the training rows using the same strategy family;
* scikit-learn `Pipeline`/`ColumnTransformer` fitted on fit rows only; a final
  refit on fit + validation; the test partition is read exactly once;
* dummy baselines plus logistic/random forest (classification) and
  linear/ridge/random forest (regression);
* classification and regression metrics with undefined values marked;
* confusion matrix, per-class metrics, ROC curve, calibration bins, error
  cohort, residual sample/summary, preliminary subgroup table;
* strict-JSON export, provenance, row-membership digests and warnings.

API: `POST /api/datasets/{id}/models/prediction`; runs and export reuse
`GET /api/models/runs/{id}[/export]`.

UI: `frontend/src/views/PredictiveLabView.tsx`, reachable from the Model Lab
tabs (statistical inference / predictive ML), with evaluation design, candidate
comparison, test metrics, diagnostics, subgroups, provenance and export.

## What is NOT implemented (do not claim otherwise)

* **F11 remainder:** Q–Q, leverage/Cook's distance/influence, learning curves,
  permutation importance, partial dependence, PR curve plot, calibration plot,
  threshold analysis, multiclass ROC, statistical tests on error cohorts.
* **F15 confirmatory:** confidence intervals, multiplicity control, formal
  heterogeneity tests. Current subgroups are descriptive and flagged when small.
* **Robustness:** no cross-validation, repeated splits, nested tuning or
  hyperparameter search. One validation holdout is used.
* **Predictive frontend unit tests:** none; Playwright and typecheck cover it.
* **S7:** not started, by instruction.

## Exact next action for a new agent

1. Extend F11 with the remaining diagnostics, each computed from the stored
   fitted pipeline or the sealed test partition and labelled with its partition:
   * Q–Q and scale-location for regression;
   * leverage/Cook's distance only if the design matrix is retained safely;
   * permutation importance on test **only** with the partition stated, or skip
     it rather than implying causality;
   * PR curve and calibration plot for binary classification;
   * threshold table if added.
2. Add oracles for every new number before displaying it. Reuse the fixture and
   strict-JSON discipline in `tests/test_models_prediction.py`.
3. Then, and only then, extend F15 beyond descriptive subgroups. Do not convert
   subgroup error differences into causal claims.
4. Update `S6_VERIFICATION.md`, this file and `S6_HANDOFF.md`; rerun the full
   verification block above; commit.

## Architecture decisions to preserve

* All preprocessing is learned inside the training-fitted pipeline. Never fit an
  imputer, encoder or scaler on the full frame.
* Candidates compare on validation. The selected model is refitted on
  fit + validation and evaluated once on test. Never tune on test.
* A statistical fit and a predictive evaluation are different products and stay
  visually separate.
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

* Real Chromium journeys: classification and regression both pass and export
  strict JSON.
* Fixed during review: candidate settings clipped at 1366 px; colliding
  constant-prediction axis labels; stage guidance that mentioned only
  statistical fits.
* Captures: `docs/screenshots/s6/after/predictive-classification-{1366,1920}.png`,
  `predictive-regression.png`, `docs/screenshots/s6/mobile/predictive-{controls,results}.png`.
* Not covered: Firefox/WebKit, forced-colours, screen readers.

## Known warnings / non-failures

* `pytest` reports 3 warnings: two numpy divide warnings from the deliberate
  singular-design correlation probe, one Starlette/httpx deprecation.
* `npm run build` warns that the bundle exceeds 500 kB; the build exits 0.
* `git` emits LF→CRLF notices on Windows; harmless.
