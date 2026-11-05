# S9A final verification (post-audit tree)

All numbers are from actual runs on the final audited tree (branch
`v2-premium-visual-foundation`, implementation commit `158c833` + the
audit-repair commit recorded in `git log`). Commands use the repository
virtual environment (`E:\Splitscore V2\.venv`, Python 3.11.9).

| Gate | Command | Result |
|---|---|---|
| Backend, full suite | `.venv/Scripts/python.exe -m pytest -q` (in `backend/`) | **530 passed** (499 pre-audit + 16 independent-audit + 15 adversarial), 0 failures |
| — S9A engine tests | included above (`tests/test_causal_estimation.py`) | 34 passed |
| — S9A API tests | included above (`tests/test_causal_estimation_api.py`) | 11 passed |
| — Independent audit harness | included above (`tests/test_causal_estimation_audit.py`) | 16 passed |
| — Adversarial suite | included above (`tests/test_causal_estimation_adversarial.py`) | 15 passed |
| — S8A/B/C regression | included above | all pass |
| Synthetic leakage oracle | `.venv/Scripts/python.exe scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks, exit 0** |
| Frontend unit tests | `npm run test` (in `frontend/`) | **145 passed** (14 files) |
| TypeScript typecheck | `npm run typecheck` | clean |
| ESLint | not run — no frontend source changed by S9A or the audit | — |
| Production build | not rebuilt — `frontend/dist` unchanged; S9A is backend-only | — |
| Playwright journeys | `npx playwright test --reporter=line` with the repo venv on PATH | **29 passed** (chromium, real backend + built frontend) |
| Ruff (all S9A files incl. audit/adversarial tests) | `ruff check backend/app/causal/estimation backend/app/api/routes_causal_estimation.py backend/tests/test_causal_estimation*.py` | clean |

## Notes on execution

* Backend suite runtime ≈ 5¼ min, dominated by refitting bootstrap and
  cross-fitting tests. No test was skipped, weakened, or deleted to achieve
  green status; the audit *added* 31 tests, including regression tests for
  every repaired defect.
* The three pre-audit 500-path defects are exercised in their repaired form
  by permanent tests; the pre-repair behavior was captured in the audit log
  (`docs/S9A_INDEPENDENT_AUDIT.md` §3) before fixing.
* Environment caveat (pre-existing): Playwright's webServer starts the backend
  with `python` from PATH, so the run requires the repository venv on PATH.
  The first bare invocation fails with `ModuleNotFoundError: statsmodels` — an
  environment issue, not a product defect.
