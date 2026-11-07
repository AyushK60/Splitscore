# S11 — Interaction & Motion System

**Date:** 2026-11-07 · Introduced in commit `5074e2a`

## Tokens (`frontend/src/styles/app.css`, `:root`)

| Token | Value | Use |
|---|---|---|
| `--motion-fast` | 120 ms | interaction feedback: hover, press, focus, colour/border changes |
| `--motion-base` | 180 ms | controls appearing in place: dropdowns, inline reveals |
| `--motion-slow` | 260 ms | workspace-level stage appearance — nothing larger |
| `--ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | state changes |
| `--ease-emphasis` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | elements that enter |

## Rules

1. **Motion clarifies state changes; it never competes with data.** No springy
   or exaggerated easing; no staggered entrances on dense analytical pages; no
   animation delays added to fast operations.
2. **Stage transition.** `.app-stage` (keyed by route in `Shell`) plays
   `stage-in`: opacity 0→1 with a 3 px rise over `--motion-slow`.
   Opacity/transform only — nothing reflows, input is never blocked, and the
   analytical canvases are not re-laid out.
3. **Reduced motion.** The global `prefers-reduced-motion: reduce` block in
   `app.css` collapses every transition/animation to ~0 while the spinner is
   deliberately kept at 2 s so loading feedback stays comprehensible; the
   `.app-stage` animation is additionally set to `none` explicitly. Functional
   state changes still apply — instantly.
4. **Cheap properties only.** All normalized transitions animate colour,
   background, border, opacity or transform. No width/height/top/left
   animation on page regions; precision-critical chart geometry is never
   animated.

## Normalization applied

The S11-A audit found 44 `transition:` declarations across `styles/*.css` with
durations from 120 ms to 1.6 s and mixed easings. The eight shared
interaction-feedback transitions in `app.css` (buttons, inputs, cards,
controls) now use the tokens. Stage-scoped sheets (`s3/s7/s8/s9/explore/
landing/research/models`) keep their deliberate long-form sequence animations
(landing observatory, reveals) — those are marketing/hero motion with their own
reduced-motion handling, not interaction feedback; converging them onto the
tokens is recorded as future polish, not S11 scope.

## Verification

- `tsc`/`eslint` clean; vitest 246/246; production build OK.
- Live-browser check: stage navigation feels anchored without delaying input;
  keyboard focus remains visible (existing `:focus-visible` rules untouched).
- Reduced-motion: the global block predates S11 and is re-verified present;
  the stage animation carries its own explicit `none` override.
