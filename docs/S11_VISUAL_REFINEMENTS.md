# S11-C — Visual Refinements & Responsive Review

**Date:** 2026-11-07 · Screenshots: `docs/screenshots/s11/` (captured on the
S11 bundle by a real browser; every file listed was opened and inspected, not
accepted on exit codes)

## What changed (and what deliberately did not)

The established SplitScope identity — warm ivory paper, deep ink-green
structure, single teal accent, copper for findings/selection, editorial serif
display type — is preserved untouched. S11 made no palette, typography or
layout-system changes; the visual work below is repair-level.

| Area | Change | Evidence |
|---|---|---|
| Landing readout CTA | Wrapped uppercase mono lines now left-align instead of visually centring under the first line (`landing.css`) | `landing-1440.png` |
| Causal variable rail | `scrollbar-gutter: stable` keeps the native scrollbar off the ADD chips (`s8.css`) | `causal-lab-1440.png` |
| Stage appearance | Quiet fade-and-rise on every stage switch (see motion doc) | live check |
| Loading on split stages | Labelled "Loading …" card (no blank swap) for Data / Model Lab / Compare / Report Studio | code + journeys pass |

## Inspected screenshots (1440×900 desktop, 390×844 mobile)

- `landing-1440.png`, `landing-390.png` — hero, plates, CTA hierarchy OK.
- `data-1440.png`, `data-390.png` — readiness checklist, role editor OK.
- `audit-1440.png`, `audit-390.png` — honest summary + risk scorecard OK.
- `causal-lab-1440.png` — drawn node + inspector; rail legibility OK.
- `history-1440.png` — integer run count ("0 runs"), TTL disclosure OK.

## Responsive checks (programmatic + visual)

`document.scrollWidth - clientWidth` measured **0 px** (no horizontal
overflow) at 390 px on landing, Data and Audit results. 1440 px desktop uses
the established `--ws-max: 1800px` full-width workspace with clamped gutters;
no oversized fixed-width containers introduced. The workbench nav collapses to
a horizontally scrollable strip with the active item auto-centred (existing
behaviour, re-verified).

## Known cosmetic items left open (LOW, recorded)

- Several stage-scoped sheets still carry their own long-form animation
  durations (see motion-system doc §Normalization).
- Landing hero plate CTA wraps to two lines at ~1440 px (now left-aligned);
  shortening the label was rejected because the wording is load-bearing.
