# S5-A — Responsive Layout QA

**Date:** 2026-11-03
**Method:** real browser (Chromium via ZCode in-app browser), production build
served by `python -m app.main`, `repeated_entity` synthetic demo loaded.
Measurements taken with `getBoundingClientRect` on the live DOM.

## Width utilisation (Explore — the most demanding screen)

| Viewport | Content width | Left gutter | Right gutter | Used | Page overflow |
|---|---|---|---|---|---|
| 1920×1080 | 1800 px | 53 px | 67 px | **93.8 %** | none |
| 1440×900 | 1425 px | 0 px | 15 px | **99.0 %** | none |
| 1366×768 | 1351 px | 0 px | 15 px | **98.9 %** | none |
| 390×844 | stacked panels | — | — | single column | **none** (fixed during QA) |

The 1800 px shell cap keeps ultra-wide layouts composed; scientific canvases
receive the full remaining width. Before S5-A the same screen was capped at
1120 px (≈58 % at 1920).

## Chart containment

| Check | Result |
|---|---|
| Parallel-coordinates SVG inside canvas panel | 1329 px in 1358 px panel — inside |
| Scatter SVG inside canvas panel | 1329 px in 1358 px panel — inside (was 720 px before the ResizeObserver fix) |
| `document.scrollWidth > innerWidth` at 1920/1440/1366/390 | false everywhere |

## Mobile (390×844)

- Controls, tabs, plot and inspector stack in one intentional column.
- Chart floors shrink to the viewport; plot containers scroll horizontally
  within their panel instead of overflowing the document.
- Navigation wraps to two rows; active stage keeps its celadon underline.

## Screenshots

`docs/screenshots/s5/after/` (post-S5-A) versus `docs/screenshots/s5/before/`
(S4 state):

| After file | Screen / viewport |
|---|---|
| `07-explore-1920.png` | Explore, parallel coordinates, 1920 |
| `08-entry-1920.png` | Workspace entry (no dataset), 1920 |
| `09-data-1920.png` | Data, 1920 |
| `10-study-1920.png` | Study, 1920 |
| `11-compare-1920.png` | Compare, 1920 |
| `12-explore-1366.png` | Explore, 1366 |
| `13-scatter-1920.png` | Explore, scatter tab filling the panel, 1920 |
| `14-explore-390.png` | Explore stacked mobile layout, 390 |

Additional preview captures made during the repair loop are in
`docs/screenshots/s5/_preview/`.

## Sticky navigation

The masthead is sticky; every stage change scrolls to top and moves focus to
`<main>` (pre-existing behaviour, re-verified). Headings are not hidden under
the bar.

## Known notes

- Playwright's E2E webServer port defaults to 8123; a process outside this
  repository holds that port on the current machine (verified with a raw
  socket bind test — nothing visible in `netstat`). The suite is run as
  `SPLITSCOPE_E2E_PORT=8180 npx playwright test` on this machine; the config
  default remains 8123 and works on unblocked hosts.
