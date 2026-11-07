# S11-B — HCI & Usability Review

**Date:** 2026-11-07 · **Commits:** `7d1e90a` (audit), `5074e2a` (HCI changes)
**Method:** heuristic review against the S11 brief's HCI objectives, executed
as real-browser walkthroughs (1440×900 and 390×844) of the live application,
plus the existing unit/Playwright suites as regression protection. This is a
design review, **not** a validated human-subject usability study — no
participant scores are claimed.

## Findings and what changed

### 1. Unsaved causal drafts were destroyed by navigation (HIGH — repaired)
**Before:** the draft reducer lived inside `CausalLabView`. Navigating to any
other stage unmounted the view; an uncommitted graph (nodes, edges, scope,
assumptions, undo history) was silently discarded. Reproduced in the S11-A
browser audit: draw a node → History → Causal Lab → node gone.
**After:** `CausalDraftProvider` holds the same reducer above the route switch
(`frontend/src/causal/CausalDraftContext.tsx`). Returning restores the exact
draft; the per-dataset auto-load skips a draft that already belongs to the
current dataset; switching datasets still resets it (justified context change).
Regression-tested in `CausalLabView.test.tsx` ("an uncommitted draft survives
unmounting and remounting the lab") and verified in the live browser.

### 2. Workspace transitions (MEDIUM — implemented)
**Before:** a hard instant swap between stages; the eye got no anchor.
**After:** a keyed `.app-stage` wrapper plays a 260 ms fade-and-rise (3 px).
Opacity/transform only — nothing reflows, input is never blocked, canvases are
not re-laid out, and `prefers-reduced-motion` collapses it to the instant swap.
Because the views already remounted on stage change before S11, the key adds no
state loss; with the draft provider, the state that matters now survives.

### 3. Loading experience (verified sound; one gap closed)
The app already had the hard parts right — labelled busy state in the header
(`role="status"`), no duplicate submissions (nav disabled while busy, guarded
actions), stale-response generation tokens in `AppState`, honest Suspense
labels per lazy route. S11 generalized the per-route Suspense fallbacks into
one `stage(label, node)` helper and extended labelled loading to the four newly
code-split stages (Data, Model Lab, Compare, Report Studio). No fabricated
progress percentages anywhere (verified by grep and walkthrough).

### 4. Navigation & orientation (verified sound)
Stage-ordered primary nav with numbered steps, breadcrumb, and the "NEXT"
guidance strip with contextual actions are all present on every stage and
survive at 390 px (nav scrolls horizontally, active item auto-centred —
existing behaviour, re-verified). Deep links, browser Back/Forward and scroll
reset to top are unchanged and re-verified in the walkthrough.

### 5. Errors, empty states (verified sound)
Audit results distinguish "evaluated, no finding" from "not checked"; the
global error banner carries the backend message plus a collapsible technical
detail block; History explains the in-memory store and TTL; the Causal Lab
empty state explains what will appear. No changes needed beyond the count
format fix (AUDIT-2 in S11-A).

## Deliberately not changed
- The landing page (already coherent; only a wrapped-line alignment fix).
- Navigation order, stage gating, or any scientific flow — all preserved.
- No new animation dependency was introduced; the motion system is pure CSS
  custom properties.
