# S9B — Verification

All checks below were run on Windows in `E:\Splitscore V2` at commit time
(2026-11-06), against the local backend and the production frontend build.
Nothing is inferred from a previous stage's run.

## Commands and results

| Gate | Command | Result |
|---|---|---|
| Backend suite | `.venv\Scripts\python -m pytest` from `backend/` | **536 passed**, 3 warnings, 572 s |
| Synthetic audit oracle | `.venv\Scripts\python scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks, exit 0** |
| Frontend typecheck | `npm run typecheck` (`tsc -b` + app config) | **clean** |
| ESLint | `npm run lint` (`--max-warnings 0`) | **clean** |
| Frontend unit/component | `npm test` | **22 files, 205 tests passed** (60 new) |
| Production build | `npm run build` | **passes**; `EstimationView` is a lazy chunk, main bundle warning is pre-existing |
| Browser journeys | `npx playwright test` with the project venv first on `PATH` | **33 passed** (29 existing + 4 new) |

The Playwright `webServer` command is `python -m app.main` with `cwd ../backend`.
That `python` must be the project interpreter, which is why the run prefixes the
venv's `Scripts` directory to `PATH`; the system Python does not have
`statsmodels`. This is an environment prerequisite, not an application change.

## What the backend tests cover for S9B

- `tests/test_s9b_diagnostics.py` — histogram bin count/edges, per-arm counts,
  within-arm shares summing to one, empty-arm handling, extreme-bin placement,
  no mutation of inputs, and the presence of `propensity_histogram` in the
  overlap payload.
- `tests/test_demos.py` — the `causal_effect` demo loads with a binary treatment,
  complete outcome, documented true ATE 1.5 and a confounded naive contrast
  greater than 2, and the manifest and generation method carry the honest
  caveats.
- `tests/test_api.py` — the demo id is part of the public demo listing.

No existing assertion was relaxed.

## Frontend tests added (60)

| File | Tests | Focus |
|---|---|---|
| `tests/estimationFixtures.ts` | — | Realistic S9A payload builder and config factory |
| `tests/estimationModel.test.ts` | 14 | Request construction, sorting, signatures, every staleness reason, seed semantics, diagnostic selection, layout-only changes |
| `tests/EffectSummary.test.tsx` | 8 | Dots/intervals, failed estimator never zero, unavailable interval, units, comparison reading |
| `tests/BalanceView.test.tsx` | 7 | Love plot marks, undefined SMD, weighting inapplicability, sorting, imputation disclosure |
| `tests/OverlapView.test.tsx` | 6 | Histogram shares/edges, overlap window, no row-level score exposure |
| `tests/WeightsView.test.tsx` | 5 | Raw vs ESS, retained fractions, truncation, instability warning |
| `tests/MethodologyView.test.tsx` | 7 | Interpretation template, graph verdict caveat, provenance, defaults, limitations |
| `tests/EstimationView.test.tsx` | 8 | Readiness gate, explicit run only, partial failure, stale banner, stored run, expiry, out-of-order protection |
| `tests/estimationExport.test.ts` | 5 | SVG styling/caption, CSV values match the plot, JSON provenance, filenames |

`npm test` reports 22 files / 205 tests, so the pre-existing 145 tests still
pass unchanged.

## Browser journeys (new)

`frontend/e2e/s9b-estimation.spec.ts`, real backend on port 8123, real demo
dataset, no mocked estimation responses.

- **A — full estimation, diagnostics and export.** Loads the `causal_effect`
  demo, creates the saved demonstration DAG, waits for readiness, runs the
  three-estimator comparison, checks the result rows, inspects all five views,
  asserts the methodology provenance, downloads an SVG figure and the run JSON,
  and verifies the file envelopes.
- **B — unavailable intervals and refused configurations.** Switches to
  influence-function intervals, runs one estimator, confirms regression
  adjustment shows "interval unavailable" with no interval mark, then clears the
  adjustment set and confirms the readiness probe refuses the configuration, the
  run button is disabled and the block reason names the backdoor violation. The
  intentional `422` is registered with the shared `allowFailure` fixture so it is
  visible in the report rather than silently filtered.
- **C — staleness, navigation and stored results.** Runs a comparison, changes
  the interval level, confirms the named stale reason and that the numbers are
  labelled not current, leaves and re-enters the studio (result not restored as
  current), then loads the stored run from history and returns to current
  results.
- **D — responsive QA at four widths.** At 1440×900, 1024×768, 768×900 and
  390×844: asserts no page-level horizontal overflow, all five view tabs remain
  reachable (scrollable strip on phone), and captures `desktop-1440.png`,
  `laptop-1024.png`, `tablet-768.png`, `mobile-390.png`.

The full suite also re-runs the 29 earlier journeys, so the S9B route, shell
navigation and lazy chunk did not regress the audit/study/model/causal flows.

## Visual inspection

Screenshots in `docs/screenshots/s9b/` were opened and inspected after the real
run, not merely generated:

`setup.png`, `effect-summary-figure.png`, `effect-summary.png`, `balance.png`,
`overlap.png`, `weights-figure.png`, `weights.png`, `methodology.png`,
`refused-configuration.png`, `stale-result.png`, `desktop-1440.png`,
`laptop-1024.png`, `tablet-768.png`, `mobile-390.png`.

Defects found and fixed during inspection:

1. The fifth tab ("Methodology") wrapped alone onto a second row → replaced the
   wrapping strip with a five-column grid and a scrollable strip at ≤820 px.
2. The comparison table showed an internal horizontal scrollbar at laptop widths
   because headers never wrapped → `esttable--wrap` lets headers and warnings
   wrap; the table now fits its column.
3. "ESTIMATED" broke into `ESTIMA/TED` in the narrow status column after that
   change → status chips keep `white-space: nowrap`.
4. A demo-graph creation button nested inside a `<label>` gave the whole label a
   composite accessible name → wrapper is a `<div>`.
5. "Inverse propensity weighting" was clipped at tablet widths because the
   chart's label column was 160 px → 206 px below 760 px.
6. At 1024/768 the primary nav clipped the last stages, and at 390 the active
   stage was off-screen. Step badges are now hidden ≤1040 px (they are
   `aria-hidden` decoration), the header fits all nine stages from 1024 up, and
   the nav centres the active stage on resize below that.
7. Dense figures keep their true scale on a phone and scroll inside the figure
   card; at ≤620 px the scrollbar is made visible and touch scrolling is enabled,
   so the plot is not mistaken for a cropped image.
8. The "refused configuration" and "stale result" screenshots initially began
   under the sticky header; the journeys now position those banners before
   capture.

The screenshots confirm: five tabs on one row at 1440 (copper underline on the
active tab), no table scrollbar, readable estimator names at 768, the full nine-
stage header at 1024/768, the active stage visible at 390, and no page overflow.

## Data-integrity checks observed in the real run

- Bundled demo: 1,200 rows, 349 treated / 851 control, no exclusions.
- Known generating ATE **1.500**; confounded naive difference **3.1724**.
- Real engine output in the inspected run (100 bootstrap replicates, server-
  drawn seed): regression adjustment **1.731**, IPW **1.680**, AIPW **1.670**.
  The estimates are close to but not equal to 1.5, as a finite sample should be;
  no number on screen is hardcoded except the separately labelled known truth.
- Influence-function run: regression adjustment reports **interval unavailable**
  and plots no interval; IPW/AIPW show their computed intervals.
- Empty adjustment set: readiness refused with `open_backdoor_path`, run button
  disabled, no estimator invoked (journey B).
- Stale result: changing the interval level produces "The interval level
  changed." and the explicit statement that the displayed numbers are not
  current (journey C).
- Exports: SVG figure filename matches `splitscope_s9b_effect_summary_*.svg`,
  run JSON matches `splitscope_estimation_run-*.json` with `export_kind`
  `splitscope_causal_estimation_run` and three results (journey A).

## Limitations of this verification

- Chromium only, matching the existing Playwright configuration; no Firefox or
  WebKit run.
- The responsive check asserts document overflow and reachability, not pixel
  comparison against a design file.
- No real-world causal dataset was used; the demo's truth is known by
  construction and is not evidence about any real treatment.
- The estimation run history is exercised within one backend session; the
  one-hour expiry path is unit-tested rather than waited out in the browser.
- CI was not run (no remote authorized); all results are local.
