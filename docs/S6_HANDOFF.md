# S6 handoff

**Status: PARTIAL.** The mandatory S5 defect repairs are complete and verified,
and the F09 statistical workbench is implemented, integrated and numerically
validated. F10 (predictive ML), most of F11 (diagnostics) and F15 (subgroups)
are not implemented. Nothing in those areas is simulated or advertised.

## Delivered

### 1. S6-A — the four reported defects (`52a2ef9`)

| Defect | Cause | Repair |
|---|---|---|
| Scatter page grew without bound | ResizeObserver wrote the container's content height back into the SVG it sized; the inline SVG line box added pixels every frame | Definite CSS height on the plot frame, observer reads only, state equality guard, SVG `display:block`; verified by measured height stability |
| Header hover unreadable | Global `button:hover` painted `--accent-soft` behind `--bone` text; nav overrode only colour | Transparent nav/brand hover surfaces, explicit active+hover, celadon focus ring |
| Navigation implied skipped stages | Study/Explore numbered before Results while Data → Run Audit goes to Results | Audit results is stage 3; breadcrumb plus per-stage next actions; Study/Explore marked optional; routes and history unchanged |
| Parallel coordinates opaque | No encoding explanation, no selection count, bare `crosshair` | Progressive reading guide with annotated example, persistent one-line hint, count, empty-selection guidance, `ns-resize` brush affordance and rail labels |

Evidence: `docs/S6_A_UI_REPAIRS.md`, `docs/screenshots/s6/{before,after,mobile,tablet}`,
`frontend/e2e/s6-ui-repairs.spec.ts`.

### 2. S6-B — F09 statistical workbench (`aec75e9`)

* Explicit typed specification (task, outcome, predictors, missing policy,
  intercept, confidence level, positive class, categorical references).
* OLS and binary logistic regression through `statsmodels` 0.15.0.
* Coefficients, standard errors, confidence intervals, statistics, p-values,
  odds ratios, R²/adjusted R²/F/df/residual σ, log-likelihood/AIC/BIC/McFadden
  pseudo-R², class counts, coding reference and level list.
* Complete-case accounting with per-column exclusions; `fail` policy refuses.
* Guardrails: unknown/duplicate columns, constant outcome or predictor, singular
  design, minimum sample, >12 category levels, single class, missing positive
  level, perfect separation, non-convergence — all structured refusals.
* Diagnostics subset: coefficient interval plot, residual-versus-fitted from the
  fitted object, residual summary, VIF, condition number, sampled diagnostic
  rows with immutable row ids.
* Bounded run storage (`RunKind` now includes `model`), JSON export identical to
  the on-screen payload, provenance including statsmodels/numpy/pandas/scipy
  versions and dataset sha256.
* Integrated Model Lab at `#/models`, step 6, three-region instrument layout,
  responsive collapse, result reset on dataset replacement.
* 11 numerical oracles comparing every inferential quantity against independent
  numpy normal equations and a direct statsmodels logistic fit; tolerances
  1e-8–1e-9.

Evidence: `docs/S6_STATISTICAL_METHODS.md`, `docs/S6_NUMERICAL_VALIDATION.md`,
`docs/S6_MODEL_DIAGNOSTICS.md`, `docs/S6_VERIFICATION.md`,
`frontend/e2e/s6-model-lab.spec.ts`.

## Verification ledger (final code)

| Suite | Result |
|---|---|
| Backend pytest | **351 passed** (340 baseline + 11 new) |
| Synthetic audit oracle | **41/41 cases, 61/61 checks**, exit 0 |
| Frontend vitest | **82 passed** |
| TypeScript / ESLint / production build | clean |
| Playwright | **18 passed** (11 baseline + 4 S6-A + 3 S6-B) |

## Not delivered

* F10 predictive ML: no trained estimator, no predictive metric, no comparison,
  no sealed-test policy in code. Contract only.
* F11 remainder: Q–Q, influence/leverage, calibration, ROC/PR, confusion matrix,
  threshold analysis, permutation importance, error cohorts.
* F15 subgroups: no subgroup table, denominators or error analysis.
* Synthetic fixtures 3–5 for leakage/group-time/subgroup validation.
* Frontend unit tests specific to Model Lab (E2E covers it); 1366/1920 visual
  captures.

## Known limitations of the statistical workbench

Classical standard errors only; complete case only; indicator coding only; no
interactions, weights, offsets or splines; no multiple-testing correction;
categorical reference defaults to the first sorted level unless the user chooses
one (always reported). A statistical fit uses all analysed rows and does not
establish predictive validity or detect leakage.

## Next stage

S6-C: implement F10 against `S6_ML_EVALUATION_CONTRACT.md`, starting with
`backend/app/models/prediction.py` and its leakage-boundary tests. Exact next
action, commands, environment gotchas and architecture constraints are in
`docs/S6_AGENT_CONTINUATION.md`.

**Do not start S7 (causal DAG/estimation) in this stage.**
