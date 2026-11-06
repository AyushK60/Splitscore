# S9C — Handoff

**Status: COMPLETE.** Subgroup effects (S9C-A), robustness/sensitivity
(S9C-B) and the model-based what-if explorer (S9C-C) are implemented,
scientifically validated, visually inspected and committed on
`v2-premium-visual-foundation`.

## What shipped

- **Backend** (`backend/app/causal/estimation/`): `subgroups.py`,
  `robustness.py`, `whatif.py`; three new gated, stored, staleness-checked
  routes in `routes_causal_estimation.py`. 45 new backend tests; full suite
  **581 passed**; synthetic oracle **41/41 (61 checks)**.
- **Frontend**: new `#/research` stage (**Causal research**, nav step 9) with
  three focused views — Subgroup effects (forest plot), Robustness
  (distribution/histogram/heatmap), What-If (scenario explorer). New model
  layer `src/research/researchModel.ts`; 31 new unit/component tests; **236
  passing**. 4 new real-backend Playwright journeys; **37 total passing**.
- **Docs**: `S9C_ARCHITECTURE.md`, `S9C_SUBGROUP_METHODOLOGY.md`,
  `S9C_SENSITIVITY_METHODOLOGY.md`, `S9C_WHAT_IF_CONTRACT.md`,
  `S9C_SCIENTIFIC_VALIDATION.md`, `S9C_VISUAL_VERIFICATION.md`, this file;
  `STATUS.md` updated.

## The flow

Effect Estimation → **Causal research** (Subgroup effects | Robustness |
What-If) → Export. The research stage builds strictly on a **stored estimation
run**: it rebuilds that run's exact request from the recorded reproducibility
block, refuses stale runs by name, and never re-specifies a study silently.

## Commit plan (as made)

1. `S9C backend: subgroup effects, robustness experiments and what-if
   scenarios` — the three modules, routes, and 45 tests. (One commit rather
   than three because the routes module and the shared request contracts span
   all three packages; each package is independently tested inside it.)
2. `S9C: the Causal Research stage` — frontend views, model layer, styles,
   types/client, router/main wiring, 31 unit tests, 4 journeys, screenshots.
3. `S9C documentation and status` — docs + STATUS.md (may be folded into 2).

## Decisions worth not re-litigating

- **Subgroup ATEs are AIPW pseudo-outcome averages** with influence-function
  uncertainty; the global cross-fitting provenance is disclosed in every
  payload. There is deliberately no per-group nuisance refit and no individual
  CATE prediction.
- **Sensitivity is a labelled simulation scenario**, not a bound; the grid is
  fixed 5×5 to bound compute.
- **What-if scenarios carry no intervals**, and profiles are restricted to the
  verified adjustment set (which structurally excludes treatment descendants).
- **No S7 dossier schema change**; figure/run exports with provenance remain
  the reporting path (same decision as S9B).

## Known gaps / natural next steps

1. Report/dossier integration for S9C analyses behind a versioned schema
   change (reusing `estimationExport` values).
2. Per-subgroup sensitivity or refit-based subgroup estimators when within-
   group overlap is poor (the warnings already flag those cases).
3. E-value or partial-R² sensitivity parameterisations as complements to the
   simulation scenario.
4. Persistent run history (the ≈1 h in-memory TTL applies to S9C runs too).

## Environment / runbook

Unchanged from `docs/S9B_FINAL_HANDOFF.md`: venv first on `PATH` for
Playwright; full gate = backend pytest, `scripts/evaluate_synthetic.py`,
frontend `typecheck`/`lint`/`test`/`build`, `npx playwright test`.

## Preserved, deliberately untracked

`_s9b_*.log`, `_s9b_compare.json`, `import requests.txt`,
`scripts/_patch_s3_hero.py`, `docs/screenshots/*/_preview/` remain untouched
session scratch outside version control.
