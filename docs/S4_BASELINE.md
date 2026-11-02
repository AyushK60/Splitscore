# S4 baseline — Visual Explorer foundation

Recorded 2026-11-03 on branch `v2-premium-visual-foundation`, commit `6bfb638`
(S3) verified before any S4 work began.

## Independently verified starting state

| Gate | Command | Result |
| --- | --- | --- |
| Backend tests | `cd backend && ../.venv/Scripts/python -m pytest -q` | **252 passed** |
| Frontend typecheck | `cd frontend && npm run typecheck` | exit 0 |
| Frontend unit tests | `cd frontend && npm run test` | **70 passed** (6 files) |
| Frontend lint | `cd frontend && npm run lint` | exit 0 (zero warnings enforced) |
| Synthetic oracle harness | `python scripts/evaluate_synthetic.py` | **41 cases / 61 checks, 0 failed, exit 0** |
| Playwright E2E (pre-S4) | `SPLITSCOPE_E2E_PORT=… npx playwright test` | 5 passed (4 legacy + 1 S3) |

## Repository facts established before coding

- **Immutable row identity already existed.** `Dataset.row_ids` (minted by
  `app.audit.io.make_row_ids` as `row-000001…` at load time) is the join key
  every S4 view uses. No chart joins on display positions.
- **The stash `stash@{0}` ("S3 checkpoint: all S3 work staged, pre-verification")**
  predates the verified S3 commit `6bfb638`; its content was superseded by that
  commit. It was **left untouched** (not applied, not dropped) per the S4
  safety rules.
- Untracked files `import requests.txt`, `scripts/_patch_s3_hero.py` and
  `docs/screenshots/s3/_preview/` are scratch artefacts from the S3 session;
  they were left untracked and are not part of S4.
- The effective landing palette was defined twice: `landing.css` (`:root`) and
  a calibrating override in `s3.css` (`.lp` scope) that wins inside the landing
  page. The S4-A refinement updated both consistently.
- The backend serves `frontend/dist` from disk on one port
  (`SPLITSCOPE_PORT`); a rebuilt bundle is picked up without restart, but
  Python changes require one.

## S4-A landing colour refinement (only change to the landing page)

Refinement of the Forensic Archive identity, not a redesign — hero, animation,
typography, layout, content and navigation untouched:

- Copper: `#e07a3c` → `#d58055` (same hue family, roughly 15 points less
  saturation); copper-light `#f2a86f` → `#e6ab84`; copper-deep `#8f3d1e` →
  `#8f4a2a`.
- Ink levels lifted slightly (`#080e0b` → `#0a110d` etc.) so adjacent dark
  surfaces sit closer; paper tones harmonised (`#f3ebdb` → `#f1e9d9`).
- Muted bone text gained 8–10 opacity points at the dimmest tiers (42% → 52%
  … 64% → 72%); decorative grid lines softened.
- All hardcoded copper/ink rgba tints retinted to match (17 replacements).
- Contrast verified (WCAG relative luminance): CTA ink-on-copper 6.42:1,
  copper-light accents on ink 9.58:1, muted bone 72% on ink ≈ 9.15:1,
  ink-soft on paper 5.83:1, copper-deep links on paper 5.47:1. Text roles
  that read as copper on ivory already use copper-deep (5.47:1), so no text
  pair falls below target.
- Before/after full-page captures at 1440×900 and 390×844 (scroll pass first):
  `docs/screenshots/s4/landing-before/` and `landing-after/`.
