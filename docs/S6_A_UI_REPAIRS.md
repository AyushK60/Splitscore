# S6-A — user-reported UI repairs

**Checkpoint scope:** the four defects the owner found by hand in S5. No
statistical or ML capability was added in this commit.

**Repository:** `E:\Splitscore V2` · branch `v2-premium-visual-foundation` ·
baseline `660ea7c`.

---

## B1 — Scatter expanded the page without bound

### Symptom

Explore → Scatter kept increasing `document.scrollHeight`. The scrollbar
chased an unreachable bottom; leaving the tab was the only escape.

### Root cause (confirmed by measurement, not inference)

`ScatterFocus.tsx` observed the **plot container** with a `ResizeObserver` and
fed its measured height straight back into the SVG:

```tsx
const rect = entries[0].contentRect
setSize({ width: …, height: Math.max(340, rect.height) })
…
<svg width={size.width} height={size.height}>
```

The observed element `.xfig__plot` had **no definite height**: its height came
from the inline SVG it contained. An inline SVG is an inline-level box, so the
container was always a few pixels taller than the SVG (line-box descent). Each
observer callback therefore set the SVG — and with it the container — a few
pixels taller, which fired the observer again. A classic self-sizing feedback
loop.

The S5 fix addressed a *different* failure (observer attached before the
conditional plot existed); it made the observer attach reliably, which is what
exposed this loop.

Measured on the pre-fix build (360-row `chronology_violation` demo, 1440×900):

```
scrollHeight: 2174  2324  2474  2630  2774  2930     (2.4 s, still growing)
SVG height  : 2092 px
```

### Fix

* `.xfig__plot--sized` now owns a **definite CSS height**
  (`clamp(340px, 46vh, 520px)`), and its child SVG is `display: block`.
  The observer reads that height; it can no longer be produced by the SVG it
  sizes, so the loop cannot re-form.
* The observer writes state only when the rounded width/height actually
  changes, removing residual sub-pixel churn.
* Initial measurement uses the element's bounding box instead of waiting for
  the first observer callback.
* Width still follows the container, and the 420 px phone floor with
  horizontal scrolling is preserved.

### Verification

Measured after the fix, same demo, same viewport:

```
scrollHeight: 1396  1396  1396  1396  1396  1396   (constant)
SVG height  : 414 px  (inside its container)
```

New Playwright regression `frontend/e2e/s6-ui-repairs.spec.ts`:

* height spread ≤ 4 px across eight observations;
* repeated scroll-to-bottom and back does not change the height;
* SVG height never exceeds its container;
* viewport resize, axis changes, and focus-mode open/close each settle to a
  new stable height;
* the plot still renders points after all of that.

Evidence: `docs/screenshots/s6/before/scatter.png` (2092 px SVG),
`docs/screenshots/s6/after/scatter.png`.

---

## B2 — header hover made labels unreadable

### Root cause

`app.css` has a global control hover:

```css
button:hover:not(:disabled) { background: var(--accent-soft); color: var(--accent-deep); }
```

The masthead's nav rule then overrode only the **colour**:

```css
.app-nav button:hover:not(:disabled) { color: var(--bone); … }
```

so hovering produced `--bone` (pale ivory) text on `--accent-soft` (pale
teal) — unreadable. The brand is a `<button>` too: hovering it painted the
same pale fill behind the pale wordmark.

### Fix (`frontend/src/styles/app.css`)

* `.app-nav button` sets `background: transparent` in default, hover, current
  and disabled states; the current+hover combination is stated explicitly so
  the active indicator (celadon underline) is preserved.
* `.app-header__brand--home:hover/:active` resets background, colour, border
  and transform; hovered title/tagline stay `--bone`.
* `.app-topbar button:focus-visible` uses a **celadon** 2 px outline (the
  global teal ring is too close in luminance to the ink band).
* No layout shift: no padding, border width or font weight changes on hover.

### Verification

`e2e/s6-ui-repairs.spec.ts` hovers every primary nav item, the current stage
(active + hover) and the wordmark, then computes WCAG contrast from the
**computed colours composited over the painted ancestors**. Every case is
≥ 4.5:1. Keyboard focus is asserted to be `:focus-visible` with a 2 px celadon
outline.

Evidence: `docs/screenshots/s6/after/topbar.png`,
`docs/screenshots/s6/after/topbar-hover.png`.

---

## B3 — workflow order contradicted the audit transition

### Problem

The nav read Start → Data → Study → Explore → Results → Compare → Export, but
“Run the audit” on Data went straight to stage 5. The user reasonably
concluded stages 3 and 4 had been skipped.

### Fix

The primary path now follows the work actually performed:

| Step | Label | Route (unchanged) |
|---|---|---|
| 1 | Start | `#/overview` |
| 2 | Data | `#/dataset` |
| 3 | **Audit results** | `#/audit` |
| 4 | Study (optional) | `#/study` |
| 5 | Explore (optional) | `#/explore` |
| 6 | Compare | `#/comparison` |
| 7 | Export | `#/export` |

* Study and Explore are labelled `(optional)` in the Start overview and its
  guidance; they remain fully usable before or after an audit.
* A new **breadcrumb + next-step strip** under the nav names the current stage
  (`Workspace / Audit results`) and states the real next actions, with working
  links only to existing routes. Copy per stage:
  * Data — “Run the audit once the split and roles are confirmed. Study and
    Explore stay optional.”
  * Audit results — “Open a finding's evidence, explore the data, or compare
    split strategies.”
  * Study — “Study metadata is optional context. Explore the dataset, or run
    the audit from Data.”
  * Explore — “Selections are analysis context, not findings…”
* No fake sequential wizard and no gating. Routes, hashes, deep links and
  browser history are unchanged; the nav still uses `window.location.hash`.
* `OverviewView` stage cards were reordered to Data → Audit results → Study →
  Explore → Compare and mark the optional stages as optional.

### Verification

`e2e/s6-ui-repairs.spec.ts` asserts the exact step/label sequence, that
running the audit from Data makes step 3 `aria-current="page"`, that the
breadcrumb follows, that `goBack()`/`goForward()` walk Data ↔ Audit results,
and that Study remains reachable afterwards. The S4 spec's nav label was
updated (`Results` → `Audit results`); S3/happy-path selectors already matched
`/Results|Audit/`.

Evidence: `docs/screenshots/s6/after/workflow-data.png`,
`docs/screenshots/s6/after/workflow-audit.png`.

---

## B4 — Parallel Coordinates needed novice guidance

The algorithm is untouched (same rows, same brushes, same shared selection
engine). Presentation changes only:

* **Compact persistent hint** above the canvas: each line is one observation,
  each rail a variable, drag a rail to brush.
* **“How to read this chart”** toggle (keyboard-operable button,
  `aria-expanded`, `aria-controls`) opens a four-part progressive guide:
  observation/rail encoding, crossings (explicitly *not* correlation,
  causation or leakage), and brushing semantics.
* **Annotated miniature example** — two rails with two crossing lines and a
  caption; decorative, not analysis.
* **Selection count in the plot header** (`N selected` / `no rows selected`),
  plus the existing legend count of drawn vs total.
* **Empty-selection guidance** under the legend until the first brush.
* **Brush affordance**: `ns-resize` cursor, `aria-label` per rail, and the
  existing “drag over an existing brush to remove it” hint retained.
* Axis names remain full in the reorder bar and tooltips; units are the
  column's own units and no unit is invented when the study has not declared
  one.
* The guide states that drawn density is the render sample and that the chart
  is exploratory.

### Verification

`e2e/s6-ui-repairs.spec.ts` drives the guide by keyboard, checks the panel
contents and example, then brushes a rail and reconciles three independent
numbers: the header count, the legend “drawn / total”, and the Row Evidence
“N of 360 rows selected”, plus the number of copper selected paths.

Evidence: `docs/screenshots/s6/after/pc-help.png`.

---

## Verification ledger for S6-A

| Check | Command | Result |
|---|---|---|
| Backend | `python -m pytest -q` | 340 passed |
| Synthetic oracle | `python scripts/evaluate_synthetic.py` | 41/41 cases, 61/61 checks |
| Frontend unit | `npm run test` | 82 passed |
| Typecheck | `npm run typecheck` | clean |
| Lint | `npm run lint` | clean, 0 warnings |
| Build | `npm run build` | clean |
| Playwright | `SPLITSCOPE_E2E_PORT=8180 npx playwright test` | **15 passed** (11 pre-existing + 4 new) |
| Responsive | new spec + captures at 390×844 and 768×1024 | horizontal overflow **0 px** on both |

## Honest limitations

## S6-B update to the stage order

S6-B inserted the Model Lab after Explore, so the current primary path is
Start 1 · Data 2 · Audit results 3 · Study 4 · Explore 5 · **Model Lab 6** ·
Compare 7 · Export 8. The S6-A ordering rule is unchanged — the audit is still
the third stage and is still reachable directly from Data; Study and Explore
remain optional. The S6-A browser test now asserts the extended sequence.

* Contrast is computed for the normal (non-forced-colours) rendering. Windows
  High Contrast / `forced-colors` was not exercised; the app's colours are
  author-defined, so forced-colours mode will substitute system colours.
* Only Chromium is configured for Playwright; Firefox and WebKit were not run.
* The Scatter regression bounds the height by measurement; it does not prove
  the absence of every possible future layout loop in unrelated charts.
* Element screenshots of the parallel-coordinates figure are clipped by the
  sticky masthead at the top edge; that is a capture artifact, not a page
  overflow (the measured document width is unchanged).
