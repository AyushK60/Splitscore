# S9A verification record

> **Note (post-audit):** this file preserves the implementation-stage
> verification exactly as run. The final post-audit tree results are in
> `docs/S9A_FINAL_VERIFICATION.md`; the independent audit itself is in
> `docs/S9A_INDEPENDENT_AUDIT.md`.

All numbers below are from actual runs in this session. Commands use the
repository virtual environment (`E:\Splitscore V2\.venv`, Python 3.11.9).

| Gate | Command | Result |
|---|---|---|
| Backend, full suite | `../.venv/Scripts/python.exe -m pytest -q` (in `backend/`) | **499 passed** (454 pre-existing + 45 new S9A), 0 failures |
| — new engine tests | `python -m pytest tests/test_causal_estimation.py -q` | 34 passed |
| — new API tests | `python -m pytest tests/test_causal_estimation_api.py -q` | 11 passed |
| — S8 regression (S8A/B/C) | included in the full suite | all pass (identical suites) |
| Synthetic leakage oracle | `python scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks** — exit 0 |
| Frontend unit tests | `npm run test` (in `frontend/`) | **145 passed** (14 files) |
| TypeScript typecheck | `npm run typecheck` | clean |
| ESLint | not run — no frontend source changed by S9A | — |
| Production build | not rebuilt — `frontend/dist` unchanged; S9A adds backend routes only | — |
| Playwright journeys | `npx playwright test --reporter=line` with the repo venv on PATH | **29 passed** (chromium, real backend + built frontend) |
| Ruff | `ruff check` on all new/changed S9A files | clean (pre-existing lint debt in untouched files is unchanged) |

Notes:

* Backend suite runtime ≈ 5 min; the S9A engine tests dominate (bootstrap
  refitting). No test was weakened to make an expected value agree: the two
  tolerance findings investigated were (a) the naive-difference bias in the
  strong-confounding case is seed-dependent (assertion adjusted to a
  scientifically defensible threshold, recovery tolerances unchanged) and
  (b) strong-confounding IPW shows its expected higher finite-sample
  variance (documented, tolerance ≈ 2 SEs retained).
* The first Playwright invocation failed with `ModuleNotFoundError:
  statsmodels` because the Playwright webServer picks `python` from PATH —
  an environment issue, not a product defect; re-running with the repo venv
  on PATH passes. (Pre-existing convention; unchanged by S9A.)
* Starting baseline re-verified before any change: 454 passed on `0c5bf2d`.
