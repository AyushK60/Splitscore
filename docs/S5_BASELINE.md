# S5 Baseline — where S5 started

**Date:** 2026-11-03
**Branch:** `v2-premium-visual-foundation`
**S4 checkpoint at S5 start:** `5903206` ("S4-D: fix typecheck import in figureExport test")

## Repository state at S5 start

- Working tree clean except three untracked, unrelated user files
  (`import requests.txt`, `scripts/_patch_s3_hero.py`, `docs/screenshots/s3/_preview/`).
  All were preserved; none is part of S5.
- One pre-existing stash (`stash@{0}: S3 checkpoint`) left untouched.
- Latest S4 checkpoint confirmed as S4-D (`5903206`) by `git log`.

## Baseline verification (before any S5 change)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` (backend) | **292 passed**, 1 warning |
| Frontend unit tests | `npm run test` | **82 passed** (8 files) |
| Browser sanity | app served by `python -m app.main`, port 8000 | All six stages render; demo loads; audit runs |

Known pre-existing defect found during baseline (not introduced by S5):
`npm run lint` failed with 2 errors in `e2e/s4-explorer.spec.ts`
(`import()` type annotations). Fixed during S5-A alongside the e2e updates
required by the new workspace entry.

## Baseline screenshots (before S5-A)

Stored in `docs/screenshots/s5/before/`:

| File | Screen |
|---|---|
| `01-overview-start-1920.png` | Start — the old duplicate marketing-style launcher |
| `02-dataset-1920.png` | Data — old white/blue identity |
| `03-study-1920.png` | Study — S3 identity, narrow container |
| `04-explore-1920.png` | Explore — faint parallel-coordinates lines, empty Row Evidence panel |
| `05-results-1920.png` / `05b-results-findings-1920.png` | Results — old card style |
| `06-compare-1920.png` | Compare — old card style |

## Owner-reported problems confirmed in the baseline browser pass

1. **Multiple visual identities** — the internal app still used the S0–S2
   indigo/blue token layer (`styles/app.css` `:root` + `styles/v2.css`
   overrides) while Study/Explore used the S3 forensic-archive palette.
2. **Duplicate launcher** — `OverviewView` rendered a second marketing-style
   landing page (hero, "Try a demo", "How it works") inside the workbench.
3. **Unused horizontal space** — `.app-main`, header and nav were capped at
   1120 px; `.rs` stages at 1240 px. At 1920 px roughly 40% of the viewport
   was empty margins on the scientific screens.
4. **Chart refinement** — parallel-coordinates unselected lines drawn at
   0.13–0.16 opacity (near-invisible), axis range labels collided with top
   tick labels, tick/axis fonts 8.5–9 px, Row Evidence showed a large
   near-empty guidance panel.
