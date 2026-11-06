# S9C — Architecture

**Status:** implemented and verified. Three work packages on top of the unchanged S8C/S9A foundations.

## Server

Three new modules in `backend/app/causal/estimation/`, each reusing the verified
machinery rather than reimplementing any numerics:

| Module | Work package | Reused foundations |
|---|---|---|
| `subgroups.py` | S9C-A subgroup effects | `run_identification_gate`, `prepare_cohort`, `estimate_aipw` (pseudo-outcome), `_reproducibility` |
| `robustness.py` | S9C-B robustness | `_estimate_point` (production RA/IPW/AIPW), direct estimator calls for the extended sensitivity design |
| `whatif.py` | S9C-C what-if | `_fit_outcome_model`, `_potential_outcome_predictions` (the g-computation model itself) |

Three new routes in `routes_causal_estimation.py`, all under the existing
dataset/graph scoping and the single structured error envelope:

- `POST /api/datasets/{id}/causal-graphs/{gid}/estimation/subgroups`
- `POST /api/datasets/{id}/causal-graphs/{gid}/estimation/robustness`
- `POST /api/datasets/{id}/causal-graphs/{gid}/estimation/whatif`

Every S9C run passes the same mandatory identification gate, is prepared on the
same cohort rules, is stored as `kind="estimation"` (so the existing history
listing, retrieval and fingerprint staleness re-check apply unchanged), and
echoes full reproducibility metadata including its experiment parameters and
resolved seed. Payloads carry `analysis_kind` (`subgroups` / `robustness` /
`what_if`) plus their own schema versions (`1.0.0` each).

## Client

New stage `#/research` (**Causal research**, nav step 9; Compare and Export
shift to 10 and 11), code-split like the other late stages:

- `src/research/ResearchView.tsx` — stage shell. Builds on a **stored
  estimation run**: the user picks one from session history; the shell rebuilds
  that run's exact `EstimationRequest` from its recorded reproducibility block
  (`requestFromRun`), fetches the graph for subgroup-variable metadata, and
  refuses stale runs with a named error pointing back to the estimation studio.
- `src/research/SubgroupView.tsx` — configuration + forest plot (FigureFrame),
  subgroup table, between-group contrasts, notes.
- `src/research/RobustnessView.tsx` — experiment chooser; repetition histogram
  with the original reference; sensitivity heatmap with descriptive shading.
- `src/research/WhatIfView.tsx` — per-covariate profile controls; two-arm
  prediction bars; profile/disclosure table.
- `src/research/researchModel.ts` — pure helpers: request reconstruction,
  forest domain/scaling, fixed-16-bin distribution binning, signed sensitivity
  colour scale.
- `src/estimation/estimationErrors.ts` — `describeError` extracted from the S9B
  studio so both stages present backend refusals identically (behaviour-preserving
  refactor; the S9B suite is unchanged and passing).

## Deliberate scope decisions

- **No S7 dossier schema change.** As in S9B, figure/run exports carry
  provenance instead of forcing an incompatible report-schema mutation; the
  decision recorded in `docs/S9B_HANDOFF.md` stands until a versioned dossier
  extension is designed.
- **Subgroup effects are AIPW-based.** The cross-fitted AIPW pseudo-outcome is
  the only per-row estimating quantity the verified engine produces, so it is
  the only basis for subgroup ATEs with closed-form uncertainty. RA/IPW remain
  available inside robustness experiments.
- **Sensitivity is a simulation scenario, not a bound** (see
  `S9C_SENSITIVITY_METHODOLOGY.md`); the payload, the UI and the tests all say so.
- **No intervals on what-if scenarios**; the model specification states this
  explicitly and points to the estimation studio for interval-bearing results.
