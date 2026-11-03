# S6 agent continuation

**Written:** 2026-11-03. This file is the durable handoff; do not assume any chat
context is available.

## Repository and exact state

* **Authoritative repository:** `E:\Splitscore V2`
* **Branch:** `v2-premium-visual-foundation`
* **HEAD when written:** `aec75e9` (S6-B). The commit that adds this file is
  documentation-only.
* **Checkpoints:**
  * `52a2ef9` — S6-A: scatter growth, header contrast, audit-first navigation,
    parallel-coordinates guidance.
  * `aec75e9` — S6-B: statsmodels OLS/logistic engine, Model Lab UI, oracles.
* **Uncommitted work:** none, apart from pre-existing untracked files that must
  be preserved and are not S6:
  `docs/screenshots/s3/_preview/`, `docs/screenshots/s5/_preview/`,
  `import requests.txt`, `scripts/_patch_s3_hero.py`.
* **Stashes:** none.

**Critical:** the editor workspace may open `E:\Splitscore`, which is a stale
pre-S3 copy (HEAD `8c4b540`, no S4/S5 explorer). Work in `E:\Splitscore V2`.

## Environment and commands that actually work

```bash
cd "/e/Splitscore V2"
export PATH="/e/Splitscore V2/.venv/Scripts:$PATH"   # REQUIRED for Playwright

cd backend && python -m pytest -q                     # 351 passed
cd .. && python scripts/evaluate_synthetic.py         # 41/41 cases, 61/61 checks

cd frontend
npm run test                                          # 82 passed
npm run typecheck && npm run lint && npm run build
SPLITSCOPE_E2E_PORT=8180 npx playwright test          # 18 passed
```

Why the `PATH` line: the Playwright `webServer` runs `python -m app.main`.
`statsmodels` is installed only in the repository `.venv`; without the venv on
`PATH`, the server fails with `ModuleNotFoundError: statsmodels` (this was hit
and diagnosed during S6-B). Port 8123 is held by an unrelated process on this
machine; `8180` is the working port. The committed default is unchanged.

Python 3.11.9 · pandas 3.0.6 · numpy 2.4.6 · scikit-learn 1.9.1 · scipy 1.17.1 ·
statsmodels 0.15.0 (new, pinned in `backend/requirements.txt` and
`requirements.lock.txt`) · Node 24.22.0.

## What is complete and verified

**S6-A — all four user-reported defects: PASS.**
Scatter height is stable and loop-free (measured 2174→2930 px growing before,
constant 1396 px after); header hover contrast ≥ 4.5:1 in every state; the audit
is stage 3 with a breadcrumb and contextual next steps; parallel coordinates has
progressive reading guidance and reconciled selection counts. Covered by
`frontend/e2e/s6-ui-repairs.spec.ts` (4 tests) and
`docs/S6_A_UI_REPAIRS.md`.

**S6-B — F09 statistical workbench: implemented and validated.**
`backend/app/models/{contracts,statistics}.py`, `backend/app/api/routes_models.py`,
`backend/tests/test_models_statistics.py` (11 oracles), and
`frontend/src/views/ModelLabView.tsx` (OLS/logistic configuration, coefficients,
intervals, odds ratios, fit statistics, VIF/condition diagnostics, residual
plot, warnings, coding, population, export). Run storage reuses the bounded
in-memory store with `RunKind = "audit" | "comparison" | "model"`.

## What is NOT implemented (do not claim otherwise)

* **F10 predictive ML:** no scikit-learn estimator is trained, no metric is
  computed, no train/validation/test plan is executed. The contract is in
  `docs/S6_ML_EVALUATION_CONTRACT.md`.
* **F11 (most):** no Q–Q, leverage/Cook's distance, calibration, ROC/PR,
  confusion matrix, threshold analysis, permutation importance, learning curves.
* **F15 subgroups:** nothing.
* **Synthetic fixtures 3–5** from the brief (preprocessing leakage, group/time
  split, subgroup error) are not built.
* **S6-C, S6-D, S6-E** were not started.

## Exact next action for a new agent

Implement F10 in this order, testing each step before moving on:

1. Create `backend/app/models/prediction.py` with:
   * typed `PredictionConfig` (`task`, outcome, positive class, predictors,
     model family, split source, seed, preprocessing options);
   * split membership resolution from the S5 study record / assignment (exact
     row ids, train/validation/test), refusing when no valid held-out partition
     exists;
   * scikit-learn `Pipeline`/`ColumnTransformer` constructions where imputation,
     scaling and encoding are fitted **only** on training rows;
   * dummy baselines plus logistic/linear and random-forest estimators.
2. Add `backend/tests/test_models_prediction.py` **before** the UI. Required
   tests are listed in `S6_ML_EVALUATION_CONTRACT.md` §9. Build the
   preprocessing-leakage and group/time fixtures there; a naive global
   preprocessing path must be shown to differ from the pipeline path, and the
   test must assert the fit boundary, not just that a metric exists.
3. Add API routes under `/api/datasets/{id}/models/prediction` plus run storage
   and export, following `routes_models.py`.
4. Extend the Model Lab with a Predict tab (evaluation design · models ·
   metrics · comparison · run evidence), reusing `models.css`. Do not mix
   statistical and predictive results in one table.
5. Only then begin F11 diagnostics and F15 subgroups.

## Architecture decisions to preserve

* Statistics live in `app/models/statistics.py`; the API layer only validates and
  delegates. No inferential formula may be computed in the frontend.
* Refuse rather than silently alter a specification (constant predictors,
  singular designs, single classes, separation, non-convergence).
* The formula string is display-only and never executed.
* Complete-case exclusions are always counted and reported.
* A statistical fit is not a predictive evaluation; the UI states this.
* Model results are cleared whenever the dataset identity changes.
* Navigation order (Start 1, Data 2, Audit results 3, Study 4, Explore 5, Model
  Lab 6, Compare 7, Export 8) is asserted in `e2e/s6-ui-repairs.spec.ts`.
* Charts that measure themselves must never derive their container height from
  the SVG they size (the S6-A defect). Keep `.xfig__plot--sized` and the
  observer equality guard.

## Browser QA findings

* Visual review of OLS and logistic results was performed on real Chromium
  captures; screenshots are in `docs/screenshots/s6/after/`.
* Fixed during review: header tagline missing the Model Lab; coefficient and
  residual plots had insufficient axis labels; the parallel-coordinates example
  SVG scaled its labels ~3×; Model Lab `<select>` labels included option text as
  accessible names; the `KeyError: '_probability'` on OLS.
* Not captured: 1366×768 and 1920×1080 for the Model Lab; forced-colours mode;
  Firefox/WebKit.

## Known warnings / non-failures

* `pytest` reports 3 warnings: two numpy `invalid value encountered in divide`
  from the deliberate singular-design correlation probe, one pre-existing
  Starlette/httpx deprecation.
* `git` emits LF→CRLF notices on Windows; harmless.
