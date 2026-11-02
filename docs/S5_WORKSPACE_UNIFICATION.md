# S5-A — Workspace Unification

**Date:** 2026-11-03
**Scope:** one coherent internal visual identity, the workspace entry
experience, and the full-width responsive workspace (owner problems A, B, C, E
and the S4 chart usability items of problem D).

## What changed

### 1. One workspace identity (was: three assembled ones)

The internal app previously carried the S0–S2 indigo/blue token layer
(`app.css` `:root`, `v2.css` overrides) while Study/Explore used the S3
forensic-archive palette. S5-A replaces the token *values* — not the class
system — so every legacy view re-skins coherently:

- `styles/app.css` `:root` now carries the calibrated archive palette:
  ivory paper (`--bg-sunken #f5f1e7`), deep ink-green structure
  (`--ink #18231d`, masthead band `#12190f`), teal as the workbench action
  colour (`--accent #0a6d7d`), copper reserved for what the audit finds and
  what the user selects, bone/celadon for the masthead and active navigation.
- Instrument geometry: radii drop from SaaS-round (14/9/6 px) to
  precision-panel (4/3/2 px).
- `styles/v2.css` rewritten: it no longer overrides tokens or the masthead —
  it only calibrates typography, tables and buttons on the shared palette.
- The masthead is the landing page's ink band carried inward: bone-on-ink
  brand, mono tagline describing *current implemented* capabilities
  ("leakage assurance workbench · audit · study · explore · compare"), and
  step navigation with a celadon active underline.
- `--mono`/`--sans`/`--display` families now match the landing page's faces.

### 2. Workspace entry (was: a second marketing landing page)

`views/OverviewView.tsx` rewritten from a second hero-and-marketing page into
the instrument's entry panel:

- **No dataset active:** two real ways in — "Upload a dataset" (honest format
  list, size limit, in-memory/privacy statement) and "Open a synthetic
  demonstration" (all six bundled demos with title, purpose, teaching point,
  shape and a real Open action). No decorative content, no third launcher.
- **Dataset active:** a contextual session overview — dataset name, source,
  shape, fingerprint, split and entity, plus one card per stage (Data, Study,
  Explore, Results, Compare) with its actual session state and next action.
- "Launch Workbench" from the landing page leads here; "Explore Interactive
  Demo" still loads the featured demo directly (unchanged).
- Styles live in the new `.we` scope of `styles/research.css`, reusing the
  `.rs` tokens.

### 3. Full-width responsive workspace

- New tokens: `--ws-max: 1800px`, `--ws-gutter: clamp(18px, 2.6vw, 44px)`.
- `.app-main`, `.app-header__inner` and `.app-nav__inner` span the viewport up
  to 1800 px instead of the old 1120 px cap; `.rs` stages span the shell
  (`.rs` no longer self-caps at 1240 px).
- Study Card forms keep a bounded reading width (`.rs-grid` max 1180 px) with
  inputs filling their grid cells (the legacy 340 px input cap no longer
  applies inside `.rs`).
- Form controls, tables and charts expand with the available width.

Measured at 1920×1080 (Explore, most demanding screen): main content 1800 px,
gutters 53/67 px, **93.8 %** of the viewport in use. 1366: **98.9 %**,
1440: **99.0 %**. No horizontal page overflow at any tested width.
Details and per-stage screenshots: `docs/S5_RESPONSIVE_LAYOUT_QA.md`.

### 4. Chart refinement (S4 usability pass, engine untouched)

Parallel coordinates (`ParallelCoordinates.tsx` + `explore.css`):

- Unselected line opacity raised 0.13/0.16 → 0.28/0.34 (dimmed to 0.09 when a
  selection exists, preserving selection contrast); stroke width 1.05.
- Axis header moved clear of the top tick labels (PAD.top 34 → 48); axis
  name/range/tick fonts raised (9/9/11 px → 10/10/12 px mono).
- Plot padding rebalanced (left 90→70, right 150→110) so wide canvases spend
  space on the plot, not on empty margins.

Scatter (`ScatterFocus.tsx`):

- **Real bug found and fixed:** the plot's ResizeObserver attached on mount,
  but the plot div renders only after data arrives, so the SVG kept its
  720×460 initial size forever — the "scatter does not use / may overflow its
  container" symptom. The observer now attaches via a callback ref whenever
  the plot appears; the SVG fills the panel (1329 px in a 1358 px canvas,
  verified in-browser) and never overflows it.
- Phone floors are responsive (`min(420, innerWidth − 40)`) and the plot
  container scrolls horizontally on narrow screens instead of the page.

Row evidence (`RowEvidence.tsx`):

- No-selection state is now a compact guidance card (three short factual
  lines); the long provenance footnote only renders with an active selection.
  No example rows are invented for real datasets.

### 5. Regression protection

- All S4 computations, sampling, row ids and selection logic untouched —
  the changes above are rendering/layout only.
- `e2e` specs updated for the new entry flow (a shared `loadDemoFromEntry`
  helper in `e2e/fixtures.ts`); the two pre-existing lint errors in
  `s4-explorer.spec.ts` (inline `import()` type annotations) fixed.
- Backend: zero changes in S5-A.
