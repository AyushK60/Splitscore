# S9C Final Verification

**Date:** 2026-11-07 · **Branch:** `v2-premium-visual-foundation`
**Base commit:** `befea1e` · **Verdict: PASS** (all gates below executed in
this session; none taken from the handoff on trust).

## Verification matrix

| # | Gate | Command | Result |
| --- | --- | --- | --- |
| 1 | Full backend pytest | `.venv/Scripts/python -m pytest -q` (backend/) | **600 passed** (581 baseline + 15 independent-audit + 4 S9C API integrity) |
| 2 | Synthetic leakage oracle | `python scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks** |
| 3 | S8C identification tests | included in (1) (`test_causal_d_separation.py`, `test_causal_identification.py`) | passed |
| 4 | S9A estimation tests | included in (1) (`test_causal_estimation*.py`) | passed |
| 5 | S9B tests | included in (1) (`test_s9b_diagnostics.py`) | passed |
| 6 | S9C tests | included in (1) (`test_s9c_*.py`) | passed |
| 7 | Frontend unit tests | `npx vitest run` | **236 passed** (27 files) |
| 8 | TypeScript | `npx tsc -p tsconfig.app.json --noEmit` | clean |
| 9 | ESLint | `npx eslint src tests e2e` | clean |
| 10 | Production build | `npm run build` | success |
| 11 | Playwright browser suite | `npx playwright test` (venv python on PATH) | **37 passed** (4.2m) |
| 12 | Flaky-test soak | 15 × single-file runs of `CausalIdentification.test.tsx` | 15/15 after repair (2 failures in ~23 runs before) |
| 13 | Visual QA | screenshots at 1440/1024/768/390 re-captured from the full run | inspected; whiskers render, no overflow/clipping found at any width |

## Repairs delivered (verified)

1. **AUDIT-1 (HIGH)** — forest-plot whiskers computed `stroke: none` in the
   research stage because the estimation palette was scoped to `.eststudio`.
   Fixed by hoisting `--est-*` to `:root`; verified live (computed stroke
   `color(srgb 0.039 0.427 0.49 / 0.55)`); guarded by a new Playwright
   assertion on painted whisker geometry.
2. **AUDIT-2 (MEDIUM)** — `CausalIdentification.test.tsx` intermittency
   (≈1-in-10) reproduced, root-caused to a test-side race with the async
   saved-graph hydration, fixed by awaiting the save gate's clearance.
3. **AUDIT-3 (LOW)** — what-if numeric placeholder clipping; shortened.

## Independent numerical verification

15 new tests in `backend/tests/test_s9c_independent_audit.py`, summarised in
`S9C_INDEPENDENT_AUDIT.md` §2. Highlights: every simulated-confounder grid
cell re-fit with **statsmodels** matches production ≤ 1e-7; subsampling
repetition 0 traces to the recorded seed exactly; IPW matches the exact
closed-form Hájek result incl. influence-function SE at 1e-9; the subgroup
mixture identity and SE/contrast formulas are exact at three interval levels;
what-if predictions match hand-derived OLS at 1e-6.

## S9C decision gate

- Mathematical claims independently verified: **yes** (table above).
- Unresolved CRITICAL/HIGH defects: **none**.
- Required executable tests: **all pass** (rows 1–11).

**Verdict: PASS.** Per the assignment's automatic continuation rule, S10
implementation proceeds.
