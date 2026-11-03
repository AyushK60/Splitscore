# S6 verification

**Date:** 2026-11-03 (final run after the last code change)
**Branch:** `v2-premium-visual-foundation`
**Checkpoints:** S6-A `52a2ef9`; S6-B is the commit that contains this file.
**Overall status: PARTIAL** — the four S5 defects are repaired, the F09
statistical engine is implemented and validated, and the integrated Model Lab
works. Predictive ML (F10), the full diagnostics workspace (F11) and subgroup
analysis (F15) are **not implemented** and are not claimed.

## Automated verification (last run, final code)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` (backend) | **351 passed**, 3 warnings (2 numpy correlation warnings in the deliberate singular-design test, 1 pre-existing Starlette/httpx warning) |
| Synthetic audit oracle | `python scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks, exit 0** |
| Frontend unit tests | `npm run test` | **82 passed** (8 files) |
| TypeScript | `npm run typecheck` | clean |
| ESLint | `npm run lint` (`--max-warnings 0`) | clean |
| Production build | `npm run build` | clean |
| Playwright E2E | `SPLITSCOPE_E2E_PORT=8180 npx playwright test` | **18 passed** (11 pre-existing + 4 S6-A + 3 S6-B) |

`pytest` uses the repository `.venv`. The Playwright `webServer` runs
`python -m app.main`, so E2E runs required the venv on `PATH`:

```bash
export PATH="/e/Splitscore V2/.venv/Scripts:$PATH"
cd frontend
SPLITSCOPE_E2E_PORT=8180 npx playwright test
```

Port 8123 is held by an unrelated process on this machine (documented in S5);
the committed default is unchanged.

## User-reported defects (S6-A acceptance)

| Requirement | Status | Evidence |
|---|---|---|
| Scatter no longer expands indefinitely | **PASS** | Browser regression: 8 samples spread <= 4 px, scroll cycles, viewport change, axis changes and inspector toggles; measured 2174->2930 px before, constant 1396 px after |
| Header hover states readable | **PASS** | Computed WCAG contrast >= 4.5 for every hovered nav item, active+hover and the brand; transparent fills asserted; keyboard focus ring asserted |
| Audit navigation no longer misleading | **PASS** | Audit results is step 3; running the audit from Data makes it current; breadcrumb and next actions; back/forward verified; Study/Explore optional |
| Parallel coordinates beginner guidance | **PASS** | Keyboard-operable reading guide, annotated example, selection count, empty-selection hint, brush aria-labels; header count, legend and Row Evidence counts reconciled |

## F09 acceptance (statistical engine)

| Requirement | Status | Evidence |
|---|---|---|
| OLS genuinely computed | **PASS** | statsmodels OLS; coefficients/SE/CI/t/p/R2/adjusted R2/F/df/sigma/log-likelihood/AIC/BIC |
| Logistic genuinely computed | **PASS** | statsmodels Logit; coefficients/SE/CI/z/p/odds ratios/LL/LR/McFadden R2/AIC/BIC |
| Numerical oracles | **PASS** | 11 tests; OLS vs numpy normal equations, logistic vs direct statsmodels reference, categorical dummies vs numpy; tolerances 1e-8 to 1e-9 |
| Transparent configuration | **PASS** | Formula, intercept, missing policy, alpha, positive class, coding/reference, analysed population, versions, run id in result and UI |
| Guardrails | **PASS** | Single class, constant outcome/predictor, singular design, too few rows, too many levels, missing coding, separation, non-convergence -> structured refusals |
| Not executed as code | **PASS** | Formula is built and displayed only; design matrix is constructed in Python |
| Export | **PASS** | `GET /api/models/runs/{run_id}/export`; E2E downloads and reconciles run id and the constant coefficient with the table |

## F10 / F11 / F15 acceptance

| Requirement | Status |
|---|---|
| Baseline + fitted predictive models with leakage-safe pipelines | **NOT IMPLEMENTED** — no scikit-learn estimator is trained |
| Predictive metrics (accuracy/ROC-AUC/MAE/RMSE) | **NOT IMPLEMENTED** — no metric is displayed |
| Test-set sealing and train/validation/test policy | **CONTRACT ONLY** (`S6_ML_EVALUATION_CONTRACT.md`) |
| Model comparison | **NOT IMPLEMENTED** |
| Q-Q, leverage/Cook's, calibration, ROC/PR, importance | **NOT IMPLEMENTED** |
| Coefficient intervals, residual-vs-fitted, VIF, conditioning | **IMPLEMENTED** (basic F11 subset) |
| Subgroup analysis (F15) | **NOT IMPLEMENTED** |

No placeholder, hardcoded diagnostic image or simulated metric exists anywhere
in the product for these unimplemented areas.

## Defects found and fixed during S6

| Defect | Found by | Fix |
|---|---|---|
| Scatter ResizeObserver feedback loop | Measurement on the pre-fix build | Definite CSS plot height; observer reads, never writes, its own height; state equality guard |
| Global button hover paint on the masthead | Computed-style inspection in Chromium | Explicit transparent nav/brand hover surfaces; celadon focus ring |
| Stage numbering contradicted Data -> Run Audit | Code and browser review | Audit results moved to step 3; breadcrumb + contextual next steps |
| Parallel-coordinates example SVG scaled its labels ~3x | Screenshot review | Fixed intrinsic width/height on the illustrative SVG |
| Model Lab labels included option text as accessible names | E2E strict-mode failure | Explicit `aria-label` on every select |
| `KeyError: '_probability'` for OLS | New oracle tests | Diagnostic sampler accepts absent probabilities |
| Stale model fit after dataset replacement | Design review | Fit state cleared on dataset identity change; E2E asserts it |

## Honest limitations

* Statistical fits use classical standard errors, complete-case missingness and
  indicator coding only (see `S6_STATISTICAL_METHODS.md`).
* A statistical fit is not a predictive evaluation; the UI says so, and no
  train/test metric is produced.
* Frontend unit tests were not added for the Model Lab this session; its UI is
  covered by three Playwright journeys plus the typechecker. The statistical
  correctness is covered by backend oracles.
* Visual QA captured 1440 px and 390/768 px; 1366 px and 1920 px were reviewed
  by breakpoint, not captured.
* Chromium only; no forced-colours testing.
* Synthetic fixtures 3-5 from the S6 brief (preprocessing leakage, group/time
  split, subgroup error) were not built because the engines they validate are
  not implemented.

## Overall

**PARTIAL.** S6-A is complete and verified. F09 is complete for the declared
scope. F10, most of F11 and F15 remain. The repository is committed, tested and
documented for a successor to continue from `docs/S6_AGENT_CONTINUATION.md`.
