# S11 — Final Verification

**Date:** 2026-11-07 · **Branch:** `v2-premium-visual-foundation`
**Commits:** `7d1e90a` (S11-A audit) → `5074e2a` (S11-B HCI/motion/bundle) →
S11-D (this commit: fixtures fix, docs, screenshots)

## Full gate on the final modified tree

Every line below was executed in the S11 sessions; nothing is inherited from a
previous stage's report.

| Gate | Command | Result |
|---|---|---|
| Backend pytest | `.venv/Scripts/python -m pytest backend/tests -q` | **620 passed** (410.8 s)¹ |
| Synthetic leakage oracle | `.venv/Scripts/python scripts/evaluate_synthetic.py` | **41/41 cases, 61 checks, 0 failed** |
| Frontend unit tests | `npx vitest run` | **246 passed** (28 files)² |
| TypeScript | `npx tsc -b && npx tsc -p tsconfig.app.json --noEmit` | **clean** |
| ESLint | `npx eslint . --max-warnings 0` | **clean** |
| Production build | `npm run build` | **OK** — main chunk **405.53 kB (120.83 kB gz)**, no >500 kB warning |
| Playwright (real backend, fresh process) | `npm run test:e2e` | **39 passed (8.8 min)** on the final tree³ |
| Responsive screenshots | live browser 1440×900 / 390×844 | captured to `docs/screenshots/s11/` and inspected |
| Horizontal overflow | `scrollWidth − clientWidth` at 390 px | **0 px** on landing / Data / Audit |

¹ Backend code is untouched by S11 (frontend-only commits); the 620-pass run
was executed during S11-A on the same backend tree that ships.
² 245 S10 tests + 1 new draft-preservation test; one pre-existing flaky
identification test repaired (S11-A AUDIT-1) and verified stable.
³ First final-tree run was 38/39: the S7 chrome-geometry journey raced the new
lazy Data chunk (acted on the loading card). Fixed in the shared
`loadDemoFromEntry` helper by waiting for the dataset heading — a test-timing
repair, no product change; then the full suite passed 39/39.

## Intermediate E2E runs during S11

- Baseline on `f7103ea` (before any change): 39/39 (8.1 min) — confirms the
  reported S10 gate.
- After S11-B code changes: 38/39 with the single race above (documented).
- Final tree: **39/39 (8.8 min)**, zero retries configured (`retries: 0`).

## Scientific invariants confirmed

- No backend or statistical code changed in S11; estimator outputs, d-separation,
  fingerprints, dossier schema and manifests are byte-identical (backend tree
  untouched; the 620-test suite re-passes).
- Failed estimators still render as failures, never zeros; unavailable CIs are
  never invented; stale results keep their named staleness reasons (covered by
  the re-run S9B/S9C/S10 suites).
- No existing Playwright assertion was weakened; the one edited helper waits
  *for more* evidence, not less.

## Acceptance criteria (§30 of the S11 brief)

1–5 met (workflows verified, navigation smooth, loading labelled, feedback
immediate, no layout jumps); 6–9 met (no responsive defects found at
1440/390, forms unchanged and sound, charts accurate); 10–12 met (reduced
motion respected, keyboard accessibility improved via draft preservation +
labelled fallbacks, no critical/high security issue); 13 met (main bundle
−31 %, no interaction latency added); 14 met (dossier/exports untouched and
passing); 15 met (full gate above); 16 met (screenshots opened and inspected);
17 met (docs + commits below).
