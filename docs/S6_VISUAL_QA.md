# S6 visual QA

All screenshots are real Chromium captures of the production build served by the
FastAPI backend. No mock data is used inside the application.

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

## S6-B — Model Lab

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
* The header tagline now names the Model Lab.
* Statistics are rendered in the product’s monospace face; long formulas and
  sha256 values wrap rather than overflow.

## Viewports exercised

| Size | Result |
|---|---|
| 1440 × 900 / 1440 × 950 | Three-region layout; all S6 tests run here |
| 1920 × 1080 | Not captured in this session; layout is max-width bounded (`--ws-max`) |
| 1366 × 768 | Not captured; the 1300 px breakpoint collapses the context column below the results |
| 768 × 1024 | Captured for Scatter; Model Lab collapses to one column at ≤900 px by CSS (not screenshotted) |
| 390 × 844 | Captured for Scatter; horizontal overflow 0 px |

## Limitations

* Chromium only. Firefox/WebKit were not installed for this session.
* Windows forced-colours mode was not tested.
* Screenshots were taken after `Fit model`; the page is scrolled to the top
  programmatically so the masthead and specification controls are visible.
* The Model Lab at 1366 px and 1920 px widths was reviewed by CSS breakpoint and
  typecheck, not by a captured image. A future pass should capture them.
