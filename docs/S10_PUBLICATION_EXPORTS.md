# S10-C — Publication Studio, Figures & Complete Workflow

**Status: COMPLETE.**

## Figure inventory (all exports carry provenance)

Every analytical figure already exports **SVG, PNG (2× raster), CSV of the
plotted values and JSON metadata** through the shared `FigureFrame` engine,
with figure id, title, settings line, figure-level caveat, `run_id`,
timestamps and dataset/graph fingerprints in the provenance block:

| Figure | View | figure id |
| --- | --- | --- |
| Effect summary | Effect Estimation Studio | `s9b_effect_summary` |
| Love plot (covariate balance) | Balance | `s9b_covariate_balance` |
| Propensity overlap | Overlap | `s9b_propensity_overlap` |
| Weight reliability | Weights | `s9b_weight_reliability` |
| Subgroup forest plot | Causal Research | `s9c_subgroup_forest` |
| Robustness distribution/heatmap/scenario | Causal Research | `s9c_robustness_{experiment}` |
| What-if scenario | Causal Research | `s9c_what_if_scenario` |
| **Causal DAG publication figure (new in S10-C)** | Causal Lab | `GET /api/datasets/{id}/causal-graphs/{gid}/figure.svg` |

## The DAG figure (the gap S10-C closed)

The interactive canvas is React-Flow HTML — screenshotting it would violate
the rule against exporting screenshots of UI controls as publication
figures. Instead the backend renders a **deterministic, standalone SVG from
the stored spec** (`app/causal/figure.py`):

- recorded canvas positions place nodes when present and sane; otherwise a
  deterministic layered layout is derived from the topology (layout is
  display-only and excluded from the scientific fingerprint — pinned by a
  test that moves a node and asserts the fingerprint is unchanged);
- treatment (teal) and outcome (copper) roles are labelled; unobserved
  variables render dashed;
- the caption carries the spec fingerprint, counts, the standing assumption
  caveat, and the figure schema version;
- output is valid XML (parsed in tests), deterministic across requests, and
  escapes user-authored labels.

The Causal Lab toolbar gained an **Export figure** button (enabled once the
graph is saved); the download streams `image/svg+xml` with an
`X-SplitScope-Export-Note` header. Backend coverage: 5 tests in
`test_s10_figure.py`.

## The complete workflow (verified, not claimed)

`e2e/s10-dossier.spec.ts` drives two real-backend journeys:

- **Journey A** — load demo → generated-split audit → identification-gated
  effect comparison → subgroup/robustness/what-if in Causal Research →
  Report Studio composes the integrated dossier (all seven new sections
  visible, identification verdict "verified", methodology naming the
  estimation) → downloads the dossier JSON and asserts schema 1.1.0 and the
  stored estimate.
- **Journey B** — History stage shows the typed runs with parameters →
  downloads the reproducibility manifest (metadata-only, 64-hex integrity
  hash) → Causal Lab downloads the publication figure (SVG, assumption
  caveat present).

## Honest states

Unavailable dossier sections keep their server reasons; unavailable
subgroups render as *unavailable*, never zero; failed estimators render as
failed with their reason; the manifest is metadata-only by contract.
