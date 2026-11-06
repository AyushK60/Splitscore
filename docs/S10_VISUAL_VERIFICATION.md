# S10 Visual Verification

**Status: COMPLETE.** Screenshots are captured by the real-backend Playwright
runs into `docs/screenshots/s10/` and the existing per-stage folders.

## Captures inspected in this session

| Screenshot | What was verified |
| --- | --- |
| `docs/screenshots/s10/s10-dossier-1440.png` | the full 17-section integrated dossier: cover, TOC, summary → provenance → study → audit → scorecard → findings → comparison → models → **causal graph → identification → causal estimation → subgroups → robustness → what-if → methodology** → limitations → reproducibility; coherent hierarchy, readable tables, caveat text legible |
| `docs/screenshots/s10/s10-history-1440.png` | History stage: counts, filter tabs, storage-honesty note, expanded run card with parameters, live staleness banner with spelled-out reason |
| `docs/screenshots/s10/s10-research-1440.png` | Causal research stage after all three experiments |
| `docs/screenshots/s9c/*` (re-captured post-repair) | forest plot now paints uncertainty whiskers; robustness and what-if figures unchanged |
| `docs/screenshots/s7/*`, `s8*`, `s9b/*` (re-captured by the full Playwright run) | pre-existing stages unaffected by the S10 additions |

## Layout rules kept

- One primary visualization per analytical screen; the History stage is a
  list, not a dashboard.
- The dossier preview is a single paper sheet; new sections inherit the
  existing typographic scale; no new decoration.
- No redesign of the landing page or existing stages beyond the additive
  Report Studio sources block, History nav step, and the Causal Lab's
  Export-figure button.

## Responsive behaviour

The existing per-stage journeys capture 1440/1024/768/390 screenshots
(`research-*.png`, `s7-*` set) and their layout assertions still pass with
S10 changes in the build. The S10 additions (History cards, Report Studio
source block) reuse the responsive grids already present (`hist-params` uses
`auto-fill minmax(320px, 1fr)`; the config column is the existing
`report-config` layout).

## Known cosmetic states (accepted, documented)

- The what-if numeric placeholder reads `median` (S9C audit repair) — full
  wording stays in the field hint.
- The History stage shows the honest study-link note per run; it is
  deliberate, not an unfinished panel.
