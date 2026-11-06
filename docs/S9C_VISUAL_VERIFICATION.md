# S9C — Visual verification

**Method:** real Chromium journeys against the real backend and production
build (`e2e/s9c-research.spec.ts`); the screenshots below were captured by the
passing journeys and then **opened and inspected**, not just generated.

## Screenshots (docs/screenshots/s9c/)

| File | What it shows |
|---|---|
| `subgroup-forest-1440.png` | Full-page subgroup view at 1440: study-context card (treatment/outcome/adjustment/cohort/graph), three-tab strip, configuration row, forest plot with the overall reference ("overall 1.608"), subgroup table with all three regions and status chips, between-group contrasts with their own intervals, and the four methodology notes. |
| `robustness-1440.png` | Subsampling experiment: original estimate banner, repetition histogram with the original reference, distribution summary table, per-repetition failure list. |
| `whatif-1440.png` | What-if scenario: two-arm prediction bars, scenario contrast, cohort-standardised contrast, profile/disclosure table distinguishing "set explicitly" from cohort defaults. |
| `research-1440.png`, `research-1024.png`, `research-768.png`, `research-390.png` | The research stage at the four required widths. |

## Findings from inspection

1. **Forest whiskers are subtle by inheritance** — the interval marks reuse the
   S9B `estrow__interval` style (55%-mix teal, 3.5 px), which reads correctly at
   row scale; a DOM probe confirmed the marks render at the right coordinates.
   Kept for visual continuity with the estimation studio.
2. The vertical zero/reference lines are 1-px strokes; their text labels (e.g.
   "overall 1.608") carry the information redundantly, so nothing depends on a
   hairline.
3. The three-tab strip collapses to a horizontal scroll strip below 820 px with
   the hints hidden — verified by the 768/390 screenshots; all three tabs
   remain reachable at every width (asserted in journey D).
4. The study-context metadata uses a definition-list grid that wraps naturally
   at 768/390 without overflow; journey D asserts no page-level horizontal
   overflow at 1440/1024/768/390.

## Honest-state checks performed in the journeys

- Treatment and outcome are never offered as subgroup variables (journey A).
- The overall reference, exploratory intent and the multiple-comparisons note
  render with the figure (journey A).
- A structural graph edit makes the stored run unusable in the research stage
  with a named stale refusal — the stage never silently rebuilds the study
  (journey C).
- Scenario defaults are labelled "cohort median (default)" in the profile
  table rather than presented as explicit settings (journey B).

## Limitations

- Chromium only, matching the existing Playwright configuration.
- Screenshots are point-in-time results of a finite-sample engine; the exact
  numbers differ between runs (the journeys assert structure and reference
  labels, not pinned estimates).
- The sensitivity heatmap was verified through unit tests and the payload
  contract; it is not part of the demo journeys because a 25-cell refit grid
  would triple the browser-suite runtime.
