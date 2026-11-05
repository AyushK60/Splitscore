# S8C visual verification

**Date:** 2026-11-06 · All screenshots captured by the real Playwright
journeys (`e2e/s8c-identification.spec.ts`) against the production build
served by the real backend. Reviewed at native size after capture.

## Captures

| File | Shows |
|---|---|
| `s8c_identification_available.png` | Desktop 1440: valid adjustment-set identification — status banner, suggested set chip, mode switch, legend, canvas with treatment/outcome tags. |
| `s8c_collider_empty_set.png` | M-structure: the empty set correctly reported as the minimal admissible set. |
| `s8c_collider_conditioning_refused.png` | Invalid adjustment selection: structured violation panel ("Set not admissible", open backdoor path named). |
| `s8c_unobserved_confounder_warning.png` | Unobserved-confounder honesty: `no_eligible_backdoor_set`, caveat, dashed unobserved node on canvas. |
| `s8c_stale_results.png` | Identification alongside the graph after a scientific edit: save gate + "Results are stale" banner. |
| `s8c_identification_rerun.png` | After rerun: updated verified set, staleness cleared. |
| `s8c_tablet_768.png` | Tablet layout: identification inspector overlays the canvas per the S8B ≤1024 px convention. |
| `s8c_mobile_390.png` | Mobile layout: no horizontal overflow; rail overlays panel; mode switch reachable. |

## Review findings and resolutions

1. **Defect found and fixed:** the global `button:hover:not(:disabled)` rule
   (app.css) paints *every* button accent-soft on hover and outranked the
   selected mode tab's solid accent fill — hovering the active
   **Identification** tab made it look unselected (visible in the first
   `s8c_stale_results` capture, where Playwright's pointer rests on the tab
   after clicking it). Fixed in `s8.css` with hover-specific rules for the
   segmented switch: inactive tabs hover to ink text on transparent ground,
   the selected tab keeps its solid fill (deepening to `--accent-deep` on
   hover). Screenshots recaptured; all four journeys re-passed.
2. Panel scrolling: the identification panel is long by design; it scrolls
   within its rail exactly like the S8B inspector. At tablet/mobile widths it
   overlays the canvas (existing S8B convention) rather than squeezing it.
3. No layout defects in the categories the brief forbids: no nodes off-screen
   (auto-fit + fit-view preserved), edges readable, no panel overlap of graph
   elements at desktop width, warnings never overflow (long text wraps inside
   bordered sections), controls reachable at 390 px (verified programmatically
   by the overflow assertion), explanations never overpower the canvas (the
   canvas remains the dominant region at 1440/1024).
4. Legend (treatment / outcome / in tested adjustment set / unobserved) sits
   in the canvas corner and never overlaps nodes at the default auto-fit.

## Acceptance

The identification experience preserves the S8B visual identity: paper/ink
nodes, copper selection, spacious canvas, collapsible rail, contextual right
panel. Nothing outside the Causal Lab changed visually.
