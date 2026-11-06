# S10-B — Integrated Academic Research Dossier & Methodology Generator

**Status: COMPLETE.** Commit `87d4832`.

## Sections (schema 1.1.0, additive)

The ten S7 sections are unchanged. Seven new server-authored sections are
composed from **stored estimation runs** the user selects in the Report
Studio:

| Section | Source run | Content |
| --- | --- | --- |
| `causal_graph` | graph record of any selected estimation run | nodes, edges with rationales, assumption registry, fingerprint — every edge labelled an assumption |
| `identification` | each selected run's recorded gate verdict | treatment/outcome/adjustment nodes, the backdoor verification verdict, the gate caveat |
| `causal_estimation` | `estimation` / `estimation_comparison` runs | cohort accounting, per-estimator estimates, intervals, balance/overlap digests, failures kept as failures |
| `subgroups` | one `subgroups` run | groups with counts/estimates/intervals/unavailable states, contrasts, all disclosed notes verbatim |
| `robustness` | one `robustness` run | experiment, parameters, distribution summary, recorded failures, caveats — the full repetition series stays in the stored run (`full_series_included: false`) |
| `what_if` | one `what_if` run | profile scenario with disclosures, cohort-standardised contrast, the no-interval and no-counterfactual warnings verbatim |
| `methodology` | everything included | the generated methods section |

## Integrity rules (all pinned by tests)

- Values are **copied** from the run payload, never recomputed — the
  dossier estimate equals the stored estimate exactly.
- A run whose `analysis_kind` does not match the section is **refused**
  (`require_estimation_run`), never re-labelled.
- A run whose recorded dataset fingerprint no longer matches the live
  dataset is **refused at the route** (HTTP 422) with a re-run instruction —
  a stale result is never presented as current.
- A run from another dataset is refused (HTTP 404, existing ownership rule).
- Sensitivity caveat, what-if counterfactual boundary and
  multiple-comparisons note survive verbatim into JSON, preview and HTML.
- HTML output escapes user-authored text (an edge rationale containing
  `<assumption>` renders escaped; asserted by test).
- JSON exports are `allow_nan=False` and stable apart from the generation
  timestamp.

## Methodology generator

`app/reports/methodology.py` composes structured academic prose — data
source and sample, variables, split/leakage evaluation, comparison,
statistical/predictive analysis, causal graph assumptions, identification
strategy, estimation methods, diagnostics, sensitivity methods,
reproducibility, limitations — from structured metadata only. Two
presentation levels (`concise`, `technical`; technical adds cross-fitting
and uncertainty configuration). Missing inputs become explicit
**"Not provided by the study card."** / **"Not evaluated — no qualifying
analysis run was included in this dossier."** statements. The generator
never invents sample sizes, intervals, performance figures, objectives or
causal conclusions, and never combines evidence tiers into a confidence
score.

## Frontend integration

Report Studio (`ExportView`): estimation-run sources listed with analysis
kind labels (via the enriched `estimation-runs` listing), pre-selecting
causal estimation runs, one-click include-all, availability-aware section
toggles with guidance notes, and a methodology presentation selector.
`ReportPreview` renders all new sections from the server payload, including
unavailable reasons and failed estimators.
