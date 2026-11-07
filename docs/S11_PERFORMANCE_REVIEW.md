# S11 — Performance Review

**Date:** 2026-11-07 · All measurements local (Windows, dev machine), production
builds, same conditions before/after. These are automated local measurements,
**not** real-user field data; Core Web Vitals budgets are used as reference
targets only.

## Bundle (before → after, minified / gzip)

| Chunk | S10 (`f7103ea`) | S11 (`5074e2a`) |
|---|---|---|
| **main `index-*.js`** | **589.16 kB / 161.75 kB gz** | **405.53 kB / 120.83 kB gz (−31 %)** |
| CausalLabView | 249.08 kB | 243.34 kB (lazy) |
| EstimationView | 100.26 kB | 100.26 kB (lazy) |
| ResearchView | 39.53 kB | 39.53 kB (lazy) |
| DatasetView | — eager | 50.11 kB (lazy) |
| ModelLabView | — eager | 63.20 kB (lazy) |
| ComparisonView | — eager | 19.56 kB (lazy) |
| ExportView | — eager | 57.31 kB (lazy) |
| main CSS | 180.67 kB | 181.67 kB (+ motion rules) |

The Vite ">500 kB" warning is gone. The main chunk still carries React/ReactDOM
and the eager early stages (landing, start, study, audit, evidence, explore,
history) — deliberate: those stages are the first minutes of use and their
chunks would each be small. Further splitting is possible (AuditView +
FindingCard ≈ 80 kB is the next candidate) but returns diminishing value;
recorded as future polish.

## Load & interaction

- First paint path (landing) is unchanged in composition — landing CSS/JS was
  already eager; the stage transition adds ~1 kB of CSS and one composited
  animation (opacity/transform).
- Route transitions: lazy chunks load from cache on repeat visits; first
  visits show the labelled `role="status"` card. On localhost the fallback is
  visible only for tens of milliseconds; it is not an artificial delay and
  navigation input is never blocked.
- The stage animation is composited-only: no layout/reflow is triggered by
  navigation beyond the existing remount.
- CLS risk of the 3 px stage rise: transform-based, no layout shift.

## Runtime hygiene (verified, unchanged)

`AppState` cancels stale responses via generation tokens; the causal lab
keyboard handler is ref-stable; explore/estimation canvases render from
plotted values without animation loops. No event-listener leaks introduced;
the only new listener-bearing code (none) was avoided — the stage transition
is pure CSS.

## What was not measured

LCP/INP field metrics (no RUM instrumentation exists, and adding telemetry is
out of scope for a local-first app); memory profiling over long sessions.
