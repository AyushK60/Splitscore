# S11 — Accessibility Review

**Date:** 2026-11-07 · Scope: WCAG 2.2 AA *where applicable to this local-first
research tool*, assessed by code inspection + real-browser keyboard checks.
No automated axe/lighthouse scanner ran in this session and none was installed;
this is therefore a **manual review, not a conformance certification**.

## Verified in place (re-checked on the S11 bundle)

- **Skip link** to `#main` with visible focus style; `main` is focusable
  (`tabIndex={-1}`) and receives focus on every stage change with
  `preventScroll` (main.tsx).
- **Keyboard focus visibility**: global `:focus-visible` outline (2 px accent,
  offset 2) plus control-specific rules; not obscured by the sticky topbar
  (topbar buttons carry their own `:focus-visible`).
- **Semantic navigation**: primary nav is a `<nav aria-label="Primary">` with
  `aria-current="page"` on the active stage; breadcrumb is `<nav aria-label=
  "Breadcrumb">` with an ordered list; the landing has a labelled section nav.
- **Status announcements**: the global busy label renders as
  `<p role="status" aria-live="polite">`; every lazy-stage fallback is
  `role="status"`; the error banner is `role="alert"`.
- **Non-colour-only meaning**: severity chips pair colour with text
  ("evaluated — no finding", "high", …); run/stale states are text.
- **Reduced motion**: global `prefers-reduced-motion: reduce` block + explicit
  `.app-stage` disable (see motion doc).
- **Touch targets**: workbench nav buttons and primary controls use the
  existing ≥ 32–40 px paddings; no change needed at 390 px (verified usable).
- **Zoom/reflow**: 390 px walkthrough shows reflow without loss; no horizontal
  overflow measured on the audited stages.
- **Keyboard alternatives for canvas work**: the DAG editor already offers the
  keyboard edge method ("Draw an edge from this variable (keyboard method)"),
  variable add buttons, and Escape-to-clear — re-verified present.

## S11 changes that improved accessibility

1. Lazy stages now render a `role="status"` labelled fallback instead of
   nothing (Data / Model Lab / Compare / Report Studio).
2. Draft preservation removes a screen-reader/keyboard hazard: work silently
   vanishing on navigation.
3. Stage transition respects reduced motion by explicit rule.

## Known limitations (honest, unchanged)

- The React Flow canvas itself remains pointer-drag-centric; the keyboard
  edge method covers edge creation, but free node positioning by keyboard is
  not offered (documented in earlier stages, unchanged).
- No screen-reader session was conducted; announcement quality is inferred
  from semantics and live-region usage, not from NVDA/JAWS output.
- Automated WCAG scanning was not available in this environment.
