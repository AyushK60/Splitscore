# S5 verification

**Date:** 2026-11-03
**Scope:** independent end-to-end verification of S5-A/B/C on the committed
checkpoints. Every claim below is backed by a command run during S5-D.

## Automated verification

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` (backend) | **340 passed**, 1 deprecation warning (httpx/starlette, pre-existing) |
| Synthetic oracle | `python scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks, exit 0** |
| Frontend unit tests | `npm run test` | **82 passed** (8 files) |
| TypeScript | `npm run typecheck` | clean |
| Lint | `npm run lint` (`--max-warnings 0`) | clean (2 pre-existing S4 lint errors also fixed in S5-A) |
| Production build | `npm run build` | clean (`tsc -b && vite build`) |
| Playwright E2E | `SPLITSCOPE_E2E_PORT=8180 npx playwright test` | **11 passed** |

Note: the E2E webServer port defaults to 8123; an out-of-repo process on this
machine holds that port (verified with a raw-socket bind test — nothing
visible in `netstat`). The suite runs with `SPLITSCOPE_E2E_PORT=8180`; the
config default is unchanged and works on unblocked hosts.

## Browser verification (real Chromium, production build, port 8000)

Journeys from the S5 specification, each exercised and screenshotted:

1. **Landing → Launch Workbench → demo → Data** — the entry panel lists the
   six demos with real Open actions; opening navigates to Data.
2. **Landing → Explore Interactive Demo** — unchanged; loads the featured demo
   into the Data stage.
3. **Data → Study → edit Study Card → Explore** — study form renders in the
   bounded two-column grid; Explore returns the parallel-coordinates canvas.
4. **Explore → brush → evidence** — a brush of [2.750, 4.250] on `month_index`
   selects exactly 80 of 240 rows; the Row Evidence inspector shows the file's
   own values (`row-000004`, customer `C1000`, …) with pagination; selected
   lines draw copper across all axes. **This journey exposed and fixed a real
   S4 bug** — brush coordinates were read rect-relative but used as SVG
   coordinates, shifting every brush by the top padding (a mid-axis brush was
   in range, which is why S4's centre-of-axis e2e never caught it).
5. **Results → audit → finding → Row Evidence** — the audit runs 11 checks;
   finding cards link to evidence with exact counts and denominators.
6. **Compare → plans → visualization → assignment export** — Group CV (5
   folds) audits in ~0.4 s; fold strips and aggregates show zero entity
   overlap (as group CV guarantees) and mean test fraction 20 %; CSV export
   path unchanged.
7. **Risk category → underlying finding** — the scorecard's "Open evidence:
   SS-ENT-001" resolves to the Evidence view with the full count table.
8. **Similarity pair → source rows** — the Pair Inspector resolves both
   immutable row ids to the file's own values via the rows endpoint.
9. **Refresh / deep-link** — `#/explore` after reload shows the honest
   "Nothing loaded yet" state (in-memory session model preserved); navigation
   and back behaviour unchanged.
10. **Desktop and mobile** — see `docs/S5_RESPONSIVE_LAYOUT_QA.md`.

## Defects found and fixed during verification

| Defect | Found by | Fix |
|---|---|---|
| Scatter SVG stuck at 720×460 (ResizeObserver attached before the conditional plot existed) | S5-A browser pass | observer re-attaches via callback ref; SVG fills the panel |
| Parallel-coordinates brush shifted by PAD.top (rect-relative offsetY used as SVG coordinate) | S5-D journey 4 | brush geometry measured against the SVG bounding box |
| Proxy screen flagged continuous float columns | S5-B demo audit | continuous measurements excluded from the identifier-like screen |
| SS-VRU-001 reported "no history" for an empty history | code review | `None` (not supplied) → NOT EVALUATED; `[]` → evaluated with count 0 |
| Duplicate row-id: recommended audit configs from older payloads crashed the new editor | S5-B browser pass | frontend merges configs over defaults |

## Honest limitations

- Preprocessing fit isolation and prediction-time availability are evaluated
  **from declarations**; SplitScope still does not execute pipelines.
- Evaluation plans audit leakage consequences per fold; there is still no
  model engine, so no performance numbers exist anywhere.
- The comparison table's old textual presentation remains alongside the new
  visuals; both are computed from the same audited data.
- The E2E suite does not yet drive the new similarity tab or plan flows in
  Playwright (they are covered by 15 backend tests plus the browser journeys
  documented here); adding those specs is recommended S6 entry work.
