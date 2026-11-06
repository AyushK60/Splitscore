# S9B — Premium Causal Effect Estimation Studio

S9B turns the audited S9A estimator backend into a research workflow: **Dataset
→ Causal DAG → Identification → Effect Estimation → Diagnostics → Report**. It
adds no estimator, no identification criterion and no new statistical claim.
Every number on screen is computed by the S9A engine for the current dataset and
the selected saved graph.

Branch: `v2-premium-visual-foundation`. Starting checkpoint: `5b4584b` (S9A
scientific audit repair).

## What was built

| Area | Implementation |
|---|---|
| Route | New lazy-loaded `estimation` view (`#/estimation`) in the workbench, step 8 of the primary navigation, labelled **Effect estimation**. |
| Workspace | `frontend/src/estimation/EstimationView.tsx` — setup panel, readiness gate, explicit run, five analytical views, run history, run export. |
| Analytical views | `EffectSummary.tsx`, `BalanceView.tsx`, `OverlapView.tsx`, `WeightsView.tsx`, `MethodologyView.tsx` — one primary figure each. |
| Model/request layer | `estimationModel.ts` (strict request construction, signatures, staleness reasons, diagnostic selection), `format.ts`, `figureFrame.tsx`, `estimationExport.ts`, `downloadRun.ts`. |
| Styling | `frontend/src/styles/s9.css`, imported once from `main.tsx`. |
| Contracts | `Estimation*` types in `frontend/src/api/types.ts`; `estimationApi` in `frontend/src/api/client.ts`. |
| Backend extension | Fixed 20-bin per-arm propensity histogram in `backend/app/causal/estimation/diagnostics.py`, plus the `propensity_histogram` field in the overlap payload. |
| Demo | Bundled `causal_effect` synthetic study (1,200 rows, 7 columns, known ATE 1.5). |
| Tests | 60 new frontend unit/component tests, 4 new real-backend Playwright journeys, backend tests for the histogram and the demo. |
| Docs | This file, `S9B_VISUAL_DESIGN.md`, `S9B_API_INTEGRATION.md`, `S9B_VERIFICATION.md`, `S9B_HANDOFF.md`. |

## Workflow and prerequisites

1. The studio reads the dataset currently loaded in the session. With none, it
   states so and offers a route to load one; it never invents a study.
2. It lists the **saved** causal graphs for that dataset and loads the first one.
   Entering estimation never requires rebuilding the DAG. If no graph exists it
   says so and offers the Causal Lab; on the bundled `causal_effect` demo it also
   offers a button that creates a real demonstration graph through the S8A API
   (structure only, no result).
3. Treatment, outcome and adjustment variables default from the saved graph's
   analysis scope and the S8C identification search. The adjustment set can be
   changed, cleared or taken from another verified minimal set; the backend
   verdict is authoritative.
4. Readiness is checked by `POST …/estimation/validate`, debounced 420 ms and
   tied to a request signature that includes the dataset id, graph id, graph
   scientific fingerprint and every request field. Only a matching readiness
   answer enables the run. The probe stores nothing and estimates nothing.
5. **Run comparison** calls `POST …/estimation/compare`; **Run <estimator>**
   calls `POST …/estimation/run`. No keystroke in the setup panel triggers a run.

## Scientific integrity rules encoded in the UI

- A failed estimator is rendered as `failed` with its backend reason and is
  never plotted at zero. If every estimator fails, the figure is replaced by a
  failure panel that says a failed estimate is not a zero effect.
- A missing confidence interval is shown as `interval unavailable` with the
  backend's `unavailable_reason`; no bounds are fabricated.
- Regression adjustment never receives post-weighting balance values or weight
  diagnostics: its overlap payload is `null` and the views say why.
- Balance SMDs that the backend reports as undefined are shown as `undefined`,
  not as zero. Median/mode diagnostic imputation is disclosed where it was used.
- The Love plot's 0.1 line is labelled **heuristic guide**, with the standing
  caveat that improved measured balance does not establish the absence of
  unmeasured confounding.
- Overlap text calls fitted propensities estimates, not true probabilities, and
  says empirical overlap does not prove population positivity.
- The methodology sentence is a fixed template:
  "Under the assumptions encoded in the selected DAG, the supported
  identification criterion … and the fitted estimation models, the estimated
  average treatment effect … is …, expressed in …, on N analysed rows. This is a
  finite-sample estimate … — not a proof that the effect is causal …".
  No generated prose and no claim that estimator agreement validates causality.
- The demo's known generating effect (1.5) is presented separately from the
  estimated finite-sample result and is never sent to the backend.

## Result lifecycle

| State | Behaviour |
|---|---|
| Checking | Explicit "Checking estimation readiness…" state; the run button is disabled with a reason in its title. |
| Ready | Cohort preview (rows, treated/control, exclusions) and the backend note are shown; run enabled. |
| Blocked | Named reason and details: no saved graph, structurally invalid graph, missing scope, invalid mapping, seed/truncation problem, or the backend's own refusal (409/410/422). |
| Running | Local status with the requested label; the run button reads "Running…". Prior results stay visible. |
| Completed | Result meta line (run id, analysed rows, units, adjustment set), five views, Run JSON. |
| Partially completed | `partial` badge when any estimator failed; successful estimators still plotted. |
| Failed | Alert with backend message and structured details; `410` offers "Reload the dataset". |
| Stale | Alert listing each named reason ("The adjustment set differs…", "The number of bootstrap replicates changed.", "The reproducibility seed changed.", …) and a Rerun button. The old numbers remain but are explicitly labelled not current. |
| Stored | History loads a run through `estimation-runs/{run_id}` and marks it "loaded from history"; "Back to current results" returns. |

Staleness compares the run's reproducibility block (dataset fingerprint, graph
id and scientific fingerprint, treatment/outcome, adjustment set, mapping,
cohort, missing-data policy, cross-fitting, uncertainty method/level/reps,
specified seed, truncation) with the current configuration. **Layout-only graph
edits do not change the scientific fingerprint, so moving a node never marks a
result stale.** An empty seed is not compared (the server drew and recorded one);
a specified seed that differs from the resolved seed is stale.

Out-of-order protection uses monotonically increasing sequence counters for both
the readiness probe and result loading, so an older answer can never overwrite a
newer one. The readiness answer is additionally bound to the signature it was
requested for, which prevents a stale "ready" from authorising a different
request.

## Run history

The studio lists runs from `GET /api/datasets/{dataset_id}/estimation-runs` and
loads one with `GET …/estimation-runs/{run_id}`. It states the lifecycle
honestly: runs live in the backend's bounded in-memory session store, expire
after about an hour and are dropped oldest-first when the store is full. Nothing
is persisted to disk or to a cloud service, and the UI promises no archive.

## Exports

- **Figure SVG** — the live SVG, with computed presentation styles baked in and
  a caption block (title, settings/method line, provenance, scientific note).
- **Figure PNG** — the same SVG rasterised at 2×.
- **Figure CSV** — exactly the values plotted in that figure, header included.
- **Figure JSON** — figure id, run/estimator/cohort provenance, plotted values
  and the assumptions the figure relies on.
- **Run JSON** — the backend estimation payload verbatim inside an export
  envelope, including fingerprints, seeds, exclusions, warnings and software
  versions.

Exports are built from the payload or the live element, never from a second
hand-written dataset. The S7 report dossier schemas were not modified: a
causal-effect report section needs separate report-backend work, and is recorded
as a handoff rather than faked.

## Backend changes

1. `diagnostics.py`: `HISTOGRAM_BINS = 20`, `_arm_shares`, `propensity_histogram`,
   exported in `__all__` and attached to `overlap_payload` as
   `propensity_histogram`. Counts per arm in fixed 0.05-wide bins over [0, 1] and
   within-arm shares; no row-level data, no kernel density, no inference about
   unobserved regions. Bins are fixed by definition so two runs are comparable.
   Independently tested in `backend/tests/test_s9b_diagnostics.py` (bin edges and
   count, shares summing to 1 per non-empty arm, empty arm handled, support
   outside the 0.01–0.99 extremes, overlap payload wiring).
2. `synthetic/generators.py`: deterministic `build_causal_effect()` and the
   `causal_effect` demo entry; regenerated `datasets/causal_effect.csv` and
   manifest. The simulator documents a constant treatment effect of 1.5 with
   measured confounding that biases the naive difference (3.1724).

No estimator, identification or uncertainty code was changed.

## Known limitations

- The cohort selector supports an optional split-assignment id and partition,
  but there is no route to enumerate this session's assignments; leaving the
  field empty (all prepared rows) is the documented default.
- History is in-memory and bounded; it is not a project archive.
- Figures have no brush/zoom; the SVGs are static publication figures.
- The causal-effect report section is not part of the S7 dossier yet.
- The studio presents ATE only. No ATT, CATE, mediation, sensitivity analysis,
  matching or alternative identification strategies (S9C and later).
- Playwright is Chromium-only, as in the existing suite.
