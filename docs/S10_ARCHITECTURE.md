# S10 Architecture — Integrated Research Dossier, History, Reproducibility & Publication

**Status: COMPLETE.** S10 integrates the existing stages into a coherent
research platform without rebuilding any of them: S10-A (history and
provenance), S10-B (the integrated dossier and methodology generator) and
S10-C (publication figures and the verified end-to-end workflow).

## What was added — and to what it attaches

| Layer | New | Attaches to |
| --- | --- | --- |
| `app/research/history.py` | typed history projection + portable reproducibility manifests | the existing bounded in-memory `Store` (no second storage system) |
| `GET /datasets/{id}/history`, `GET /datasets/{id}/history/{run_id}/manifest` | history & manifest routes | existing research router |
| `app/reports/dossier_estimation.py` | six summarisers for stored estimation runs | the S7 `build_dossier` engine (schema **1.1.0**, additive) |
| `app/reports/methodology.py` | academic methodology generator (concise/technical) | dossier section `methodology` |
| `app/causal/figure.py` + `GET …/figure.svg` | deterministic publication SVG of the stored graph | the stored graph spec (layout is display-only) |
| dossier route | `estimation_run_ids`, `presentation`, staleness/cross-dataset refusal | existing `DossierRequest` contract |
| `HistoryView` + nav step 11 | one focused history screen with manifest export | existing `rs-*` stage styles |
| `ExportView` estimation-run sources + section toggles + presentation selector | S10-B sources | existing Report Studio |
| `ReportPreview` + `dossier_html` renderers | seven new sections, JSON/preview/HTML from one payload | existing renderer maps |
| `e2e/s10-dossier.spec.ts` | two real-backend journeys | existing Playwright harness |

## Invariants preserved

- **Server-authored reporting.** The dossier is still composed server-side;
  the browser only renders the returned payload. Preview, JSON download and
  printable HTML cannot diverge.
- **Bounded, local-first storage.** History is a projection; the store's
  limits (`max_runs=16`, TTL 1 h, LRU) are unchanged. Nothing is persisted
  outside the process; manifests are metadata-only downloads.
- **No invented statistics.** The dossier copies recorded values; the
  methodology generator writes "Not provided"/"Not evaluated" rather than
  guessing; sensitivity stays a labelled scenario, what-if stays
  interval-free, subgroups stay AIPW-average-based.
- **S8C identification safeguards.** Every estimation-run source passes
  through the same ownership and staleness checks the run recorded; a run
  computed against changed dataset bytes is refused outright at the dossier
  route rather than silently included.

## Schema versioning

`DOSSIER_SCHEMA_VERSION` 1.0.0 → **1.1.0**, additive only: the ten v1
sections keep their ids, order, shapes and semantics (pinned by
`test_schema_is_additive_and_v1_sections_keep_their_ids`). New consumers get
`causal_graph`, `identification`, `causal_estimation`, `subgroups`,
`robustness`, `what_if` and `methodology`.
