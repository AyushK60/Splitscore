# S7 verification

**Date:** 2026-11-05 (final verification after the last code, test and copy change)
**Branch:** `v2-premium-visual-foundation`
**Starting HEAD:** `d65fc4f` — S6-D/E complete model diagnostics and subgroup uncertainty
**Implementation commit:** recorded in `docs/S7_HANDOFF.md`.
**Overall status: PASS for the approved practical S7 exit gate.**

S7 delivers the Report / Export Studio, the scatter and scatter-matrix visibility
repairs, and the compact workspace chrome. It does **not** implement the
blueprint's formal causal DAG/identification stage; causal work remains
unstarted. No PDF binary, causal effect, fabricated run or invented metric is
claimed.

## Automated verification (final code)

| Check | Command | Result |
|---|---|---|
| Backend tests | `../.venv/Scripts/python.exe -m pytest -q` in `backend` | **373 passed**, 3 warnings in 10.56 s |
| Dossier tests | `../.venv/Scripts/python.exe -m pytest -q tests/test_dossier.py` | **10 passed**, 1 warning in 2.20 s |
| Synthetic audit oracle | `../.venv/Scripts/python.exe ../scripts/evaluate_synthetic.py` in `backend` | **41/41 cases, 61/61 checks**, exit 0 |
| Frontend unit tests | `npm test -- --run` in `frontend` | **104 passed** (11 files) in 2.33 s |
| TypeScript | `npm run typecheck` | clean |
| ESLint | `npm run lint` (`--max-warnings 0`) | clean |
| Production build | `npm run build` | clean; non-failing chunk-size warning: JS 559.41 kB (gzip 154.52 kB), CSS 130.42 kB (gzip 24.98 kB) |
| Playwright E2E | `SPLITSCOPE_E2E_PORT=8197 npx playwright test` | **22 passed** in 43.7 s |

The three backend warnings are expected: two numpy divide warnings deliberately
triggered by the singular-design refusal test and one pre-existing
Starlette/httpx `TestClient` deprecation. The build's only warning is the
existing >500 kB chunk advisory; there is no build error.

The Playwright `webServer` starts `python -m app.main`, so the repository virtual
environment must be on `PATH`:

```bash
export PATH="/e/Splitscore V2/.venv/Scripts:$PATH"
cd frontend
SPLITSCOPE_E2E_PORT=8197 npx playwright test
```

Port 8123 is held by an unrelated process; the committed default is unchanged.
The final full run used 8197. Without the venv on `PATH`, the server fails with
`ModuleNotFoundError: No module named 'statsmodels'`.

## Count ledger

| Suite | Baseline at `d65fc4f` | Final | Delta |
|---|---:|---:|---:|
| Backend pytest | 363 | 373 | +10 dossier tests |
| Frontend Vitest | 90 (9 files) | 104 (11 files) | +9 scatter-rule, +5 report-preview tests |
| Playwright E2E | 21 | 22 | +1 S7 journey |
| Synthetic oracle | 41 cases / 61 checks | 41 cases / 61 checks | unchanged |
| **Total executed tests** | **474** | **499** | **+25** |

The oracle is a deterministic synthetic expectation suite, not a measure of
real-world leakage-detection accuracy.

## What the new tests independently check

### Backend — `backend/tests/test_dossier.py` (10)

| Test | Independent check |
|---|---|
| Complete dossier | Builds audit + comparison + OLS run, then asserts every one of the 10 sections is available and tied to the stored run IDs |
| Missing runs | Absent audit/comparison/model sources produce `available: false`, a named reason and `data: null`; they are not empty clean results |
| Not evaluated | Rule-unchecked checks survive into the audit, limitations and summary counts |
| Printable HTML | Self-contained document, no script/network asset, print CSS, hostile text escaped |
| JSON download | Same schema/body as preview with attachment and no-store headers |
| Section selection | Server catalogue order is preserved; empty selection is rejected |
| Run ownership | Wrong-kind runs and runs from a foreign dataset are refused |
| Predictive card | A real classification run's held-out metrics, selected model, split and subgroup rows survive into both JSON and HTML |
| Hostile study title | User-provided study text cannot inject markup into HTML |
| Builder determinism | Direct builder repeats identically apart from generation time |

The predictive test closes the one coverage gap found during final review: the
studio only exercised an OLS run in the browser, while the dossier supports both
statistical and predictive cards. It now verifies `prediction_model` metrics,
the existing split, subgroup caveats and the non-causal note independently over
HTTP.

### Frontend unit — 14 new tests

`frontend/tests/scatterMarks.test.ts` (9) covers discrete-axis detection,
continuous/tiny-sample rejection, row-and-axis determinism, the disclosed pixel
bound, finite-pair filtering, undefined correlation for small or constant
samples, signed formatting, stroke/opacity tiers and a bounded palette.

`frontend/tests/ReportPreview.test.tsx` (5) covers server counts/split
denominators, unavailable-section reasons, study-text escaping, a contents strip
built only from included sections, and the integrity/no-causation statements.

### Browser — `frontend/e2e/s7-report-studio.spec.ts` (1 journey)

The final journey performs a complete real workflow rather than mocking state:

1. Loads the repeated-entity demo and asserts the sticky primary row is
   ≤62 px, brand and navigation are vertically aligned, and the context band
   scrolls out of view.
2. Runs the leakage audit and the group-holdout comparison.
3. Fits a real OLS `tenure_months` model and captures its run ID.
4. Opens the scatter on `month_index × tenure_months`; asserts the discrete-axis
   disclosure says marks are offset ≤4 px and that mark opacity is ≥0.8.
5. Opens the 3 × 2 matrix; asserts six panels, grouped stroke colours, per-panel
   Pearson r and the descriptive/non-causal note.
6. Opens the studio; asserts the dataset cover, one real model card, comparison,
   audit finding, 10 contents entries and the exact model run ID.
7. Clicks the contents link and waits for `#report-findings` to settle 76 px
   below the top, proving the hash-router conflict is fixed.
8. Unchecks **Split comparison**, regenerates, observes 9 contents entries and
   the section removed; rechecks it and observes 10 again.
9. Downloads the JSON and independently inspects `report_kind`, schema
   `1.0.0`, dataset SHA-256, 10 included sections, real summary counts, absent
   raw data/row predictions and the selected model run.
10. Downloads the HTML, asserts document boundaries, no `<script>`, print CSS,
    dataset/model/finding text, then opens the downloaded file directly at 1440
    px and screenshots it.
11. Emulates print media and asserts topbar and composition rail are hidden while
    the paper remains.
12. Checks the studio and paper at 1366, 834 and 390 px, asserting horizontal
    overflow ≤1 px at tablet and phone widths, and confirms both pre-S7 archive
    download labels still exist.

## Acceptance gate

| S7 requirement | Status | Evidence |
|---|---|---|
| Compose only real current-session state | **PASS** | Server resolves dataset, audit, comparison, study/profile, scorecard, findings, selected model runs, limitations and reproducibility; foreign/wrong-kind IDs refused |
| Section include/exclude | **PASS** | Server-ordered toggles; browser journey proves 10 → 9 → 10 and the export request carries the selection |
| Honest missing sources | **PASS** | Missing audit/comparison/model sections stay listed with their reason; summary cautions record absent evidence |
| Structured JSON | **PASS** | Schema `1.0.0`; download independently parsed in the browser journey |
| Self-contained printable HTML | **PASS** | Inline CSS, no scripts/assets, escaped text, print rules; downloaded file opened directly |
| Print-friendly in-app paper | **PASS** | Print media hides chrome, rail and archive; paper remains |
| No fake PDF | **PASS** | Only the browser print dialog is offered; no PDF library or file is claimed |
| Scatter mark visibility | **PASS** | Larger strokes, tiered opacity, paper halo, copper selection and count/stride caption; max opacity asserted ≥0.8 |
| Honest deterministic jitter | **PASS** | Low-cardinality numeric axes only, ≤4.2 px, row-ID deterministic, disclosed; values/brushes/counts unchanged |
| Scatter matrix visibility | **PASS** | Real 3 × 2 gallery, one path per group, per-panel Pearson r, valid-pair count, keyboard panels |
| Compact, stable chrome | **PASS** | 58 px primary row (52 px mobile), non-sticky context band, one normal document scrollbar, readable hover/focus/active states |
| S0–S6 behavior preserved | **PASS** | Full 373 backend, 104 unit and 22 browser runs green; archive labels preserved |
| Six S7 documents | **PASS** | `S7_BASELINE`, `S7_REPORT_STUDIO`, `S7_VISUAL_POLISH`, `S7_EXPORT_CONTRACTS`, `S7_VERIFICATION`, `S7_HANDOFF` |

## Visual review

The final S7 browser run regenerates every capture in `docs/screenshots/s7/` at
the stated viewport, with animations disabled and instant scrolling:

| File | Viewport / state |
|---|---|
| `s7-chrome-1920.png` | 1920×1080, audit results, compact sticky row |
| `s7-scatter-1920.png` | 1920×1080, discrete month axis and disclosed offset |
| `s7-matrix-1920.png` | 1920×1080, six grouped panels with r |
| `s7-model-lab-1920.png` | 1920×1080, real OLS fit used by the dossier |
| `s7-report-1920.png` | 1920×1080, studio and paper |
| `s7-report-1366.png` | 1366×900, studio and paper |
| `s7-report-tablet-834.png` | 834×1112, stacked composition rail |
| `s7-report-paper-tablet-834.png` | 834×1112, paper itself |
| `s7-report-mobile-390.png` | 390×844, stacked rail |
| `s7-report-paper-mobile-390.png` | 390×844, paper itself |
| `s7-print-1440.png` | 1440×1000, print media |
| `s7-generated-dossier-1440.png` | 1440×1000, downloaded HTML opened from disk |

Reviewed for mark visibility, text clipping, accidental nested scroll, chrome
height, contents navigation, print-only content, table overflow and phone/tablet
stacking. The automated journey additionally asserts ≤1 px document overflow at
834 and 390 px.

## Defects found and fixed during S7

| Defect | Found by | Fix |
|---|---|---|
| Matrix caption claimed grouping but drew one teal path | Visual/code review | One path per group level from the shared palette; real legend |
| Five matrix panels across left an orphan and shrank panels | 1920 px screenshot | 3 × 2 centred gallery (`repeat(3, 238px)`); one column on phones |
| Matrix x-axis label clipped when a grid cell stretched | Screenshot | Fixed SVG height (`218`) |
| No per-panel relationship stated | Requirements review | Pearson r from the drawn sample plus valid-pair count and descriptive caveat |
| Discrete scatter collapsed into stacks | Screenshot | Deterministic ≤4.2 px row-ID offset only for low-cardinality numeric axes, disclosed |
| Marks faded and selection ambiguous | Screenshot | Tiered 3.1/2.55/2.15 px strokes, 0.86/0.78/0.70 opacity, paper halo, single copper selection |
| Contents links changed the hash route instead of scrolling | Browser journey | `preventDefault()` + `scrollIntoView()`; 76 px section scroll margin |
| Route reset animated through the previous page | Browser journey | `behavior: 'instant'` for route resets; global smooth scrolling kept for reading links |
| Screenshots captured mid-scroll | Screenshot review | Explicit instant scroll + settle wait before capture |
| Export actions hidden below a nested rail scroll | Screenshot / interaction review | Actions first in rail; nested scroll removed |
| Generated HTML showed escaped badge source text | HTML regression test | Raw-cell allowlist only for renderer-produced badges; test rejects escaped badge text |
| S7 archive replaced the old assignment rows with a list | Full E2E | Restored a real assignments table, preserving prior row semantics and labels |
| Assignment table caused 178 px phone overflow | Responsive screenshot/test | `min-width: 0` on archive card and assignment table |
| Landing copy said delivered features were “not in this build” | Final copy audit | Rewrote capability/check copy; proof counts updated to 373 / 104 / 22 |
| Dossier's predictive card had no independent test | Final coverage review | Added HTTP test for held-out metrics, split and subgroup caveats (backend 372 → 373) |

## Checks not performed / limitations

* Chromium only. Firefox, WebKit, forced-colours mode, screen readers and
  keyboard-only traversal beyond the matrix/contents checks were not exercised.
* No server-side PDF is produced. PDF depends on the browser's print dialog and
  was not compared pixel-for-pixel across browsers.
* The dossier deliberately embeds no raw dataset or row-level predictions. It
  carries only the bounded evidence examples already stored by the audit; the
  SHA-256 fingerprint is an identity check, not anonymisation.
* The studio composes the 10 server-defined sections. There is no free-form
  narrative editor, custom section authoring or report template gallery.
* Matrix r describes the drawn render sample and is not a finding, hypothesis
  test or causal claim. Jitter changes display coordinates only.
* Synthetic demo values verify contracts and rendering; they do not establish
  real-world performance.
* Uploads, browser sessions and stored runs remain in-memory with the existing
  1-hour TTL and limits; reports do not persist beyond the session.
* No S8 work was started. Formal causal DAG/identification, effect estimation,
  advanced diagnostics, export history, saved report templates and any hosted
  collaboration are deferred.
