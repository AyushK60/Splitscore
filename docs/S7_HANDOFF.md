# S7 handoff

**Status: PASS for the approved practical S7 exit gate.**
**Branch:** `v2-premium-visual-foundation`
**Starting HEAD:** `d65fc4f`
**Implementation commit:** `571a4a8` — Deliver the S7 evidence dossier and visual legibility pass
**Documentation commit:** the commit that adds this handoff.

S7 adds the Report / Export Studio, visible scatter and scatter-matrix marks, and
compact workspace chrome. S0–S6 behaviour and honesty contracts are preserved.
The formal causal DAG/identification stage in the blueprint is **not** S7 here
and was **not started**. No S8 work is included.

## What shipped

### 1. Server-authored evidence dossier

`POST /api/datasets/{dataset_id}/reports/dossier?format=json|html` composes the
runs named by the client. The server, not the browser, owns section order and
availability.

* Ten ordered sections: executive summary, dataset/provenance, study card,
  leakage audit, risk scorecard, findings, split comparison, models,
  limitations, reproducibility.
* Sources are validated: a run must belong to the dataset and have the expected
  kind; duplicates are de-duplicated. A missing source is `available: false`
  with a reason, never a clean empty result.
* JSON schema **`1.0.0`**, generated UTC timestamp, real summary counts, run IDs,
  fingerprint, app version and integrity policy.
* Statistical models carry coefficients/intervals; predictive models carry
  selected model, split, held-out metrics, diagnostics and subgroup caveats.
* The printable HTML is one self-contained file: no scripts, external assets or
  network calls, inline print CSS, escaped text and an explicit raw-cell
  allowlist only for renderer-generated badges.
* No raw dataset or row-level predictions are embedded. Only bounded evidence
  examples already stored by the audit are included. SHA-256 is an identity
  check, not anonymisation.
* No server PDF library. Print / Save as PDF uses the browser print dialog; the
  downloaded HTML is the portable artifact.

### 2. Report / Export Studio

The existing `#/export` view now opens with:

* **Preview & export first** — update, JSON, self-contained HTML and print, so
  actions are not buried under a nested rail scroll.
* **Sources** — current dataset, audit/comparison run IDs and all stored model
  runs, individually selectable.
* **Sections** — all ten toggles; unavailable sections remain requested by
  default so the artifact records the gap.
* A server-payload preview, not a parallel client composition. Stale toggles
  show an explicit update action. Failed generation shows a typed error.
* The pre-S7 single-run JSON/HTML and assignment CSV archive remains below it
  with its original labels and a real assignment table.

### 3. Scatter and matrix legibility

`frontend/src/explore/scatterMarks.ts` is the shared display-rule module:

* stroke tiers 3.1 / 2.55 / 2.15 px and opacity 0.86 / 0.78 / 0.70 according to
  the drawn sample;
* paper-coloured halo, bounded eight-token palette, copper selection while other
  marks recede;
* deterministic jitter ≤**4.2 px** only for numeric axes with 8–12 distinct
  drawn values; row-ID based, stable, disclosed and display-only;
* Pearson r from the drawn sample, used by the matrix with its valid-pair count
  and a descriptive/non-causal caveat.

The matrix is a 3 × 2 gallery, draws one path per group level, has a real legend,
keyboard-operable panels and a fixed 218 px SVG height.

### 4. Compact chrome

* Brand and primary navigation share one 58 px sticky row (52 px at ≤760 px);
  the stage list scrolls horizontally instead of wrapping on medium screens.
* Breadcrumb and next actions moved to a non-sticky `.app-context` band.
* One document scrollbar; no nested rail scroll.
* Explicit nav hover/focus/active contrast retained.
* Route resets use `behavior: 'instant'` so global smooth scrolling cannot
  animate through the previous page.

### 5. Verification assets and docs

* Backend independent dossier suite: 10 tests.
* Frontend scatter rules: 9 tests; report renderer: 5 tests.
* One full S7 browser journey with JSON/HTML inspection, section toggles,
  contents navigation, print media and 390/834/1366/1920 captures.
* Twelve curated screenshots in `docs/screenshots/s7/`.
* Six S7 documents: baseline, studio, visual polish, export contracts,
  verification and this handoff.

## Final verification

Run from the repository root.

```bash
cd backend
../.venv/Scripts/python.exe -m pytest -q
# 373 passed, 3 warnings

../.venv/Scripts/python.exe -m pytest -q tests/test_dossier.py
# 10 passed, 1 warning

../.venv/Scripts/python.exe ../scripts/evaluate_synthetic.py
# 41/41 cases, 61/61 checks, exit 0
```

```bash
cd frontend
npm test -- --run
# 104 passed (11 files)

npm run typecheck   # clean
npm run lint        # clean, --max-warnings 0
npm run build       # clean; only the >500 kB chunk advisory
```

```bash
export PATH="/e/Splitscore V2/.venv/Scripts:$PATH"
cd frontend
SPLITSCOPE_E2E_PORT=8197 npx playwright test
# 22 passed (43.7 s)
```

The venv on `PATH` is required because Playwright starts `python -m app.main`
and the predictive routes import statsmodels. Port 8123 is occupied by an
unrelated process; 8197 was used for the final run. The committed Playwright
default is unchanged.

### Ledger

| Suite | Baseline `d65fc4f` | Final `571a4a8` |
|---|---:|---:|
| Backend | 363 | **373** |
| Frontend unit | 90 | **104** |
| Browser E2E | 21 | **22** |
| Oracle | 41 cases / 61 checks | **41 / 61** |
| Executed tests | 474 | **499** |

Expected warnings only: two numpy divide warnings from the singular-design
refusal test and one pre-existing Starlette/httpx deprecation. The build's only
warning is the existing chunk-size advisory.

## Reproduce the S7 surfaces

```bash
# backend
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8195

# frontend, separate terminal
cd frontend
npm run dev
```

Open the frontend, load **Repeated-entity subscription panel**, then:

1. Run the audit and compare strategy page.
2. Fit an OLS model in Model Lab.
3. Explore → Scatter (`month_index × tenure_months`) → Scatter matrix.
4. Export → adjust sections/models → download JSON or self-contained HTML, or
   use Print / Save as PDF.

The S7 screenshots are regenerated by
`frontend/e2e/s7-report-studio.spec.ts`; no manual screenshot step is required.

## Defects fixed in S7

| Defect | Fix |
|---|---|
| Matrix drew one path despite a grouping caption | One path per group level + real legend |
| Five-across matrix orphaned a panel and shrank plots | 3 × 2 gallery; single column on phones |
| Matrix x label clipped by stretched CSS cells | Fixed 218 px SVG height |
| No relationship stated per matrix panel | Pearson r from drawn sample + valid-pair count + caveat |
| Discrete scatter overplotted into stacks | Deterministic, disclosed ≤4.2 px display jitter |
| Faded marks and ambiguous selection | Stroke/opacity tiers, halo, copper selected path |
| Contents links changed the hash route | `preventDefault()` + `scrollIntoView()` with 76 px offset |
| Route reset animated through the old page | Instant reset; smooth scrolling retained for reading links |
| Screenshots captured mid-scroll | Instant scroll + settle before capture |
| Export actions hidden in a nested rail scroll | Actions first; no nested rail scrollbar |
| Generated HTML leaked escaped badge source text | Badge raw-cell allowlist + regression assertion |
| S7 archive broke prior assignment-row semantics | Restored a real assignments table and labels |
| Assignment table caused 178 px phone overflow | `min-width: 0` on archive card/table |
| Landing claimed shipped features were absent | Updated copy and proof counts (373 / 104 / 22) |
| No independent dossier test for predictive models | Added HTTP test for metrics, split and subgroup caveats |

## Deferred / not claimed

* **S8 and formal causal identification were not started.** No DAG, treatment
  effect, CATE, causal estimator or causal claim exists.
* No binary PDF. Browser print only.
* No saved report history, template gallery, free-form narrative editor or
  collaborative publishing.
* Dossier scope is the ten server-defined sections; it is not an arbitrary
  document builder.
* Reports are session artifacts backed by the in-memory store and its one-hour
  TTL; there is no durable report database.
* Matrix correlation describes the drawn render sample and is not a hypothesis
  test. Jitter never changes values, brushes, counts or correlations.
* Chromium only. Firefox/WebKit, forced-colours mode, screen readers and full
  keyboard-only traversal beyond existing checks were not tested.
* Synthetic demos verify behaviour, not real-world detection accuracy.

## Working-tree state

Only pre-existing untracked material remains outside this handoff:

* `docs/screenshots/s3/_preview/`
* `docs/screenshots/s5/_preview/`
* `import requests.txt`
* `scripts/_patch_s3_hero.py`
* `stash@{0}` (S3 checkpoint)

No S8 files, branches or deployments were created.
