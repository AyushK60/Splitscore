# S6 visual QA

All screenshots are real Chromium captures of the production build served by the
FastAPI backend. No mock data is used inside the application. Screenshots were
reviewed at 1920 × 1080, 1366 × 900 and 390 × 844; the new predictive diagnostics
were captured after the final styling changes.

## S6-A — repairs

| Screenshot | Shows |
|---|---|
| `docs/screenshots/s6/before/scatter.png` | Pre-fix Scatter with a 2092 px SVG and a growing document |
| `docs/screenshots/s6/after/scatter.png` | Post-fix Scatter: 414 px SVG inside a definite-height frame, stable document |
| `docs/screenshots/s6/after/topbar.png` | Default masthead and breadcrumb |
| `docs/screenshots/s6/after/topbar-hover.png` | Hovered nav item: ivory text on the ink band, no pale fill |
| `docs/screenshots/s6/after/workflow-data.png` | Data stage: breadcrumb and “Run the audit…” guidance |
| `docs/screenshots/s6/after/workflow-audit.png` | Audit results as stage 3, actively indicated |
| `docs/screenshots/s6/after/pc-help.png` | Parallel-coordinates reading guide, annotated example, selection count |
| `docs/screenshots/s6/mobile/scatter.png` | Scatter at 390 × 844; document overflow 0 px |
| `docs/screenshots/s6/tablet/scatter.png` | Scatter at 768 × 1024; document overflow 0 px |

Measured scroll heights for the Scatter regression:

```
before: 2174 2324 2474 2630 2774 2930   (SVG 2092 px)
after : 1396 1396 1396 1396 1396 1396   (SVG 414 px)
```

## S6-B — statistical Model Lab

| Screenshot | Shows |
|---|---|
| `docs/screenshots/s6/after/model-lab-ols.png` | OLS on `clean_control`: formula, coefficient table, fit statistics, intervals, residual plot, population/provenance sidebar |
| `docs/screenshots/s6/after/model-lab-logistic.png` | Logistic regression: odds ratios, probability sample, pseudo-R² and log-likelihood; no OLS R² |

Visual review notes:

* The three-region instrument (controls · results · context) uses the S5 ink,
  ivory, copper and celadon tokens; no new palette was introduced.
* Tables use tabular numerals and right-aligned numeric columns.
* Warnings are semantic callouts with text, never colour alone.
* The plot canvases have visible axis labels, a zero reference line and a
  caption stating the sampled population.
* The header tagline names the Model Lab.

## S6-D/E — predictive diagnostics

| Screenshot | Viewport | Shows |
|---|---|---|
| `docs/screenshots/s6/after/diagnostics-pr-1920.png` | 1920 × 1080 | PR curve with average precision, prevalence line, positive/negative counts and the step-wise AP definition |
| `docs/screenshots/s6/after/diagnostics-calibration-1366.png` | 1366 × 900 | Reliability plot, Brier/ECE/MCE summary, ten-bin table with Wilson intervals, and the one-bin caveat |
| `docs/screenshots/s6/after/diagnostics-subgroups-1366.png` | 1366 × 900 | Subgroup table at 1366 px: denominators, accuracy, Wilson intervals, support and wrapped small-group warning |
| `docs/screenshots/s6/after/diagnostics-influence-1920.png` | 1920 × 1080 | OLS leverage/Cook's plot, coefficient table with 95% intervals, and largest-influence rows on the refit partition |
| `docs/screenshots/s6/after/diagnostics-importance-1920.png` | 1920 × 1080 | Sealed-test permutation importance with RMSE increase, repeat SD and relative-magnitude bars |
| `docs/screenshots/s6/mobile/diagnostics-pr.png` | 390 × 844 | PR curve and caption at mobile width; no horizontal page overflow |

### What was reviewed and fixed

| Observation | Resolution |
|---|---|
| PR plot's AP label collided with the vertical “precision” axis label | Moved AP to the top-right; moved prevalence to a clear position above the baseline |
| Diagnostic SVGs scaled to nearly the full results column, producing very large type | Capped predictive plots at 520 px and centred them; mobile remains fluid |
| Subgroup warning column clipped at 1366 px | Fixed-layout subgroup table with wrapped cells and explicit column proportions |
| Permutation-importance caption called baseline RMSE a “baseline rmse_increase” | Caption now says “Baseline RMSE” and the column says “Mean RMSE increase” |
| One-bin dummy calibration could look like a full reliability curve | Added an explicit caption note that a single non-empty bin cannot describe calibration shape |
| Influence section was initially captured mid-scroll | Recaptured with instant scroll anchoring; no layout defect remained |

The signal-bearing regression screenshots use the bundled
`chronology_violation` demo (`sensor_a`/`sensor_b` → `throughput`, 360 rows,
98 test rows). The clean-control classification screenshots intentionally show
one non-empty calibration bin because the selected dummy predicts a constant
probability; this is the real result, not a plotting failure.

## Viewports exercised

| Size | Result |
|---|---|
| 1920 × 1080 | New PR, Q–Q, influence and importance views captured and reviewed |
| 1440 × 900 / 1440 × 950 | All S6 Playwright journeys run here |
| 1366 × 900 | Calibration and subgroup views captured; subgroup table fits without clipping |
| 768 × 1024 | Scatter captured; Model Lab CSS collapses to one column at ≤900 px |
| 390 × 844 | PR diagnostic captured; Scatter and predictive controls/results captured previously |

## Limitations

* Chromium only. Firefox/WebKit were not installed for this session.
* Windows forced-colours mode and screen readers were not tested.
* The 1920 and 1366 screenshots are viewport captures, not full-page captures;
  they show the relevant panel rather than the entire document.
* The calibration screenshot shows a deliberately uninformative dummy model.
  The signal-bearing importance/influence views are captured separately.
