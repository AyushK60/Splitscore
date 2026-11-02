# S3 baseline — repository state before the milestone

Captured at the start of the S3 session, before any S3 change.

## Git

| Item | Value |
| --- | --- |
| Branch | `v2-premium-visual-foundation` |
| HEAD at start | `8c4b540` — *Redesign the landing page around a forensic-archive art direction* |
| Previous commits | `8315020` (S0–S2), `4f91462` (V1 baseline) |
| Uncommitted changes | none except the pre-existing untracked `import requests.txt`, deliberately left alone |

The prompt expected `8c4b540` as the visual checkpoint; that matched the repository.

## Source inspected

- Root: `SplitScope_V2_PRODUCT_BLUEPRINT.md`, `docs/S0_S2_IMPLEMENTATION_REPORT.md`, `README.md`, `STATUS.md`, `EVALUATION.md`.
- Backend: `app/main.py`, `api/{deps,schemas,routes_datasets,routes_audit,routes_reports}.py`, `audit/{dataset,io,roles,types}.py`, `core/{store,config,hashing,version}.py`, `splits/`, `reports/`, `synthetic/`, `evaluation/`.
- Frontend: `main.tsx`, `lib/router.ts`, `state/AppState.tsx`, `views/*`, `components/*`, `styles/{app,v2,landing}.css`, `tests/*`, `e2e/*`.
- No `AGENTS.md` exists in this repository. The blueprint (§4 visual system, F01/F02/F19, §9 stages) was the specification of record.

## Measured baseline (before S3 changes)

| Command | Result |
| --- | --- |
| `cd backend && ../.venv/Scripts/python -m pytest -q` | **218 passed** |
| `cd frontend && npm run typecheck` | exit 0 |
| `cd frontend && npm run lint` | exit 0, 0 warnings |
| `cd frontend && npm run test` | **70 passed** (6 files) |
| `cd frontend && npm run build` | exit 0, ~55.7 kB CSS / 337.3 kB JS |
| `cd frontend && SPLITSCOPE_E2E_PORT=8207 npm run test:e2e` | **4 passed** |
| `node scripts/capture-v2-screenshots.mjs` (port 8300) | exit 0, 0 px overflow at 1440/768/390, 0 console errors |

These are the numbers the S3 exit gate is measured against. They are historical
baselines, not guarantees: the final results are in `docs/S3_VERIFICATION.md`.

## Environment notes

- Python `.venv` lives at the repository root; run pytest from `backend/` as
  `../.venv/Scripts/python -m pytest -q`.
- The backend serves the built frontend on one port (`SPLITSCOPE_PORT`), so the
  capture and browser suites exercise the production build.
- Port 8123 is occupied by an unrelated pre-existing process on this machine, so
  the E2E suite uses `SPLITSCOPE_E2E_PORT=8207`.
- `import requests.txt` is unrelated stray content and remains untracked.

## What S3 had to add

Per the approved blueprint: **F01** (Study Card and provenance), **F02** (ingestion,
profiling, role mapping, data dictionary) and the foundational part of **F19**
(reproducibility manifest). The original five leakage checks, split strategies,
evidence, comparisons, exports and privacy posture had to remain unchanged and
re-tested.
