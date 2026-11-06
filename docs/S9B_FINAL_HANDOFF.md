# S9B — Final Handoff

**Verdict: PASS.** S9B is committed and verified; S9C is authorised to start.
This file supersedes `docs/S9B_HANDOFF.md` (kept for provenance).

## State at handoff

- Branch `v2-premium-visual-foundation`. S9B implementation and the final audit
  are committed (see `git log`; implementation commit precedes the audit commit).
- All gates green on the committed tree: backend **536** tests, synthetic oracle
  **41/41** (61 checks), frontend **205** unit tests, typecheck/lint/build clean,
  Playwright **33/33** journeys.
- Independent numerical verification (see `docs/S9B_FINAL_AUDIT.md`) reproduced
  the engine's RA estimate exactly and IPW within nuisance-pipeline tolerance.

## The successor inherits

1. **A verified estimation engine surface** (`backend/app/causal/estimation/`):
   `contracts` (strict request), `preparation` (cohort accounting), `estimators`
   (RA/IPW/AIPW), `uncertainty` (bootstrap/influence function), `diagnostics`
   (balance, overlap incl. `propensity_histogram`), `service` (identification
   gate + orchestration + staleness). S9C must extend these, not bypass them.
2. **A figure system** (`frontend/src/estimation/figureFrame.tsx`): `FigureFrame`,
   `useMeasuredWidth`, `LegendItem`, export metadata contract. Reuse it for every
   new S9C figure so provenance/export/accessibility stay uniform.
3. **A model layer** (`frontend/src/estimation/estimationModel.ts`): request
   construction, `requestSignature`, `stalenessReasons`. New request fields must
   be added there *and* to the staleness comparison.
4. **An honesty vocabulary**: failed ≠ zero, unavailable interval ≠ invented
   bounds, balance ≠ exchangeability, agreement ≠ validity, scenario ≠ observed.
   S9C views must keep it.

## Environment / runbook

- Backend: `cd backend && ..\.venv\Scripts\python -m app.main` (port 8000).
- Frontend dev: `npm run dev` in `frontend/`.
- Playwright needs the venv first on `PATH`:
  `PATH="/e/Splitscore V2/.venv/Scripts:$PATH" npx playwright test`.
- Full gate: backend pytest; `scripts/evaluate_synthetic.py`; frontend
  `typecheck`, `lint`, `test`, `build`; Playwright.

## S9C starting points (agreed scope)

- **S9C-A** subgroup ATEs on a pretreatment variable (descendants of treatment
  refused), per-subgroup reuse of the verified estimators, forest plot in a new
  focused view.
- **S9C-B** reproducible robustness experiments (subsampling, placebo treatment,
  one explicitly parameterised sensitivity method or an honest "unavailable").
- **S9C-C** model-based what-if scenario explorer using the validated backend
  models only, with extrapolation warnings and no individual counterfactual claims.
- Delivery discipline: separate commits per package, tests before docs claim
  existence, no loosened assertions, untracked scratch files preserved.

## Preserved, deliberately untracked

`_s9b_*.log`, `_s9b_compare.json`, `import requests.txt`,
`scripts/_patch_s3_hero.py`, `docs/screenshots/*/_preview/` are scratch/session
artifacts and stay out of the commits.
