# S7 baseline

**Date:** 2026-11-05
**Branch:** `v2-premium-visual-foundation`
**Starting HEAD:** `d65fc4f` — S6-D/E complete model diagnostics and subgroup uncertainty
**Stage:** S7 as defined by the approved practical brief: Report / Export Studio,
scatter and scatter-matrix legibility, compact workspace chrome, verification and
handoff.

## What S7 is — and is not

This stage is the decision/publication layer. It composes the runs a user
actually produced into one evidence dossier, makes the exploratory marks
legible, and reduces the persistent height of the workbench chrome.

It does **not** implement the blueprint's formal causal DAG and identification
stage. No causal graph, estimator, treatment effect or causal claim is added.
That work remains unstarted and is explicitly outside this S7 brief.

## Baseline state at `d65fc4f`

| Item | Baseline |
|---|---|
| Backend pytest | 363 passed, 3 warnings |
| Synthetic audit oracle | 41/41 cases, 61/61 checks |
| Frontend Vitest | 90 passed (9 files) |
| Playwright E2E | 21 passed |
| TypeScript / ESLint / build | clean; non-failing chunk-size warning |
| Working tree | clean apart from pre-existing untracked scratch/screenshots and `stash@{0}` (S3 checkpoint) |

Pre-existing untracked material was left untouched:
`docs/screenshots/s3/_preview/`, `docs/screenshots/s5/_preview/`,
`import requests.txt`, `scripts/_patch_s3_hero.py`, and the S3 stash.

## Baseline defects and gaps

| Area | Baseline problem |
|---|---|
| Scatter | Marks were visually faded and small; dense or low-cardinality axes collapsed into stacks; selection used no dedicated cue. |
| Scatter matrix | Caption claimed colour grouping but every panel drew one teal path; panels were small and the matrix packed five across at workstation width, leaving an orphan; no per-panel correlation was stated. |
| Chrome | Brand, tagline and nine stages occupied two persistent rows; context and next actions were not clearly separated from the sticky band. |
| Export | Only per-run JSON/HTML and assignment CSVs existed. There was no composed dossier, no section selection, no model-run inclusion, no unified print artifact and no image-conscious report surface. |
| Navigation/reset | Route changes inherited the global smooth-scroll setting, so a new stage could animate through the previous page before settling. |
| Landing | Copy still claimed Visual Explorer, Model Lab and a research dossier were “not in this build”; proof counts were stale. |

## S7 acceptance gate

1. A Report Studio at `#/export` composes real dataset, audit, comparison,
   study/profile/provenance, scorecard, findings, selected Model Lab runs,
   limitations and reproducibility state.
2. Sections can be included or excluded; a section whose run is missing is
   shown as unavailable with its reason, never as a clean result.
3. The same server payload drives the preview, structured JSON and a
   self-contained printable HTML artifact. Print-to-PDF uses the browser's print
   dialog; no separate PDF library is claimed.
4. Scatter and matrix marks are readable at 1920/1366/tablet/mobile, with
   deterministic, disclosed jitter for genuinely discrete axes only.
5. One compact sticky row carries brand and primary navigation; context scrolls
   away and focus/hover/active states remain readable.
6. All S0–S6 behaviour, honesty contracts, synthetic oracle and browser journeys
   keep passing.
7. Independent backend, frontend and browser tests cover report composition,
   export contracts, scatter rules and the studio journey.
8. Six S7 documents and a curated screenshot set describe exactly what was
   verified, what was fixed and what remains deferred.

## Starting test ledger

`backend/tests/test_dossier.py` and the S7 frontend tests did not exist at the
baseline. The S7 additions account for the final counts in
`docs/S7_VERIFICATION.md`.
