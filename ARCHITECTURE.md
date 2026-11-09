# Architecture

SplitScope is a FastAPI backend that also serves the built React frontend.
State is held in memory; nothing user-supplied is written to disk.

## Backend (`backend/app`)

| Package | Role |
|---------|------|
| `api` | FastAPI routers, request/response schemas, error handlers |
| `core` | Configuration and runtime limits |
| `audit` | Dataset loading, role validation, leakage rules (`audit/rules`), scorecard |
| `splits` | Random, stratified, group and chronological split generation and comparison |
| `research` | Study metadata, column roles, profiling, run history and manifests |
| `explore` | Sampling, brushing and aggregate statistics for the explorer |
| `models` | OLS and logistic regression, leakage-safe predictive pipelines |
| `causal` | Graph schema, d-separation, backdoor identification, effect estimation (`causal/estimation`) |
| `reports` | Research dossier composition, methodology text, HTML export |
| `evaluation` | Synthetic fixtures and independent oracles used by `scripts/evaluate_synthetic.py` |
| `synthetic` | Generators for the demo datasets in `datasets/` |

Each leakage rule is a separate class in `audit/rules` that returns a status
(found, clear, not evaluated, unsupported, disabled), counts, and example row
ids. A rule that did not run is never reported as clear.

## Frontend (`frontend/src`)

| Directory | Role |
|-----------|------|
| `views` | One component per workbench page |
| `components` | Shared UI: role editor, findings, charts, report preview |
| `explore`, `causal`, `estimation`, `research` | Feature-specific components and state |
| `state` | App state and reducers |
| `api` | Typed client for the backend |
| `styles` | `tokens.css` (palette, type, spacing) and component styles |

Unit tests are in `frontend/tests` (Vitest) and browser journeys in
`frontend/e2e` (Playwright).
