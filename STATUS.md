# SplitScope — Status Report

**Date:** 2026-10-18 (finalization added; Stages 4a–4d recorded below)
**S11 (2026-11-07):** COMPLETE — final release engineering shipped on branch
`v2-premium-visual-foundation` as three verified checkpoints. S11-A
independently re-executed the full S10 gate on `f7103ea` (backend 620 passed,
synthetic oracle 41/41 with 61 checks, vitest/TS/ESLint/build clean, 39
real-backend Playwright journeys) and walked the product in a real browser at
1440 and 390; it repaired a ~1-in-N flaky identification unit test and a
run-count format defect, and inventoried the motion, transition and bundle
gaps. S11-B fixed the highest-value usability defect found: **unsaved causal
graph drafts were silently destroyed by ordinary navigation** — the draft
reducer now lives above the route switch (regression-tested; live-verified
add node → leave → return). It also introduced the motion token system
(`--motion-fast/base/slow`, `--ease-standard/emphasis`) with a quiet keyed
stage transition that respects `prefers-reduced-motion`, normalized the
shared interaction transitions, and cut the main bundle **589.16 kB →
405.53 kB (−31 %)** by route-level code splitting Data/Model Lab/Compare/
Report Studio behind labelled loading fallbacks. S11-D re-ran the full gate
on the final tree: **620 backend, 246 frontend, oracle 41/41, TS/ESLint
clean, build OK, Playwright 39/39 (8.8 min, retries 0)**; zero horizontal
overflow at 390 px; inspected screenshots in `docs/screenshots/s11/`.
Reviews and handoff: `docs/S11_INITIAL_AUDIT.md`,
`docs/S11_HCI_USABILITY_REVIEW.md`, `docs/S11_INTERACTION_AND_MOTION_SYSTEM.md`,
`docs/S11_VISUAL_REFINEMENTS.md`, `docs/S11_ACCESSIBILITY_REVIEW.md`,
`docs/S11_PERFORMANCE_REVIEW.md`, `docs/S11_SECURITY_REVIEW.md`,
`docs/S11_FINAL_VERIFICATION.md`, `docs/S11_RELEASE_HANDOFF.md` — verdict:
**RELEASE READY** for the intended local/private research demo (not a claim
of production security). See `docs/S11_RELEASE_HANDOFF.md`.
**S10 (2026-11-07):** COMPLETE — the integrated Research Dossier, experiment
history, reproducibility infrastructure, methodology generation and
publication exports shipped on branch `v2-premium-visual-foundation`.
S10-A added a typed, read-only Research History projection of the bounded
in-memory run store (new `#/history` stage, step 11) with per-run identity,
parameters, staleness re-checks and honest "not recorded" states, plus
portable metadata-only reproducibility manifests with independently
verifiable canonical-JSON sha256. S10-B extended the S7 dossier engine to
schema **1.1.0 (additive)** with seven server-authored sections composed
from stored estimation runs — causal graph, identification, causal
estimation, subgroups, robustness, what-if and a methodology generator
(concise/technical) that invents nothing — with refusal of cross-dataset,
stale and mismatched sources, and verbatim carriage of every caveat into
JSON, preview and printable HTML. S10-C added the deterministic
publication SVG of the causal graph (rendered from the stored spec, never a
canvas screenshot), and two real-backend Playwright journeys verifying the
complete workflow (audit → gated estimation → three research experiments →
integrated dossier → downloads). 20 new backend tests (**620 total**), 9 new
frontend tests (**245 total**), 2 new Playwright journeys (**39 total**),
synthetic oracle still 41/41 (61 checks). See `docs/S10_HANDOFF.md`.
**S9C (2026-11-07):** COMPLETE — advanced causal research shipped on branch
`v2-premium-visual-foundation` as a new `#/research` stage (step 9, Causal
research) with three focused views that build strictly on a stored estimation
run: **Subgroup effects** (S9C-A: subgroup ATEs as cross-fitted AIPW
pseudo-outcome averages with influence-function uncertainty and valid
between-group contrasts; treatment descendants refused; small/missing/overlap-
fragile subgroups reported honestly, never fabricated) in a forest plot with
the overall reference; **Robustness** (S9C-B: reproducible seeded subsampling
and placebo-treatment experiments with per-repetition failure recording, plus a
5×5 hypothetical-unmeasured-confounder simulation grid explicitly labelled a
scenario, not a bound); and **What-If** (S9C-C: model-based conditional outcome
predictions from the verified g-computation model with disclosed cohort
defaults, extrapolation warnings and no invented intervals). One behaviour-
preserving extraction (`estimationErrors.ts`); no loosened assertions. 45 new
backend tests (**581 total**), 31 new frontend tests (**236 total**), 4 new
real-backend Playwright journeys (**37 total**), synthetic oracle still 41/41
(61 checks). See `docs/S9C_HANDOFF.md`.
**S9B (2026-11-06):** COMPLETE — the Causal Effect Estimation Studio shipped on
branch `v2-premium-visual-foundation`: a dedicated `#/estimation` stage (step 8)
that gates every run behind the S9A readiness check, requires a saved S8C graph
and an explicit run, and presents five analytical views — Effect summary
(dot-and-interval), Covariate balance (Love plot), Overlap (per-arm propensity
histograms plus a 20-bin count/share table), Weights (raw vs Kish effective
sample size) and Methodology (cohort accounting, identification verdict,
uncertainty, provenance, limitations). Results carry deterministic named
staleness reasons, partial failures are shown as failures rather than zeros,
unavailable intervals are never fabricated, and SVG/PNG/CSV/JSON figure exports
and verbatim run JSON are produced from the plotted values. One bounded backend
diagnostic was added (fixed 20-bin per-arm propensity histogram) plus a
deterministic `causal_effect` demo with a documented true ATE of 1.5 and a
confounded naive difference of 3.1724. 6 new backend tests (**536 total**), 60
new frontend tests (**205 total**), 4 new real-backend Playwright journeys (**33
total**), synthetic oracle still 41/41 (61 checks); responsive QA at 1440, 1024,
768 and 390 with inspected screenshots. No ATT/CATE, sensitivity or subgroup
analysis yet (S9C, not started). See `docs/S9B_HANDOFF.md`.
**S9A (2026-11-06):** COMPLETE — scientific causal effect estimation shipped on
branch `v2-premium-visual-foundation`: a mandatory S8C identification gate
(fingerprint match, structural re-validation, exact backdoor verdict on the
client-named adjustment set), explicit cohort/treatment/outcome preparation
with full row accounting, three estimators (g-computation regression
adjustment, Hájek IPW, cross-fitted AIPW on leakage-safe sklearn pipelines),
influence-function and fully-refitting bootstrap uncertainty, pre/post-weighting
covariate balance and overlap/positivity diagnostics, a shared-cohort three-way
comparison, and five API routes with stored, staleness-rechecked runs.
45 new backend tests (499 total passing), including known-effect synthetic
fixtures, independent statsmodels/formula cross-checks and a cross-fit leakage
detection test; synthetic oracle still 41/41 (61 checks), frontend 145 unit
tests, 29 Playwright journeys. No estimation UI yet (S9B), no sensitivity or
subgroup analysis (S9C). See `docs/S9A_HANDOFF.md`.
**S8C (2026-11-06):** COMPLETE — graphical causal identification shipped on
branch `v2-premium-visual-foundation`: exact Bayes-ball d-separation (verified
against an independent moralization oracle over all 543 labelled 4-node DAGs,
13,032 exhaustive queries), classical backdoor evaluation and bounded honest
adjustment-set search, identification status API (four read-only endpoints),
and an Authoring | Identification mode in the Causal Lab with scientific-signature
staleness handling. 48 new backend tests (454 total passing), 9 new frontend
unit tests (145 total), 4 new real-backend Playwright journeys (29 total).
No effect estimation yet (S9). See `docs/S8C_HANDOFF.md`.
**S8B (2026-11-06):** COMPLETE — the interactive Causal Lab shipped on branch
`v2-premium-visual-foundation`: `@xyflow/react` DAG canvas, dataset-scoped graph
authoring against the S8A API (create/save/validate/import/export), assumption
registry UI, 32 new unit tests and 3 real-backend Playwright journeys
(25 browser journeys total passing). No identification or estimation yet (S8C).
See `docs/S8B_HANDOFF.md`.
**S8A (2026-11-05):** COMPLETE — causal-graph foundation delivered on branch
`v2-premium-visual-foundation`: validated versioned DAG specs, structural validation
engine, assumption registry, dataset-scoped graph API and 33 new backend tests
(406 total passing); no identification or estimation yet (S8C), no editor (S8B).
See `docs/S8A_HANDOFF.md`.
**Stage 3e:** COMPLETE — the live API journey and the actual browser workflow both pass.
**Stage 4a:** COMPLETE — reproducible Playwright E2E against the production build, plus
stale-build-artifact prevention.
**Stage 4b:** COMPLETE — frontend unit/component test suite (28 tests) and a working ESLint
flat configuration.
**Stage 4c:** COMPLETE — reproducible synthetic evaluation of the audit engine
(37 cases / 53 checks, all passing).
**Stage 4d:** COMPLETE — split-strategy verification gaps closed: random,
stratified and chronological assignments verified end to end (suite now 41 cases /
61 checks).
**Finalization (2026-10-18):** COMPLETE — README, CI configuration, verified
fresh installation, complete local verification, Git-handoff review. GitHub-hosted
CI execution: NOT RUN (no remote authorized). Details in "Finalization" below.
**Latest (2026-10-19):** COMPLETE — guided upload setup for files with and
without a split column, validated with the real 1,143 × 13 `WineQT.csv`:
218 backend tests, 70 frontend tests, 4 Playwright journeys, 20/20 real-file
checks. See section 12.

This revision replaces the earlier Stage 3e report, which contained claims that were
not supported by evidence. Corrections are listed in "Corrections to the earlier
report".

---

## Finalization (2026-10-18): reproducible install, docs, CI config, full verification

### Test-count reconciliation

Verified with `pytest --collect-only`: **200 collected test cases** —
`test_api` 24, `test_canonical` 20, `test_chronology` 11,
`test_demo_journey_http` 1, `test_demos` 14, `test_duplicates` 13,
`test_entity` 10, `test_evaluation` 21, `test_io` 15,
`test_near_duplicates` 14, `test_reports` 11, `test_roles` 16,
`test_splits` 19, `test_target_copy` 11. Arithmetic: 195 at Stage 4c
(178 pre-existing + 17 runner tests) + 4 runner tests + 1 comparison test =
200. All 200 are test *functions* (one collected case each; no parametrisation),
so "tests" and "collected cases" coincide here. The Stage 4d section's earlier
"5 new eval tests" phrasing was corrected in place; no test was changed to fit
a count.

### Fresh installation (clean copy, only declared dependencies)

A clean copy of the project (excluding `.venv`, `node_modules`, `dist`,
`__pycache__`, `.tools/`, `.stale-artifacts/`, the bundled node zip/dir, caches
and test outputs — 1.5 MB) was made in the temp directory and set up with only
the declared manifests:

| Step (in the clean copy) | Result |
|---|---|
| `python -m venv .venv` + `pip install -r backend/requirements.txt -r backend/requirements-dev.txt` | PASS (exit 0) |
| `python -m pytest -q` (backend) | PASS — 200 passed |
| `python scripts/evaluate_synthetic.py` | PASS — 41/41 cases, 61/61 checks, exit 0 |
| `npm ci` in `frontend/` (from `package-lock.json`) | PASS — 301 packages, exit 0 |
| `npx playwright install chromium` | PASS (exit 0); note: the browser binary was already present in the machine-level Playwright cache, so a from-zero download was not exercised locally. CI uses `install --with-deps chromium`. |
| `npm run test` / `lint` / `typecheck` / `build` | PASS — 28 tests; lint 0 warnings; no source-adjacent `.js` emitted |
| `npx playwright test` (webServer = clean-copy venv python) | PASS — 2/2, exit 0 |

No globally installed application package was used to mask a missing
declaration; the clean venv and `npm ci` use only `requirements*.txt` and
`package-lock.json`.

### Complete local verification (working environment, after the last
non-documentation change)

| Check | Result |
|---|---|
| `python -m pytest -q` (backend) | **PASS** — 200 passed, exit 0 |
| `python scripts/evaluate_synthetic.py` | **PASS** — 41/41, 61/61, exit 0 |
| `python scripts/generate_datasets.py --check` | **PASS** — committed datasets reproduce exactly |
| `npm run test` / `lint` / `typecheck` / `build` | **PASS** — exit 0 each; no source-adjacent `.js` recreated |
| `npx playwright test` (existing suite) | **PASS** — 2/2, exit 0; managed webServer confirmed stopped (no LISTENING socket on 8123) |
| Primary startup `python -m app.main` | **PASS** — `/api/health` 200, `/` serves the built app |
| `python scripts/demo_journey.py` (live API) | **PASS** — 9/9 steps, exit 0; server stopped afterwards (ownership verified before termination) |
| GitHub-hosted CI execution | **NOT RUN** — no remote authorized; the workflow is configuration only |

### Documentation and CI changes

| File | Purpose |
|---|---|
| `README.md` (new) | What SplitScope does; the five checks + diagnostics and four split strategies; Python 3.11 / Node ≥ 20.18 requirements; PowerShell setup (`venv` + `pip install -r requirements*.txt`, `npm ci`); build + single-command startup; optional Vite dev server; every verification command with working directory; synthetic demos + evaluation reproduction; honest limitations (synthetic ≠ real-world accuracy, near-duplicates are candidates, random/stratified do not guarantee entity isolation, no concurrency/large-scale/real-corpus claims, in-memory single-user store with TTL and bounds, no outbound network calls at runtime — verified by scanning `app/`). No license, badges, screenshots or public URLs were invented. |
| `.github/workflows/ci.yml` (new) | Two proportional jobs on `ubuntu-latest`, Python 3.11 + Node 20, pinned installs, pip/npm caching. Backend: tests, synthetic evaluation (non-zero exit fails the step), dataset `--check`. Frontend: `npm ci`, unit tests, lint, typecheck, build, `playwright install --with-deps chromium`, existing E2E (Playwright manages and stops its own backend; retries stay 0), report artifacts uploaded on failure. No secrets or external services. **Configuration inspected, not executed on GitHub runners.** |
| `.gitignore` (hardened) | Added `.env*` (defensive; no such files exist today), `.freebuff/` (local app state), `evaluation_output/`. |
| `STATUS.md` | Corrected the Stage 4d test-count phrasing; this section. |

### Remaining limitations

All earlier limitations stand (see `EVALUATION.md`): synthetic fixtures only,
no population metrics, near-duplicates are candidate findings, small fixtures
only for split strategies, no concurrency/large-scale/real-world validation.
Additionally: the local machine runs node from a repo-local download (not on
`PATH`); README/CI use standard `npm`/`npx` so no such dependency is implied.

### Exact remaining steps before GitHub publication (next handoff)

1. `git init` in the repository root; review `git status` against the hardened
   `.gitignore` (nothing from `.venv`, `node_modules`, `.tools`, `dist`,
   `.stale-artifacts`, `test-results`, `playwright-report`, `.freebuff`,
   `.env*` or `evaluation_output` should appear).
2. Stage the intended source inventory (code, `datasets/`, `README.md`,
   `EVALUATION.md`, `STATUS.md`, `.github/workflows/ci.yml`, lockfiles) and
   make the initial commit.
3. Create the GitHub repository (user decision: private first), push, and
   enable Actions; the workflow must be confirmed green **on GitHub-hosted
   runners**, which has not been run here.
4. Decide on a license deliberately — none has been added.
5. After the first successful CI run, record the badge/URL only if desired.

---

## Stage 4d (2026-10-17): split-strategy verification + evaluation milestone closed

Closes the one gap Stage 4c named: random, stratified and chronological
strategies were not verified end to end as generated assignments passed into
auditing. Full write-up in **`EVALUATION.md`**.

### Expectation-independence review (first task of 4d)

The oracles were re-read in full: each is written from the rule's documented
definition with plain pandas/numpy and imports no production code (its module
docstring explains the convention choices, e.g. quartile interpolation).
Re-confirmed that the six Stage 4c corrections rest on contract + fixture
arithmetic; `EVALUATION.md` now carries six tiny hand-worked count examples
(dup denominators, entity share, target coverage, near-pair distance,
chronological tie cut, stratified allocation) pinning the ambiguous count
definitions. No valid evaluation code was rewritten.

### Cases and invariants added

Four new evaluation cases (fixtures deliberately have **no split column** —
the split under audit is the generated assignment):

| Case | Contract verified |
|------|-------------------|
| `split_random_repeated_entities` | 12 rows, three 4-row entities, seed 17 → 9/3 rows. Hand-argued: no entity fits wholly into the 3-row test side, so overlap ≥ 1 whatever the draw; all 3 test rows necessarily in shared entities → finding, severity high. The overlap count (2 here) is cross-checked against an independent set-intersection recount instead of being pinned. |
| `split_stratified_class_preservation` | 6 A / 4 B at fraction 0.5 → 5 test rows allocated exactly 3 A / 2 B (integer proportions, hand-checkable), complement on train. |
| `split_chronological_distinct` | Ten distinct timestamps; cut at sorted position 7 → train Jan 1-7, test Jan 8-10; ordering verified from fixture timestamps joined to the assignment. |
| `split_chronological_boundary_tie` | Four rows share Jan 7; the requested cut lands inside the tie and the documented policy moves it left → train 6 / test 4, tie group intact. |

Runner behaviour added (JSON `split_facts` per generated-split case, including
the pre-existing group-holdout case): always-on invariants that fail the case
on violation — exactly-once assignment of every row (masks **and** exported
row-id lists; no unknown/duplicate ids), non-empty sides, input frame
unchanged (deep-copy comparison), deterministic regeneration with the same
configuration, independent overlap recount equal to the SS-ENT-001 metric, and
independent chronology status equal to SS-CHR-001's. Hand-written
`expected_split_facts` pin sizes/ordering/class counts per case.

Focused tests (5 new runner tests + 1 comparison integration test):
split facts recorded and pass; a deliberately wrong expected fact fails;
stratified class counts verified; random overlap cross-check holds; and
`compare_splits` generating stratified + chronological candidates end to end
with assignment row-id integrity and chronology verdict agreeing with
temporal facts computed from original fixture timestamps. Infeasible-strategy
rejections were already covered in `tests/test_splits.py` and were not
duplicated.

### Actual results

- `python scripts/evaluate_synthetic.py` → **41/41 cases, 61/61 checks, exit 0**.
  All four new cases passed on the first run (no triage needed).
- `python -m pytest -q` (backend) → **200 passed**. Reconciliation (verified
  by `pytest --collect-only`): 195 at Stage 4c (178 pre-existing + 17 runner
  tests) + 4 new runner tests in `test_evaluation.py` (now 21) + 1 new
  comparison test in `test_splits.py` (now 19) = 200 collected test cases.
  (An earlier draft of this section said "5 new eval tests"; the correct
  split is 4 + 1.)
- Reproducibility: two `--output-dir` runs produced identical JSON after
  removing only `generated_at_utc`.
- Frontend: untouched; no frontend/Playwright re-run required.
- One defect in the milestone's own new code: a first-draft assertion in the
  new comparison test demanded equal class counts across sides (6/9 vs 2/3);
  the contract preserves class *proportions*, so the assertion was corrected
  to a proportion-equality check before the test was ever committed green.
  No product defect found.

### Stage 4 acceptance criteria — review

The original specification was given in conversation and is not checked into
the repository; the review below uses the outstanding-work list that
`STATUS.md` itself tracked after Stage 4a/4b:

| Criterion (as tracked in STATUS) | Status |
|----------------------------------|--------|
| Reproducible E2E verification + stale-artifact prevention (4a) | ✅ done in Stage 4a |
| Frontend unit/component tests + working ESLint (4b) | ✅ done in Stage 4b |
| Synthetic evaluation script with deterministic run, JSON output, honest metrics (4c) | ✅ done in Stage 4c |
| Split strategies verified end to end as generated assignments audited (4d) | ✅ done in this stage |
| `backend/requirements.txt` note about the missing evaluation script | ✅ resolved (Stage 4c) |

No concrete Stage 4 requirement remains outstanding. Items below are
**finalization work explicitly outside Stage 4** — proposed, not implemented:

1. **Fresh environment install**: from a clean clone, `pip install -r
   backend/requirements.txt` (plus `requirements-dev.txt`) and Node install for
   the frontend; confirm both boots.
2. **Documented startup**: README with the two-terminal startup commands
   already recorded in STATUS §8, plus verification commands.
3. **Complete verification commands**: one documented block running backend
   tests, `scripts/evaluate_synthetic.py`, `scripts/generate_datasets.py
   --check`, `scripts/demo_journey.py`, frontend `npm run test`, lint, build
   and Playwright.
4. **README + limitations**: user-facing README with the honest scope
   statement (synthetic evaluation ≠ real-world accuracy).
5. **CI**: workflow running the verification block above; Stage 4a already
   documents the generation `--check` guard for CI.
6. **Local Git preparation**: init, sensible `.gitignore` (exclude
   `__pycache__`, `.tools/`, `node_modules`, `test-results`, generated output
   dirs, `.stale-artifacts` handling decision), initial commit.
7. **Eventual GitHub publication**: only with explicit user go-ahead; publish
   nothing privately-dataset-related (all six demos are synthetic and
   committed by design).

---

## Stage 4c (2026-10-17): reproducible synthetic evaluation of the audit engine

Engineering evaluation on deterministic synthetic fixtures — not evidence of
real-world detection accuracy. Full write-up in **`EVALUATION.md`** at the repo root.

### What was built

| File | Purpose |
|------|---------|
| `backend/app/evaluation/oracles.py` | Independent ground truth written from each rule's documented definition. Imports no rule code; never runs a detector. Used for the six committed demo datasets, where planted counts are not assumed to equal total detectable cases. |
| `backend/app/evaluation/cases.py` | 37 cases in a stable order: 31 hand-built fixtures with hand-written expectations (statuses, severities, exact counts, metrics, evidence row ids, hand-calculated distances), plus the 6 demos with oracle-derived complete expectations. Includes `RULE_UNITS` (evaluation unit per rule). |
| `backend/app/evaluation/runner.py` | Executes each case through the public audit interfaces (`audit_existing_split`, or `generate_split` + `run_audit` like the split comparison), compares expectations, verifies evidence (cited row ids resolve; truncation flags are consistent), aggregates results. |
| `scripts/evaluate_synthetic.py` | CLI with deterministic default run, `--output-dir`, `--case`, `--list`; human summary + `evaluation_results.json`; exit 0 = all pass, 1 = expectation mismatch, 2 = unevaluable case or bad invocation. |
| `backend/tests/test_evaluation.py` | 17 focused runner tests: known-correct case passes; deliberately wrong expectations (status/finding-count/count/evidence) fail; missing roles/rows/unusable roles/malformed rows report ERROR; exit statuses 0/1/2 (errors outrank failures); unknown `--case` raises clearly; two runs identical minus timestamp. |

Coverage per check: cross-split vs within-split duplicates, multiple rows per
signature, missing-vs-literal (incl. `missing_tokens`), target/metadata
exclusion; shared/disjoint/within-split entities, missing identifiers, group
holdout isolation; chronological order/violation/equal-ties/invalid-timestamp
eligibility/split-with-ties; exact target copy/non-match/partial
missingness/constant target/constant feature/below-sample/majority artefact;
near-duplicate hand-calculated distances inside/at/outside threshold, robust
scaling, constant+missing handling, oversize skip and seeded sample,
non-numeric unsupported, default disabled; diagnostics case asserting class
imbalance and distribution shift produce zero leakage findings.

### Actual results

- `python scripts/evaluate_synthetic.py` → **37/37 cases, 53/53 checks, exit 0**.
- First run: 31/37. The six mismatches were triaged one by one: **4 were
  wrong expectations / arithmetic in the new suite, 2 were invalid fixtures**;
  **no detector bug was found** and no expectation was edited merely to match
  output. Detail and reasoning in `EVALUATION.md`.
- Reproducibility: two consecutive runs produce identical JSON after removing
  `generated_at_utc` (compared programmatically).
- `python -m pytest -q` (backend) → **195 passed** (178 pre-existing + 17 new).
- Frontend: not touched (no product code changed), so no frontend checks were run.

### Limitations

Synthetic fixtures only; exact per-case assertions instead of population
metrics (no precision/recall, no universal accuracy score); near-duplicate
results are candidate similarity findings, not leakage labels; bounded example
display never used to infer row-level totals. Full limitations in `EVALUATION.md`.

Stage 4c stops here. This also resolves the older STATUS note about a missing
`scripts/evaluate_checks.py`: the synthetic evaluation now exists as
`scripts/evaluate_synthetic.py` (it does not use httpx; the API journey script
already covers that path).

---

## Stage 4b (2026-10-17): frontend unit/component tests + ESLint

### Test infrastructure

* **Vitest 2.1.8** (already a devDependency) with **jsdom 25**, Testing Library
  (`@testing-library/react` 16.1, `jest-dom` 6.6, `user-event` 14.5 — all already present;
  **no new dependency was added, so the lockfile is untouched**).
* New standalone `frontend/vitest.config.ts`. Deliberately **not** in `vite.config.ts`:
  vitest 2.x bundles vite 5's types and the app uses vite 6, so a `test` block next to
  vite's `defineConfig` makes the two `UserConfig` types mutually unassignable (verified:
  typecheck failed with exactly that error). The React plugin is also omitted there for
  the same reason; Vitest transforms TSX through esbuild with the automatic JSX runtime.
* `frontend/tests/setup.ts` — adds the jest-dom matchers; Testing Library cleanup runs
  via the global `afterEach` that `globals: true` provides.
* `frontend/tests/fixtures.ts` — small hand-written typed fixtures (dataset, roles,
  validation, findings, audit/comparison/preview/checks/demo/health responses) written
  against `src/api/types.ts`; expectations are independently specified, never derived by
  calling the code under test.
* Component tests live in `frontend/tests/`, separate from Playwright's `e2e/`; vitest
  excludes `dist`, `test-results`, `playwright-report`, `e2e` and `.stale-artifacts`.
* `npm run test` = `vitest run` (single run, exit status reflects results);
  `npm run test:watch` for watch mode.

### Tests added (28 across 4 files, all passing)

**`tests/AppState.test.tsx` (7)** — the real `AppProvider` driven through its public
`useApp()` contract; `src/api/client` is mocked at the module boundary:

* mounting issues the health/checks/demos requests once and exposes the responses to
  consumers, ending in the idle state;
* a failed catalogue request produces the error status with the backend's message and
  `reloadCatalogue()` recovers once the backend answers again;
* StrictMode double-mounting leaves one consistent catalogue, not a busy or duplicated
  state; repeated reloads end idle.

**`tests/RoleEditor.test.tsx` (12)** — real component, fixtures injected as props:

* existing selections render (split/target/entity selects, train/test value inputs,
  checked feature, columns taken by another role are not offered as features);
* edits emit the expected patches (target select, feature toggle on/off, feature
  reorder with the ends disabled, split select emits cleared train/test values);
* validation: backend error/warning issues rendered verbatim with their hints;
  "Roles are internally consistent" only when the last validation passed;
* clearing the optional split emits `split: null` (with cleared value fields) and
  drops the value editors once applied.

**`tests/FindingCard.test.tsx` (6)** — real evidence, not placeholders: expansion
reveals the finding's own rationale, description, counts with denominators, example
blocks with the actual row ids and details, assumptions, limitations and recommended
action; the counts-only variant says so instead of inventing rows; truncation is
announced; the evidence-view action appears only when a handler is given;
`FindingSummaryLine` distinguishes "no findings" from a severity breakdown.

**`tests/AuditView.test.tsx` (3)** — findings and checks-that-did-not-run stay in
distinct sections with the not-passing callout; "Open in evidence view" selects the
finding that was opened (`selectedFinding.rule_id`, `origin: 'audit'`, navigate
`'evidence'`); the zero-findings empty state is shown alongside — not instead of — the
not-evaluated section.

### Bug discovered and fixed: stale in-flight results leak into a new dataset

Reproduced first with controlled promises, before touching any code: `loadPreview`,
`runAudit` and `runComparison` captured the dataset at call time but wrote their result
unconditionally, so a response that resolved after another dataset was loaded was
applied to the **new** dataset's view (an audit result labelled as belonging to the new
dataset). The failing tests are `AppState.test.tsx` "ignores a preview/audit that
resolves after the dataset has changed" — both failed with the stale value applied.

Fix (smallest justified): a `generation` ref in `AppProvider`, incremented whenever a
new dataset becomes current (`applyLoaded`) or the session is reset. `loadPreview`,
`validateRoles`, `runAudit` and `runComparison` capture the token before their request
and discard the response if it changed. No API contract or audit semantics changed;
after the fix both race tests pass and the E2E suite still passes.

### ESLint

New `frontend/eslint.config.js` (flat config) using the already-installed ESLint 9,
`@eslint/js`, `typescript-eslint` 8, `eslint-plugin-react-hooks` 5 and `globals`:

* `**/*.ts(x)`: JS recommended + typescript-eslint recommended; `no-explicit-any: error`
  (no global any-allowance), unused-vars with `_` escape, `consistent-type-imports`,
  `no-console` (warn/error allowed), `eqeqeq`, `prefer-const`.
* `src/**`: browser globals + `react-hooks/rules-of-hooks: error`,
  `exhaustive-deps: warn`.
* `tests/**`: DOM + node globals; `no-explicit-any` off **only here** (fixtures
  deliberately build partial API payloads); `no-console` off.
* `e2e/**`, `playwright.config.ts`, `vite.config.ts`, `vitest.config.ts`,
  `eslint.config.js`: node globals.
* Ignores `dist`, `node_modules`, `playwright-report`, `test-results`,
  `.stale-artifacts`.
* One lint-driven code change only: the `typeof import(...)` type annotation in two
  test files became an explicit `import type * as ApiClient` (the
  `consistent-type-imports` rule forbids inline `import()` annotations). No blanket
  disables, no formatting churn, no TypeScript checks weakened.

Note: `eslint-plugin-react-hooks` 5.x ships only the legacy config shape, so the plugin
and its two rules are registered explicitly rather than via `extends`.

### Commands and results (all executed)

| Command | Result |
|---------|--------|
| `npm run test` | exit 0 — **28 passed** across 4 files (AppState 7, RoleEditor 12, FindingCard 6, AuditView 3) |
| `npm run lint` (`--max-warnings 0`) | exit 0 |
| `npm run typecheck` | exit 0 (app + node projects) |
| `npm run build` | exit 0 — `dist/assets/index-iyEA11xA.js` |
| `npm run test:e2e` | exit 0 — **2 passed** (re-run after the AppState race fix) |
| `.js` beside sources after all runs | 0 |
| backend `python -m pytest tests/ -q` | not re-run — no backend file changed in Stage 4b (178 passing at Stage 4a) |

### Reproduction

```bash
cd frontend
npm run test          # 28 component/unit tests, single run
npm run test:watch    # watch mode
npm run lint          # eslint . --max-warnings 0
npm run typecheck && npm run build
npm run test:e2e      # full Playwright suite (unchanged)
```

### Files changed in Stage 4b

| File | Why |
|------|-----|
| `frontend/vitest.config.ts` | New. jsdom env, setup file, include/exclude scoping. |
| `frontend/vite.config.ts` | Reverted to pure vite config (the `test` block moved to `vitest.config.ts` to keep vite 6 / vitest-bundled-vite 5 types apart). |
| `frontend/tsconfig.node.json` | Include `vitest.config.ts` in the node project. |
| `frontend/tests/setup.ts` | New. jest-dom matchers; cleanup via global afterEach. |
| `frontend/tests/fixtures.ts` | New. Hand-written typed API fixtures. |
| `frontend/tests/AppState.test.tsx` | New. 7 provider tests incl. the two stale-race reproductions. |
| `frontend/tests/RoleEditor.test.tsx` | New. 12 role-editor tests. |
| `frontend/tests/FindingCard.test.tsx` | New. 6 finding-card tests. |
| `frontend/tests/AuditView.test.tsx` | New. 3 audit-view presentation tests. |
| `frontend/src/state/AppState.tsx` | Fix. Generation token discarding stale preview/validation/audit/comparison responses. |
| `frontend/eslint.config.js` | New. Flat config, scoped per area. |

### Remaining limitations (Stage 4b)

* Component tests mock the API boundary; cross-layer guarantees remain the E2E suite's
  job (Playwright, real backend, production build — still Chromium-only).
* Not covered by unit tests yet: ComparisonView, ExportView, EvidenceView detail
  rendering, AuditConfigEditor, charts. Natural next milestone.
* `eslint-plugin-react-hooks` 5.x has no flat `recommended-latest` config; the two hooks
  rules are registered manually (equivalent coverage, no plugin auto-config).
* No git repository exists, so none of this is committed; the root `.gitignore` from
  Stage 4a still governs what would be committed.

---

## Stage 4a (2026-10-17): reproducible E2E + stale-artifact prevention

### Bug fixed: every `npm run` script was broken

`frontend/.npmrc` contained `script-shell=E:\Freebuff\node-v20.18.1-win-x64\node.exe`.
node.exe is not a shell, so npm ran each package script as `node "<script text>"` and it
failed with `MODULE_NOT_FOUND` — `typecheck`, `build`, `test`, `lint` and `test:e2e` were
all unusable. The setting was removed; npm now uses its default Windows shell.

### Bug fixed: the `typecheck` script emitted JavaScript beside the sources

Origin of the 19 quarantined files established (it is no longer a guess): `npm run
typecheck` executed `tsc -b --noEmit false --emitDeclarationOnly false` against projects
with **no `outDir`**, so type checking emitted `.js` next to every `.ts`/`.tsx` —
including `vite.config.js`, which then outranks `vite.config.ts` in Vite's config order.
Proof: running that exact command regenerated the identical set of 19 files.

Fix: `typecheck` is now `tsc -b && tsc -p tsconfig.app.json --noEmit`. Every project
config carries `noEmit: true`, build info goes to `node_modules/.tmp/`, and Vite output
stays in `dist/`. Verified: repeated `npm run typecheck` and `npm run build` runs leave
zero `.js` beside the sources.

### Quarantine preserved and excluded from every consumer

`frontend/.stale-artifacts/` is kept as-is and cannot enter:

* **compilation** — no tsconfig `include` covers it (app: `src`, `tests`, `vite.config.ts`;
  node: config files; e2e: `e2e/`), and `allowJs` is off;
* **Playwright** — `testDir` is `e2e/`;
* **vitest** — it contains no test files and the include patterns only match
  `*.test.*` / `*.spec.*`;
* **packaging** — `vite build` bundles only the `index.html` module graph;
* **source control** — a new root `.gitignore` covers `frontend/.stale-artifacts/`,
  `frontend/dist/`, `frontend/test-results/`, `frontend/playwright-report/`, caches and
  toolchains.

### Playwright configuration

* `frontend/playwright.config.ts`. Primary target: **the production build served by the
  backend** (`python -m app.main` serves `frontend/dist` at `/`) — the documented
  single-command startup path. `npm run test:e2e` builds first, so the bundle under test
  is never stale.
* Dedicated, configurable test port `SPLITSCOPE_E2E_PORT` (default **8123**), a fresh
  server process per run, `reuseExistingServer: false`, health-gated on `/api/health`,
  and stopped automatically when the run ends.
* Windows-safe: a plain `python -m app.main` command, no shell-specific syntax.
* `retries: 0`, `workers: 1`, `fullyParallel: false`; trace retained and screenshot taken
  on failure; list + HTML reporters; output under `test-results/` and `playwright-report/`.
* The specs are type-checked by a new `tsconfig.e2e.json` (noEmit, node types).

### E2E coverage

`e2e/happy-path.spec.ts` — one focused happy path, nothing mocked: open the app, load the
repeated-entity demo, confirm dataset readiness and roles (split/target/entity,
train/test values, 4 features, "Roles are internally consistent"), run the audit, expand
the SS-ENT-001 finding, open the evidence view and fetch the cited rows, build a
comparison of existing vs group holdout, assert the group row shows `0 groups` and the
existing row `N groups` with `N > 0` and `N` equal to the audit's number, then download
and validate the audit JSON report, the HTML report and the group + existing split CSVs:

* JSON parses and matches the expected report structure (`report_kind`, run id, input
  name/synthetic/row_count, roles, settings, findings consistent with
  `evaluation.findings_total`, SS-ENT-001 high with examples);
* HTML starts with a doctype, closes with `</html>`, contains the fixture values and the
  same shared-entity sentence, and contains no `<script>`;
* CSV has the exact header, one row per fixture row, unique `row_id`s equal to the
  fixture's `row-000001…` set, labels within {train, test} with both present, correct
  `strategy_kind`, and the existing assignment mirrors the fixture's own split column;
* **independent recomputation**: the fixture's entity column is joined to the downloaded
  assignments — group holdout shares **0** non-missing entities (train and test entity
  sets both non-empty), the existing split shares more than 0, and that number equals
  what the UI reported.

`e2e/error-recovery.spec.ts` — one focused failure path using a **real backend
rejection** (a 3-row CSV → HTTP 422), no request interception: the "Upload rejected
(validation_error)" alert appears with the backend's message and the structured
`rows_found`/`rows_required` detail, no dataset is loaded, the error can be dismissed,
and the app then loads a demo normally. The 422 is registered through
`allowFailure(...)`, so it is recorded as an intentional failure instead of being
silently filtered.

`e2e/fixtures.ts` — auto fixture: any browser page error or any unexpected failed /
HTTP >= 400 request from the application origin fails the test.

### Commands and results

| Command | Result |
|---------|--------|
| `npm run typecheck` | exit 0 (app + node + e2e projects) |
| `npm run build` | exit 0 — 44 modules, `dist/assets/index-BDJ5DJHQ.js` |
| `npm run test:e2e` | exit 0 — **2 passed** (happy path 1.4 s, error-recovery 0.6 s) |
| `npm run test:e2e -- e2e/happy-path.spec.ts` twice, sequentially | exit 0 both — 1 passed each, fresh server per run |
| listener on :8123 after the runs | none (only TIME_WAIT sockets) — server stopped |
| `.js` beside sources after all runs | 0 |
| `python -m pytest tests/ -q` (backend) | 178 passed — backend untouched in Stage 4a |
| `npm run lint` | exit 2 — pre-existing: no `eslint.config.js` (ESLint 9 requires one) |
| `npm run test` (vitest) | exit 1 — pre-existing: "no tests" (Stage 4 unit tests not written) |

### E2E setup and run

```bash
# One-time: put Node.js on PATH (npm scripts run local binaries through node_modules/.bin)
# Windows: add e.g. E:\Freebuff\.tools\node-v22.14.0-win-x64 to PATH
cd frontend
npm install                  # only if node_modules is missing
npm run test:e2e             # builds, starts its own backend on :8123, runs headless
npm run test:e2e:headed      # same flow, headed, for debugging
# Optional dedicated port: SPLITSCOPE_E2E_PORT=8200 npm run test:e2e
npx playwright show-report  # open the last HTML report
```

### Files changed in Stage 4a

| File | Why |
|------|-----|
| `frontend/package.json` | Non-emitting `typecheck`; `test:e2e` builds before Playwright; added `test:e2e:headed`. |
| `frontend/.npmrc` | Removed the broken `script-shell=node.exe` setting that broke every script. |
| `frontend/tsconfig.app.json`, `frontend/tsconfig.json`, `frontend/tsconfig.e2e.json` | e2e specs get their own noEmit project (node types) referenced from the solution config. |
| `frontend/playwright.config.ts` | New. Production-build target, dedicated port, fresh webServer, trace/screenshot on failure, no retries. |
| `frontend/e2e/happy-path.spec.ts`, `frontend/e2e/error-recovery.spec.ts`, `frontend/e2e/fixtures.ts` | New. The journey, the failure path, and failure diagnostics. |
| `.gitignore` | New. Keeps dist, Playwright output, caches, toolchains and the quarantine out of source control. |

---

## 1. Root cause of the reported integration failure

The earlier report claimed `scripts/demo_journey.py` produced "false negatives" because
"curl from subprocess does not set up the Python runtime context the server expects".
That explanation was wrong: HTTP clients need nothing from the server's runtime.

The script piped each JSON body into **curl's stdin but never told curl to read it**
(no `-d @-` / `--data-binary @-`). `subprocess.run(input=...)` therefore only closed a
stdin that curl never read, and every POST went out with an **empty body**. FastAPI
then rejected the request at the body level:

```
POST /api/audit            (request body: empty)
HTTP 422 {"error":{"code":"validation_error",
  "message":"The request body or query parameters are not valid.",
  "details":{"problems":[{"location":"body","message":"Field required","type":"missing"}],
             "problem_count":1}}}
```

Reproduced live against the running server with two probes that differ only in `-d @-`:

* `-X POST` + piped stdin, no `-d @-` → HTTP 422, `location: body`, `Field required` (exact match for the reported failure).
* same payload **with** `-d @-` → body parsed; server moved past validation and answered `410 expired_or_evicted` for the fake dataset id, proving the schema accepted the payload.

Two further defects in the same script (invisible while bodies were empty):

* compare payload: strategy entries omitted the required `label` and sent an unsupported `entity` key (`extra="forbid"` → 422);
* response reads used non-existent keys: `finding.evidence_examples` (real key: `examples`), `row.evaluation.entity_overlap_total` (real key: `entity_shared_groups`), and the script counted such steps as PASSED anyway.

### Two blockers found in the browser journey (both fixed)

1. **The frontend never fetched its catalogue.** `AppState` exposed `reloadCatalogue()`
   but nothing called it, so `health`, `checks` and `demos` stayed `null` forever:
   the overview stats, the check catalogue, the demo picker and the export page's
   health panel all sat on "has not loaded yet", and **a demo could not be loaded from
   the UI at all** (the demo picker is the only demo-loading entry point).
2. **Stale compiled `.js` shadowed the TypeScript sources.** 19 tsc-emitted files
   (18 in `frontend/src/**`, plus `frontend/vite.config.js`) sat next to their
   `.ts/.tsx` sources. Vite resolves `.js` before `.tsx`, and reads `vite.config.js`
   before `vite.config.ts`, so the dev server **and** the production build were running
   stale compiled output while `tsc` type-checked the newer sources. Verified from the
   browser's resource log: `main.tsx` loaded, but every extensionless import resolved to
   `.js` (`AppState.js`, `OverviewView.js`, …).

### Two React console errors found in the browser (both fixed)

* `RoleEditor` datalist: `example_values` are the first observed cells and can repeat
  (`split` → `train, test, test`), so `key={value}` produced duplicate keys (`test`).
* `OverviewView` expected-findings table: the `target_copy` manifest intentionally lists
  two `SS-TGT-001` expectations (high for `risk_score`, medium for `risk_band`), so
  `key={expected.rule_id}` duplicated.

### One test-isolation leak fixed (exposed by the new regression test)

`row_limited_client` in `backend/tests/test_api.py` rebuilt the settings cache in its
`finally` block while `SPLITSCOPE_MAX_ROWS=10` was still exported (monkeypatch teardown
runs after the fixture). Every later test in the session silently ran with a 10-row
limit. No existing test could see it; the new journey test did.

---

## 2. Live API journey — PASS (9/9, exit 0)

`python scripts/demo_journey.py` (rewritten; stdlib `urllib`, real HTTP, finite
timeouts, nonzero exit on any failure).

| # | Step | Status | Evidence |
|---|------|--------|----------|
| 1 | Health check | PASS | `GET /api/health` → 200, `SplitScope v1.0.0` |
| 2 | Demo catalogue + synthetic demo load | PASS | 6 demos; `POST /api/demos/repeated_entity/load` → 200, `ds-…`, 240 rows × 8 cols, `source=demo`, `is_synthetic=true` |
| 3 | Dataset preview + full row scan | PASS | preview 200; 240 rows scanned, ids unique |
| 4 | Audit run and finding evidence | PASS | `POST /api/audit` → 200; 1 finding, `SS-ENT-001` high (manifest fixture); 58 evidence `row_id` references, all resolve to real dataset rows |
| 5 | Split comparison (existing vs group) | PASS | `POST /api/splits/compare` → 200; existing 33 shared groups + `SS-ENT-001`, group 0 shared groups, no findings |
| 6 | Group-holdout CSV: rows, labels, **independent** overlap = 0 | PASS | 240 rows (180 train / 60 test) matching the comparison; row-id set identical to the dataset; labels ⊆ {train, test}; recomputed from CSV + dataset entity column: 30 train / 10 test entities, **0 shared** |
| 7 | Existing-split CSV: independent overlap > 0 | PASS | 179/61 rows; independently recomputed **33 shared** entities (matches the server's 33) |
| 8 | JSON report download + parsing | PASS | 37,319 bytes, `report_kind=audit`, `run_id` matches, 1 finding, roles + settings echoed |
| 9 | HTML report download | PASS | 24,949 bytes, `text/html`, attachment header, starts with `<!doctype html>`, renders `SS-ENT-001`, contains no `<script>` |

The group-holdout overlap check in step 6 is computed **independently of the server's
own metrics**: the script joins the downloaded assignment CSV's `row_id`/`split` columns
to the entity column fetched from `/api/datasets/{id}/preview`, then intersects the
non-missing entity sets. No audit rule is re-implemented in the script; fixtures come
from the demo manifest.

Exit codes verified: `0` full pass, `1` HTTP/validation failure (prints the complete
structured 422 body), `2` server unreachable (prints startup instructions).

## 3. Browser journey — PASS (real Chromium, `http://127.0.0.1:5177`)

Verified interactively in a real browser through the Vite dev proxy, with console and
network capture. (An earlier report claimed both "a successful browser walkthrough" and
"no available browser executable"; browser tooling is in fact available — Playwright and
its Chromium builds are installed under `frontend/node_modules` and
`%LOCALAPPDATA%/ms-playwright`.)

| Step | Status | Evidence |
|------|--------|----------|
| Load synthetic demo | PASS | `POST /api/demos/repeated_entity/load` → 200; dataset panel shows 240 × 8, SHA-256, limits |
| Configure column roles | PASS | feature toggled 4 → 3 → 4; "Roles are internally consistent" updates live; split/target/entity/train-test values populated from the manifest |
| Run the audit | PASS | `POST /api/audit` → 200; "1 finding(s) across 3 evaluated check(s): 1 high" |
| Open evidence | PASS | finding expanded: 33 shared entities, 61 test rows (100.0%), 137 train rows, 10 bounded examples; evidence view renders 110 `row-…` references in a table |
| Group-based comparison | PASS | `POST /api/splits/compare` → 200; existing 33 groups, random holdout 33 groups, **group holdout 0 groups** and no findings |
| Download reports | PASS | audit JSON, audit HTML and group CSV all → 200 through the proxy with `attachment` filenames; JSON parsed (1 finding; comparison: 3 rows) |
| Console errors | PASS | none from the application after the two duplicate-key fixes (only a 410 from a deliberate bad-`run_id` probe) |
| Failed network requests | PASS | every request observed returned 200 |

## 4. Regression checks — PASS

| Check | Status | Evidence |
|-------|--------|----------|
| Backend tests | PASS | `python -m pytest tests/ -q` → **178 passed**, 1 warning (Starlette TestClient deprecation), ~2.3 s |
| New: live-journey regression test | PASS | `backend/tests/test_demo_journey_http.py` starts the real app on a real socket (uvicorn) and runs `scripts/demo_journey.py` as a subprocess over HTTP; asserts 9 PASS steps and exit 0 |
| New: settings-leak regression test | PASS | `backend/tests/test_api.py::test_row_limit_settings_do_not_leak_into_later_tests` |
| Frontend typecheck | PASS | `tsc --noEmit -p tsconfig.app.json` → exit 0 |
| Frontend production build | PASS | `vite build` → 44 modules, `dist/assets/index-BDJ5DJHQ.js` (274.98 kB / 82.01 kB gzip) |
| Built bundle is what the backend serves | PASS | `python -m app.main` on :8000 serves `index-BDJ5DJHQ.js`, i.e. the bundle containing the fixes |

## 5. Not run / blocked

| Item | Status | Reason |
|------|--------|--------|
| Playwright E2E suite | NOT RUN | No `e2e/` directory and no `playwright.config.ts` exist yet. `@playwright/test` and browser binaries are installed; writing the suite is Stage 4 work. |
| Vitest unit tests | NOT RUN | No `tests/` directory and no test files exist (`vitest` and `jsdom` are installed). Stage 4 work. |
| ESLint | NOT RUN | No `eslint.config.js` exists, although `eslint` and plugins are installed and `package.json` declares a `lint` script. Stage 4 work. |
| Anything | BLOCKED | Nothing is blocked. |

## 6. Files changed in this pass

| File | Why |
|------|-----|
| `scripts/demo_journey.py` | Rewritten. Real HTTP via stdlib `urllib` (the old script transmitted no bodies), finite timeouts, structured error printing, distinct exit codes, independent group-holdout overlap invariant, real assertions instead of "PASSED (skipped)". |
| `backend/tests/test_demo_journey_http.py` | New. Regression test running the journey script against the app on a real socket. |
| `backend/tests/test_api.py` | Fixture teardown restores the environment before rebuilding the settings cache; new test asserting the limits do not leak into later tests. |
| `frontend/src/state/AppState.tsx` | Fetch health/checks/demos once on mount (previously nothing called `reloadCatalogue`). |
| `frontend/src/components/RoleEditor.tsx` | Deduplicate split-value suggestions before keying the datalist (duplicate-key console error). |
| `frontend/src/views/OverviewView.tsx` | Key expected-finding rows by rule + index (the `target_copy` manifest lists `SS-TGT-001` twice on purpose). |
| `frontend/.stale-artifacts/` | 19 stale tsc-emitted `.js` files (18 in `src/**` plus `vite.config.js`) **moved** here, not deleted. They shadowed the `.ts/.tsx` sources in Vite's resolution order, so the served and built app was stale compiled output. |
| `frontend/dist/` | Rebuilt so the single-command backend serves the fixed bundle. |
| `STATUS.md` | This report. |

No backend application code was changed: the API itself behaved correctly throughout.

## 7. Corrections to the earlier report

* "176 tests passing" → **178** (two focused regression tests added).
* "The integration script failed with a false negative / curl lacks the server's Python
  runtime context" → incorrect. The script sent empty request bodies; the server's
  validation was right. Fixed in the script; no validation was weakened.
* "Browser walkthrough verified, but no browser executable available" → contradictory
  and unsupported. Browser tooling exists; the earlier check only looked for navigation
  buttons, which proves nothing about integration. The journey above is now verified
  end to end, with console and network evidence.
* "No ESLint / vitest / Playwright installed" → they are installed; what is missing is
  the configuration and the test files (Stage 4).
* Earlier "known limitation: Python subprocess integration tests need Content-Type
  headers" → the Content-Type header was never the problem and is no longer relevant.

## 8. Startup commands

```bash
# Terminal 1 — backend (serves the built frontend too)
cd /e/Freebuff/backend
python -m app.main                       # http://127.0.0.1:8000

# Terminal 2 — frontend dev server with /api proxy (optional)
cd /e/Freebuff/frontend
/e/Freebuff/.tools/node-v22.14.0-win-x64/node.exe node_modules/vite/bin/vite.js --port 5177 --host 127.0.0.1
                                          # http://127.0.0.1:5177

# Verification
cd /e/Freebuff/backend && python -m pytest tests/ -q          # 178 passed
cd /e/Freebuff && python scripts/demo_journey.py              # exit 0, 9/9 steps
```

## 9. Next smallest task

Stage 4a is done (see the Stage 4a section). Remaining Stage 4 work, in order:

1. Meaningful frontend unit tests — vitest, jsdom and Testing Library are installed, but
   `npm run test` currently reports "no tests".
2. The synthetic evaluation script referenced by `backend/requirements.txt`
   (`scripts/evaluate_checks.py` does not exist yet).
3. ESLint flat configuration; when added it must ignore `frontend/.stale-artifacts/`,
   `frontend/dist/`, `frontend/test-results/` and `frontend/playwright-report/`.

## 10. Frontend usability redesign (first-time-user pass)

### Usability problems addressed

* **Overloaded landing screen.** The old Start view showed the full check catalogue,
  demo descriptions, upload constraints, limits and empty result panels at once. It now
  shows only: a compact header, a one-sentence purpose, two entry actions ("Try a demo"
  / "Upload CSV"), a short "What happens next" list, and collapsed disclosures for the
  demo picker, the check catalogue and the technical limits.
* **Unclear terminology.** Target, entity, split and group holdout are now defined in
  plain language where they first appear (Data view role legend, comparison notes).
* **Duplicated and low-priority statistics.** Summary stats in the audit view are
  grouped by question (what was found / how much data / what happened) instead of a
  grid of equal-weight numbers; long evidence lives in expandable sections.
* **Competing actions.** Each screen now has one visually primary action (Load data →
  Run audit → Compare / Export), with secondary navigation in the step nav only.
* **Stale runtime counters.** The Export page's store counters were rendered from the
  one-time startup health snapshot and showed zeros after data was loaded; it now
  re-fetches health on every mount (`refreshHealth` in `AppState`).

### Navigation / presentation changes

* Five-step primary nav (Start · Data · Results · Compare · Export) with disabled steps
  only where a prerequisite is genuinely missing, each with an explanation.
* Consistent neutral palette, single accent, one content width, shared spacing scale in
  `app.css`; status conveyed by colour **and** text label.
* Findings lead with a plain-language summary; rule ids (SS-…) are de-emphasised as
  secondary metadata; near-duplicates are framed as similarity candidates; the four
  check outcomes (ran-and-found-nothing / did not run / unsupported / failed) are
  rendered as distinct states.
* Comparison view explains that no split is nominated as "best" and that zero shared
  entities under a group holdout is not proof that all leakage is fixed.

### Files changed (this pass)

| File | Why |
|------|-----|
| `frontend/src/main.tsx` | Step-nav shell, per-view layout, skip link. |
| `frontend/src/views/OverviewView.tsx` | Minimal landing; entry actions; collapsed disclosures. |
| `frontend/src/views/DatasetView.tsx` | Compact dataset header, role-review step, one primary action. |
| `frontend/src/views/AuditView.tsx` | Question-grouped summary, prioritised findings, distinct check-outcome states. |
| `frontend/src/views/ComparisonView.tsx` | Side-by-side table, plain-language tradeoff notes. |
| `frontend/src/views/EvidenceView.tsx` | Readable evidence with column labels and controlled overflow. |
| `frontend/src/views/ExportView.tsx` | Named artifacts; mount-time health refresh. |
| `frontend/src/components/RoleEditor.tsx` | Plain-language role legend, pluralised wording. |
| `frontend/src/components/FindingCard.tsx` | Finding summary hierarchy, expandable detail. |
| `frontend/src/components/AuditConfigEditor.tsx` | Advanced settings behind disclosure. |
| `frontend/src/state/AppState.tsx` | `refreshHealth` action for the export page. |
| `frontend/src/lib/router.ts`, `src/lib/defaults.ts` | Step ids and default demo wiring. |
| `frontend/src/styles/app.css` | Palette, type scale, spacing, table/overflow handling, focus rings. |
| `frontend/index.html` | Title/meta for the simplified shell. |
| `frontend/tests/RoleEditor.test.tsx`, `tests/AuditView.test.tsx`, `tests/FindingCard.test.tsx` | Updated for intentional wording/navigation changes; behavioral assertions preserved. |
| `frontend/e2e/happy-path.spec.ts`, `e2e/error-recovery.spec.ts` | Updated selectors for the step nav; same flows asserted. |

No backend code, API schema, export content, storage behaviour or audit semantics were
changed.

### Checks executed (all passing)

* `npm run typecheck` — clean (`tsc -b` + `tsc -p tsconfig.app.json --noEmit`).
* `npm run lint` — clean, 0 warnings.
* `npm test` — **29/29** across 4 files (includes a focused regression test for the
  new `refreshHealth`: it re-fetches health so store counters update, and keeps the
  last snapshot without raising an error status when the refresh fails).
* `npm run build` — production bundle rebuilt (`dist/`).
* `npx playwright test` — **2/2** E2E (happy path incl. report downloads; rejected
  upload error recovery), against the production build served by FastAPI.
* Browser walkthrough (Chromium, 1280×800 and 390×844): landing → demo → roles →
  audit → finding evidence → group-holdout comparison (0 shared entities, tradeoff
  framing present) → export page; zero console errors; every application request 200;
  no page-level horizontal overflow at 390 px (wide tables scroll in-container).
* Export page store counters verified live after the health-refresh fix.

### Remaining limitations

* The in-memory store is per-process: refreshing the tab loses a run (documented in
  the UI; export before refreshing).
* Playwright suite is two specs (happy path + error recovery); broader coverage can be
  added incrementally.
* The browser preview webview occasionally served a cached `index.html` after a rebuild;
  a cache-busting reload was needed to pick up the fresh bundle (environment quirk,
  not an application issue).

## 11. Visual polish milestone — production-quality presentation (2026-10-19)

Goal of this pass: make the simplified frontend look professionally designed while
keeping its usefulness. One coherent direction was implemented — refined light
interface: soft neutral page background (`--bg-sunken`), crisp white surfaces, deep
navy text (`--ink`), one indigo accent, subtle borders/shadows, consistent radii,
spacing scale and typography, no new fonts/frameworks/runtime network dependencies.

### Main improvements

* **Design system completed.** 15 component classes used by the JSX had zero styling
  before this pass (`.callout`, `.stat`, `.deflist`, `.loading`/spinner, `.badge`
  variants, `.finding`, `.filters`/`.filter-chip`, `.panel`, `.evidence-details`,
  `.rowids`, `.hint`, `.empty`, `.kv`, `.disclosure`, `.table-wrap`). All now have
  consistent hover/focus/active/disabled/loading states; reduced-motion respected.
* **Landing composed.** Branded header with a SplitScope SVG mark (two panels split
  by a rule), concise hero, primary "Try a demo" + secondary "Upload CSV", synthetic
  data labelling, four-step "How it works" strip, "Browse other demos" chooser,
  collapsed check-catalogue and limits disclosures — all aligned to one content
  column (940px) so sections no longer float at different widths.
* **Three levels of explanation on every finding** (`FindingCard` + `lib/explain.ts`):
  an accessible three-option control — "Quick explanation" (default: the count
  sentence, why it matters, counts with their engine-supplied units) · "More context"
  (rule-specific mechanism copy, a real example from the finding's evidence, next
  step, limitations) · "Technical details" (rule id, verbatim description, evaluated
  columns, settings applied from the run's own config, counting-definitions table,
  recorded metrics, all examples, assumptions, limitations, and the checks that did
  not run with their reasons). Exactly one level renders at a time; the selection
  persists across findings and navigation. No invented scores or metrics; near
  duplicates stay "similarity candidates"; not-evaluated never reads as clean.
* **Results follow-up actions.** Audit summary now offers one primary next step
  (Compare other ways to split this data) plus lower-emphasis Review/adjust
  configuration, Export a report and Try another demo.
* **Evidence summary shown once**: the card header shows it collapsed; when expanded
  the Quick level opens with the same sentence (no visible duplication).

### Files changed (this pass)

| File | Why |
|------|-----|
| `frontend/src/lib/explain.ts` | New: level persistence + rule-specific copy + `settingsForRule` (reads the run's own `audit_config`). |
| `frontend/src/components/FindingCard.tsx` | Three-level explanation control; per-level content; `FindingTechnical` context prop. |
| `frontend/src/views/AuditView.tsx` | Passes columns/settings/metrics/not-run context; "Next steps" action row. |
| `frontend/src/styles/app.css` | Design-system tokens, 15 missing component styles, landing composition, segmented control, reduced-motion. |
| `frontend/src/main.tsx` | Branded header with SplitScope mark. |
| `frontend/src/views/OverviewView.tsx` | Landing composition (hero, steps, demo chooser). |
| `frontend/e2e/happy-path.spec.ts`, `e2e/error-recovery.spec.ts` | Selector updates for the intentional "Browse other demos"/"How it works" rename; behavioral assertions unchanged. |
| `frontend/tests/FindingCard.test.tsx` | Updated for the level control (same evidence assertions, reached via the level they now live on) + 2 new tests: level switching (one at a time, persists across collapse) and technical run context rendering. |
| `frontend/scripts/capture-screenshots.mjs` | New: scripted screenshot capture that also fails on any console/page/request error. |
| `frontend/dist/` | Rebuilt so the normal backend startup serves the new design. |

### Verification (final, after the last application change)

| Check | Result |
|-------|--------|
| `npm run test` | PASS — **31/31** across 4 files (FindingCard now 8, incl. the focused explanation-switching test). |
| `npm run lint` | PASS — 0 warnings. |
| `npm run typecheck` | PASS — `tsc -b` + `tsc -p tsconfig.app.json --noEmit`. |
| `npm run build` | PASS — `dist/` rebuilt (`index-BznhjxgM.js`, `index-DpXd9bdm.css`). |
| Playwright E2E (`SPLITSCOPE_E2E_PORT=8124 npx playwright test`) | PASS — **2/2** (happy path incl. evidence/comparison/downloads; rejected-upload recovery) against the production build served by FastAPI. |
| Browser inspection (Chromium) | PASS — landing, demo load, audit results at all three explanation levels, evidence, comparison (incl. explained-disabled "Chronological holdout"), export; desktop 1280px and mobile 390px; **zero console errors, zero page errors, every request 200** (verified twice: live panel and the capture script). |
| Screenshots | `frontend/screenshots/landing-desktop.png`, `landing-mobile.png`, `results-quick.png`, `results-context.png`, `results-technical.png`. |

### Not run / blocked

* Backend `pytest` was not re-run in this pass — no backend code changed in this
  milestone; the real API was exercised end-to-end by the E2E suite (audit,
  comparison, exports, 422 rejection path).

### Startup

```bash
cd E:\Freebuff\backend
E:\Freebuff\.venv\Scripts\python.exe -m app.main      # serves the rebuilt frontend at http://127.0.0.1:8000
```

## 12. Guided upload setup and beginner-first audit workflow (2026-10-19)

### The defect

The upload path ended in a false dead end. A CSV without a split column produced
`validation.ok = true`, because no column held two roles, and the UI presented
that as "ready". The audit still could not run: nothing had answered where the
train/test boundary came from, and the only split editor accepted free-text
labels. A file with its own split column could be typo-mapped, and a file without
one had no creation path at all. The real blocker was workflow state, not a role
conflict.

Two adjacent problems were confirmed:

* A stale successful validation could arrive after a role edit and make the
  current, incomplete roles look runnable.
* An intermittent `AppState` test failure (reproduced 2/20 runs under load) came
  from `findByTestId` resolving as soon as the status `<span>` existed, before
  the mocked request settled. The assertion was racing the state update.

### The fixes

* **One readiness derivation, two questions.** `frontend/src/lib/readiness.ts`
  now separates `columnState` ("do the assignments conflict?") from `ready`
  ("is the whole workflow runnable?"). The Data view uses `workflowBlockers`
  (column problems summarised once, next to the controls); Results uses the full
  `blockers`. Every reason names the action that removes it.
* **The entry question is explicit.** "Does your file already say which rows are
  training and testing?" offers "Yes — check my existing split." and "No — help
  me create a split." The run button stays disabled until the path, roles and
  confirmation are complete.
* **Existing splits are mapped from observed values.** The split column is
  selected from the file, and train/test labels come from that column's values
  with row counts. Missing cells and third labels are named and counted as
  excluded, never folded into a side. Unmapped, absent and equal labels have
  inline errors with fixes; the audit can still run when a third label is merely
  excluded.
* **Files without a split get a real one.** Random, stratified, group and
  chronological holdouts reuse the backend generator and auditor. Ineligible
  strategies are disabled with the missing role named. The strategy, seed and
  every assignment are stored with the run and exported as a CSV; `existing` is
  never offered as a generatable strategy, and the uploaded CSV is not edited.
* **Guided roles keep the advanced control.** Target, optional entity, optional
  timestamp and feature selection edit the same state as the manual editor.
  Each question explains the check it enables and retains a visible "not
  applicable / I don't know". Name/type suggestions require confirmation.
  `WineQT.csv` suggests `quality` as target, keeps `Id` as excluded metadata,
  leaves entity/time unset and offers the 11 chemistry columns as features.
* **Stale answers are rejected.** `AppState` bumps a validation sequence on
  every role edit and compares a serialized `rolesKey` before applying a
  response. Column-value responses and audits are likewise tied to the current
  dataset/column generation.
* **No duplicate error presentation.** Split validation issues moved next to the
  mapping controls; backend issues that the inline observation already
  reproduces are suppressed there, while any issue the client cannot reproduce
  remains visible.
* **Tests fixed at the cause.** `AppState.test.tsx` now waits for the catalogue
  content (and the failed-request status), not merely for an element that exists
  from the first render. No retries were added.

### Real-file acceptance (`D:\Downloads\Datasets\WineQT.csv`)

The file is 78,057 bytes, 1,143 rows × 13 columns: 11 chemistry features, the
`quality` target and an `Id` row identifier; no split, entity or timestamp
column. The scripted real-browser journey passed **20/20** checks:

* upload and first render (1,143 × 13);
* target `quality` suggested, no entity/timestamp invented, `Id` excluded;
* 11 features selected, group/chronology strategies unavailable and explained;
* random holdout audited with the seed recorded;
* all three explanation levels rendered; evidence cited 50 real rows;
* comparison excluded the non-existent "existing split";
* generated assignment CSV covered every row (1,145 lines including header/note);
* stratified-by-quality split audited;
* no page errors and no failed requests.

### Verification (final)

| Check | Result |
|-------|--------|
| Backend `pytest -q` | **218 passed**, 1 deprecation warning |
| Synthetic evaluation | **41/41 cases, 61/61 checks**, exit 0 |
| Frontend `npm test` | **70 passed** across 6 files (readiness 22, RoleEditor 17, roles 11, AppState 9, FindingCard 8, AuditView 3) |
| AppState flake stress | **0 failures / 100 concurrent runs** after waiting for settled state (before the fix: 2/20, then 8/100 under stress) |
| `npm run lint` | exit 0, 0 warnings |
| `npm run typecheck` | exit 0 |
| `npm run build` | exit 0 — `dist/assets/index-C9igwLQS.css`, `index-B9QwvZMR.js` |
| Playwright E2E (port 8128) | **4/4 passed** — error recovery, demo journey, existing-split upload, generated-split upload |
| Real-browser layout/keyboard (1440 and 390) | **15/15 checks** — no page-level overflow, 11/11 visible focus stops, no console or network errors |
| Large-upload measurement | 10.49 MiB CSV accepted in 2.75 s; 63.90 MiB parsed footprint; generated-split audit 2.64 s |

The large-upload measurement used a synthetic 10,000 × 100 numeric-text CSV on
Windows 11 against one local process. It is a single-request admission check, not
a throughput or real-corpus benchmark.

### Limits in force

| Bound | Default |
|-------|---------|
| Raw upload | **25 MiB** (server-enforced while reading) |
| Parsed frame | **256 MiB** estimated by pandas `memory_usage(deep=True)` |
| Shape | **10,000 rows**, **100 columns** (minimum 20 × 2) |
| Store | **384 MiB** parsed footprint, 8 datasets, 16 runs, 1-hour TTL |
| Near duplicates | 500 combined rows, at most 200 reported pairs |

All are configurable through `SPLITSCOPE_*` environment variables. Raising the
byte cap does not raise the row, column, parsed-memory or store limits.
Rejections are explicit; no upload is truncated.

### Visual verification and before/after

Captured at the same viewports with `.freebuff/shots.cjs` (1440 × 900 desktop,
390 × 844 mobile). The matched sets are local and ignored by Git.

| View | Before | After |
|------|--------|-------|
| Landing, desktop | `.freebuff/screenshots/before/desktop-1-landing.png` | `.freebuff/screenshots/after/desktop-1-landing.png` |
| Setup, desktop | `.freebuff/screenshots/before/desktop-2-setup.png` | `.freebuff/screenshots/after/desktop-2-setup.png` |
| Audit, desktop | `.freebuff/screenshots/before/desktop-3-audit.png` | `.freebuff/screenshots/after/desktop-3-audit.png` |
| Comparison, desktop | `.freebuff/screenshots/before/desktop-4-comparison.png` | `.freebuff/screenshots/after/desktop-4-comparison.png` |
| Export, desktop | `.freebuff/screenshots/before/desktop-5-export.png` | `.freebuff/screenshots/after/desktop-5-export.png` |
| Landing, mobile | `.freebuff/screenshots/before/mobile-1-landing.png` | `.freebuff/screenshots/after/mobile-1-landing.png` |
| Setup, mobile | `.freebuff/screenshots/before/mobile-2-setup.png` | `.freebuff/screenshots/after/mobile-2-setup.png` |

Real-file screenshots are in `.freebuff/screenshots/wineqt/`. The refinements
visible in the after set are the compact dataset header, four-step progress
strip, explicit readiness panel with status dot, observed-value mapping, feature
grid and consistent surfaces/type scale. No metrics, accounts, billing or
history were fabricated.

### Beginner-facing vs expert-facing

* **Beginner:** one entry question, plain-language explanations and examples,
  visible "not applicable / I don't know", strategy eligibility, observed-value
  label choices, inline fixes, one gated run action and three explanation levels
  on every finding.
* **Expert:** the same role state remains editable manually, including feature
  order and metadata overrides; every threshold stays under "Audit settings
  (advanced)"; the report records the strategy, seed, settings, evaluated/skipped
  checks and limitations; the generated assignment CSV is downloadable.

### Not run / remaining limitations

* No commit, push, publish or deploy was performed; the Git index was not
  touched. The new backend upload test and frontend upload E2E file remain
  untracked, as does the screenshot capture script.
* GitHub-hosted CI was not run (no remote authorized). Chromium only; Firefox and
  WebKit were not exercised.
* Real-world corpora, concurrency and sustained throughput were not evaluated.
  The 25 MiB cap is safe only together with the parsed-memory, shape and store
  limits, which reject rather than truncate.
* The in-memory store is per-process and single-user; restarting clears uploads,
  runs and assignments. Export before restarting.
* Auto-suggestions use column names/types and must be confirmed; they do not
  understand domain semantics. Near-duplicate findings remain candidates.

### Startup (existing repository-root virtual environment)

```powershell
# from E:\Freebuff
cd E:\Freebuff\frontend
npm run build

cd E:\Freebuff\backend
E:\Freebuff\.venv\Scripts\python.exe -m app.main
# open http://127.0.0.1:8000
```

For Playwright, put the root venv on `PATH` so its `webServer` command
(`python -m app.main`) resolves:

```powershell
$env:PATH = 'E:\Freebuff\.venv\Scripts;E:\Freebuff\node-v20.18.1-win-x64;' + $env:PATH
cd E:\Freebuff\frontend
$env:SPLITSCOPE_E2E_PORT = '8128'
npm run test:e2e
```
