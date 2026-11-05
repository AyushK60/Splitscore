# S7 Report Studio

The Report / Export Studio turns the runs in the current server session into one
evidence dossier. It is reachable at `#/export` and is the first content in the
existing export view; the pre-S7 per-run archive remains below it.

## Sources, not fabricated state

The studio never invents an analysis. It reads:

| Source | Where it comes from |
|---|---|
| Dataset identity | Current `AppState.dataset`: name, dimensions, SHA-256, synthetic marker |
| Leakage audit | Stored audit run in `AppState.audit`, with its run ID |
| Split comparison | Stored comparison run in `AppState.comparison`, with its run ID |
| Study card and profile | Server study/profile state for the dataset |
| Model runs | `GET /api/datasets/{dataset_id}/models/runs`, listed for the dataset |
| Health / limits | Existing health endpoint, shown in the runtime disclosure |

A model run is selected by run ID. All stored runs are selected initially; the
user can uncheck individual runs or use **Include all**. The server verifies that
every named run belongs to the dataset and has the expected kind.

## Composition rail

The rail is ordered **Preview & export → Sources → Sections**:

* **Preview & export** — Update preview (disabled while generating), Download
  dossier JSON, Download self-contained HTML, Print / Save as PDF, the explicit
  browser-print note and the generation timestamp.
* **Sources** — dataset, audit run, comparison run and model-run count/selection.
  Missing sources say “not run in this session”; model-listing failures are shown
  instead of being treated as zero runs.
* **Sections** — ten toggles in the server catalogue order:
  Executive summary, Dataset and provenance, Study card, Leakage audit, Risk
  scorecard, Findings and evidence, Split comparison, Model Lab, Limitations,
  Reproducibility and export metadata.

Unavailable sections stay checked by default so the artifact records the gap.
They can be unchecked to omit them. The rail states that a missing analysis is
never converted into a clean result.

At ≤1180 px the rail becomes a three-column band above the paper; at ≤860 px it
stacks. The actions stay first so they remain reachable without a nested scroll
area.

## Generation and staleness

* The first preview is generated automatically once the dataset and model-run
  list are known.
* A change to the named audit/comparison run or to the stored model-run list
  triggers a fresh preview.
* Section and model toggles mark the preview stale and show an explicit “Update
  preview” action; the screen never silently differs from the export request.
* A failed generation replaces the paper with a typed error callout and leaves
  the previous source list visible for diagnosis.
* No dataset produces a dataset-empty state, not a fake report.

The request body is:

```json
{
  "sections": ["summary", "provenance", "study", "audit", "scorecard",
               "findings", "comparison", "models", "limitations",
               "reproducibility"],
  "audit_run_id": "run-…",
  "comparison_run_id": "run-…",
  "model_run_ids": ["run-…"]
}
```

`null` is used when a run is absent. The server, not the browser, decides the
section order and the unavailable reason.

## What the paper renders

The preview is a renderer for the exact server object, not a second composition
layer. It includes, when available:

* cover with dataset name, dimensions, fingerprint, generation time and
  synthetic/uploaded marker;
* an executive summary with real finding, evaluated-check, not-evaluated and
  model counts; split identity; audit headline; included analyses; key findings
  and reviewer cautions;
* dataset provenance and profile;
* declared study context and study issues;
* audit rule outcomes and the complete not-evaluated list;
* category-based risk scorecard with no combined safety score;
* findings with stored counts, denominators, bounded evidence examples,
  recommended action, limitations and assumptions;
* split-comparison consequences and its limitations, with no winner;
* statistical-model coefficients/intervals and predictive-model held-out
  metrics/subgroups/diagnostics for the selected runs;
* limitations and reproducibility: run IDs, dataset fingerprint, versions,
  deterministic note and integrity statement.

Unavailable requested sections retain their title and a reason such as “Run the
leakage audit to add this section.” The summary cautions also record absent
audit/comparison/model evidence.

## Preview navigation

Dossier contents links use a real click handler rather than changing the URL
hash: SplitScope is a hash-routed app, so `href="#report-findings"` would have
been read as a route change. The handler scrolls the named section into view;
sections carry a 76 px scroll margin for the sticky masthead. In the standalone
HTML artifact the normal anchors work.

## Pre-S7 archive retained

Below the dossier, **Single-run reports and assignments** keeps the original
audit JSON/HTML downloads and split-assignment CSV downloads, with the exact
labels used by earlier journeys. Split assignments are a real table with
train/test counts and a download button per strategy.

## Implementation map

| Path | Responsibility |
|---|---|
| `backend/app/reports/dossier.py` | Section catalogue, source validation, composition and summary |
| `backend/app/reports/dossier_html.py` | Self-contained printable HTML |
| `backend/app/api/routes_reports.py` | `POST /api/datasets/{id}/reports/dossier` |
| `backend/app/api/schemas.py` | `DossierRequest` |
| `frontend/src/components/report/ReportPreview.tsx` | In-app renderer |
| `frontend/src/views/ExportView.tsx` | Studio, source/section controls, downloads, retained archive |
| `frontend/src/api/client.ts`, `types.ts` | Dossier request/response contract |
| `frontend/src/styles/s7.css` | Studio, paper, responsive and print styling |
