# SplitScope

SplitScope audits a tabular machine-learning **train/test split** for specific,
evidence-supported data-leakage risks and shows every finding with the exact
rows behind it. It runs entirely locally: a FastAPI backend, a React frontend,
and six small committed synthetic demo datasets. No accounts, no cloud, no
outbound network calls at runtime.

It is a deterministic engineering tool, not a statistical guarantee: it checks
enumerable conditions and states plainly what it did *not* check.

## What it checks

| Check | Question it answers |
|-------|---------------------|
| **SS-DUP-001** Exact duplicates | Do identical feature rows appear in both train and test? |
| **SS-ENT-001** Entity overlap | Do whole entities (customers, patients, …) straddle the boundary? |
| **SS-CHR-001** Chronology | Are some training rows later than the earliest test row? |
| **SS-TGT-001** Target copy | Does a feature reproduce the label itself? |
| **SS-NEAR-001** Near duplicates (opt-in) | Which cross-split row pairs are near-identical under a scaled Chebyshev distance? |

Plus dataset **diagnostics** (class imbalance, distribution shift) that are
reported as diagnostics — never as leakage findings.

**Split strategies:** audit an existing split column, or generate and compare
candidates: `random`, `stratified`, `group` (entity holdout), and
`chronological`. The comparison shows consequences; it never picks a winner.

## Requirements

* **Python 3.11** (verified on 3.11.9, Windows 11)
* **Node.js ≥ 20.18** and npm (verified on 20.18.1 / npm 10.8.2)

## Setup (Windows PowerShell)

All commands are given with their working directory.

```powershell
# 1. Backend dependencies (from the repository root)
py -3.11 -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt        # runtime
.venv\Scripts\pip install -r backend\requirements-dev.txt    # + pytest, ruff (tests)

# 2. Frontend dependencies (clean install from the lockfile)
cd frontend
npm ci
cd ..
```

## Starting SplitScope V2 (one-click, recommended)

On Windows you do not need the terminal at all:

1. **First time only:** double-click `Setup-SplitScope.cmd` (checks Python
   3.11 and Node.js ≥ 20.18, installs the pinned dependencies, builds the
   frontend, creates the desktop shortcut — clear errors if a prerequisite
   is missing).
2. **Every day:** double-click the **SplitScope V2** desktop shortcut (or
   `Start-SplitScope.cmd`). SplitScope opens in your browser at
   http://127.0.0.1:8000.
3. **To shut down:** run `Stop-SplitScope.cmd` — it stops only the server
   the launcher started. `Status-SplitScope.cmd` shows a plain-language
   status at any time.

The launcher reuses a healthy running server, never rebuilds unnecessarily,
never opens a duplicate browser tab, and never touches unrelated programs on
port 8000. See `docs/POST_S11_LOCAL_LAUNCHER.md` for details and
troubleshooting.

## Build and start the application (manual)

```powershell
# Build the frontend once (output: frontend/dist)
cd frontend
npm run build
cd ..

# Start the full application — API + built frontend on one port
# (..\ points at the repository-root .venv created above)
cd backend
..\.venv\Scripts\python -m app.main
```

Open **http://127.0.0.1:8000**. The API docs are at
http://127.0.0.1:8000/api/docs. Host and port can be changed with the
`SPLITSCOPE_HOST` / `SPLITSCOPE_PORT` environment variables.

### Optional: frontend development server

```powershell
# Terminal 1 (as above)
cd backend; ..\.venv\Scripts\python -m app.main

# Terminal 2 — Vite dev server, proxies /api to the backend
cd frontend
npm run dev
```

## Using your own data

Upload a CSV from **Data → Choose a CSV file**. SplitScope then asks one entry
question: *does your file already say which rows are training and testing?*

* **Yes — check my existing split.** Pick the split column, inspect the values
  that actually occur (with row counts), and map exactly one value to train and
  one to test. Empty cells and any third label are named, counted and excluded
  from the audited split rather than folded into a side.
* **No — help me create a split.** Choose a random, stratified, group or
  chronological holdout. Ineligible strategies are disabled with the missing
  role named. The strategy, seed and every row's assignment are stored with the
  run and can be downloaded as a CSV; the uploaded file is never edited.

The remaining guided questions are target (optional but recommended), entity
(optional), timestamp (optional) and features. Suggestions come from column
names and types and must be confirmed; **not applicable / I don't know** is
always available. A successful role check only means no column holds two roles
— it is not confirmation that the audit can run.

## Verification

```powershell
# Backend test suite (218 tests)
cd backend; ..\.venv\Scripts\python -m pytest -q; cd ..

# Synthetic evaluation of the audit engine (41 cases / 61 checks, exit 0/1/2)
# Run from the repository root:
.venv\Scripts\python scripts\evaluate_synthetic.py

# Frontend unit/component tests (70 tests), lint, typecheck, production build
cd frontend
npm run test
npm run lint
npm run typecheck
npm run build

# Four end-to-end journeys (real Chromium; Playwright builds the frontend and
# starts a fresh backend on port 8123 itself, stopping it afterwards).
# Add the repository-root .venv\Scripts directory to PATH so `python` resolves.
npx playwright install chromium   # once per machine
npm run test:e2e
cd ..
```

The evaluation script exits `0` when every expectation matched, `1` on an
expectation mismatch, and `2` when a case could not be evaluated. Add
`--output-dir <dir>` to write machine-readable `evaluation_results.json`, and
`--list` to see the case ids.

To confirm the committed synthetic datasets reproduce byte-for-byte:

```powershell
# Run from the repository root:
.venv\Scripts\python scripts\generate_datasets.py --check
```

To exercise the live API end to end against a running server:

```powershell
# Run from the repository root while the server from "Build and start" is up:
.venv\Scripts\python scripts\demo_journey.py
```

## Upload and runtime limits

Every bound is enforced by the backend and echoed by `GET /api/health`; the UI
shows the same numbers in the same units. An upload over a limit is rejected
with an actionable message — it is never silently truncated.

| Default limit | Scope |
|---------------|-------|
| **25 MiB** raw upload | Request body bytes, checked server-side while reading. |
| **256 MiB** parsed dataset | Estimated in-memory size of the parsed frame, not process RSS. A small file of long text can hit this. |
| **10,000 rows**, **100 columns** | Shape limits, independent of byte size. Minimum 20 rows and 2 columns. |
| **384 MiB** store | Combined parsed footprint of stored datasets; least-recently-used entries are evicted. A dataset larger than the whole budget is rejected. |
| **500 combined rows** | Upper bound for the expensive near-duplicate distance analysis; beyond it that check is skipped with a stated reason. |
| **8 datasets / 16 runs**, **1 hour TTL** | In-memory store bounds. Restarting the server clears everything. |

Override the defaults with `SPLITSCOPE_MAX_UPLOAD_BYTES`,
`SPLITSCOPE_MAX_PARSED_BYTES`, `SPLITSCOPE_MAX_ROWS`,
`SPLITSCOPE_MAX_COLUMNS`, `SPLITSCOPE_MAX_STORE_BYTES` and the other variables
listed in `backend/app/core/config.py`. Raising the byte cap does not raise the
row, column, parsed-memory or store limits.

**Representative local measurement** (Windows 11, one local process, synthetic
10,000 × 100 numeric-text CSV of **10.49 MiB**): upload accepted in 2.75 s with
a server-reported parsed footprint of **63.90 MiB**; a generated 80/20 random
split audited in 2.64 s. This is a single-request check that the old 10 MiB cap
can be raised safely for this shape — not a throughput benchmark, and not a
claim about real-world corpora.

## Synthetic demos and evaluation

The six bundled demo datasets (in `datasets/`, described by
`datasets/manifest.json`) are small, deliberately constructed fixtures that
teach one leakage pattern each. The synthetic evaluation suite runs the audit
engine against hand-built fixtures and these demos with independently computed
ground truth. Methodology, results, triage history and limitations are
documented in **[EVALUATION.md](EVALUATION.md)**; the project log is in
**[STATUS.md](STATUS.md)**.

## Important limitations

* **Synthetic evaluation does not establish real-world detection accuracy.**
  The fixtures are tiny and clean by design; passing them shows the checks
  implement their stated definitions, nothing more.
* **Near-duplicate findings are similarity candidates**, not proven leakage;
  the check's severity is capped at "medium" by design.
* **Random and stratified splits do not guarantee entity isolation or class
  balance** in any given draw (stratified preserves class proportions only).
* **Concurrency, large-scale performance, and real-world corpora were not
  evaluated.** Datasets are bounded by documented upload limits.
* **Local, single-user, no authentication.** Uploads are held in a bounded,
  in-memory store with a TTL (never written to disk); the only files on disk
  are the committed demos and any report you explicitly download. CORS is
  restricted to the documented local development origins. Do not expose the
  server to untrusted networks.
