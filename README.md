# SplitScope

SplitScope audits a tabular machine-learning train/test split for data leakage
and shows each finding with the rows behind it. It also offers exploratory
plots, regression and prediction models, a causal graph editor with effect
estimation, and exportable reports. Everything runs locally: a FastAPI backend,
a React frontend, and a few small synthetic demo datasets in `datasets/`. There
are no accounts and no outbound network calls.

## Leakage checks

| Rule | Question |
|------|----------|
| SS-DUP-001 Exact duplicates | Do identical feature rows appear in both train and test? |
| SS-ENT-001 Entity overlap | Do entities (customers, patients, ...) appear on both sides of the split? |
| SS-CHR-001 Chronology | Are some training rows later than the earliest test row? |
| SS-TGT-001 Target copy | Does a feature reproduce the label? |
| SS-NEAR-001 Near duplicates (opt-in) | Which cross-split row pairs are nearly identical? |

Class imbalance and distribution shift are reported as diagnostics, not as
leakage findings. You can audit an existing split column or generate candidate
splits (`random`, `stratified`, `group`, `chronological`) and compare them.

## Requirements

* Python 3.11
* Node.js 20.18 or newer

## Setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt -r backend\requirements-dev.txt

cd frontend
npm ci
npm run build
cd ..
```

On Windows you can instead double-click `Setup-SplitScope.cmd` once, then use
`Start-SplitScope.cmd` and `Stop-SplitScope.cmd`. See [docs/LAUNCHER.md](docs/LAUNCHER.md).

## Run

```powershell
cd backend
..\.venv\Scripts\python -m app.main
```

Open http://127.0.0.1:8000 (API docs at `/api/docs`). Change the address with
`SPLITSCOPE_HOST` and `SPLITSCOPE_PORT`.

For frontend development, start the backend as above and run `npm run dev` in
`frontend/`. Vite proxies `/api` to the backend.

## Using your own data

Upload a CSV on the Data page. If the file already marks train and test rows,
pick that column and map one value to each side. Rows with empty or extra
labels are counted and excluded. Otherwise choose a split strategy; the
strategy, seed and every row assignment are stored with the run and can be
downloaded. The uploaded file is never modified. Target, entity, timestamp and
feature columns are optional, and the suggested roles must be confirmed.

## Tests

```powershell
# backend
cd backend
..\.venv\Scripts\python -m pytest -q
cd ..

# audit engine against synthetic fixtures with known ground truth
.venv\Scripts\python scripts\evaluate_synthetic.py

# check that the committed demo datasets regenerate identically
.venv\Scripts\python scripts\generate_datasets.py --check

# frontend
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
npx playwright install chromium   # once
npm run test:e2e                  # starts its own backend on port 8123
```

`scripts/demo_journey.py` runs an end-to-end API walkthrough against a running
server. More on the evaluation suite in [EVALUATION.md](EVALUATION.md); code
layout in [ARCHITECTURE.md](ARCHITECTURE.md).

## Limits

The backend enforces and reports these through `GET /api/health`. Upload errors
say which limit was hit; files are never silently truncated.

| Default | Scope |
|---------|-------|
| 25 MiB | Raw upload size |
| 10,000 rows, 100 columns | Dataset shape (minimum 20 rows, 2 columns) |
| 256 MiB | Estimated in-memory size of one parsed dataset |
| 384 MiB | Total in-memory store; least recently used datasets are evicted |
| 500 rows | Near-duplicate analysis is skipped above this combined row count |
| 8 datasets, 16 runs, 1 hour | In-memory store size and time to live |

Override them with the `SPLITSCOPE_MAX_*` environment variables listed in
`backend/app/core/config.py`.

## Caveats

* The evaluation fixtures are small and synthetic. Passing them shows the
  checks match their definitions, not how they perform on real data.
* Near-duplicate findings are candidates, not proof of leakage.
* Random and stratified splits do not guarantee entity isolation.
* Single user, no authentication. Uploads live in memory only and CORS is
  limited to local development origins. Do not expose the server to an
  untrusted network.

## License

MIT. See [LICENSE](LICENSE).
