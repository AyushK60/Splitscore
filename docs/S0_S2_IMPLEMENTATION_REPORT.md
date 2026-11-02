# SplitScope V2 — S0 + S1 + S2 Implementation Report

Session date: 2026-11-01
Branch: `v2-premium-visual-foundation` (baseline commit `4f91462` on `main`)

## Stage classification

| Stage | Status | Summary |
|---|---|---|
| S0 — baseline protection & architecture inspection | **COMPLETE** | Baseline captured and committed, branch created, all suites run and recorded before any V1-affecting change. |
| S1 — premium landing page | **COMPLETE** | New `#/` landing route with one dominant animated SVG hero scene, working primary/demo actions, capability explanation, responsive + reduced-motion behaviour. |
| S2 — premium interior interface | **COMPLETE (progressive restyle)** | Shared token layer (`v2.css`) re-themes the whole workbench shell, headers, buttons, tables, findings, empty/error/loading states; all existing workflows preserved. No future-lab features built or advertised as operational. |

## 0. Specification files read

Requested in order, with results:

1. `docs/V2_UX_CLARITY_ADDENDUM.md` — **does not exist in this repository.**
2. `docs/PRODUCT_BLUEPRINT_V2.md` — **does not exist.** The authoritative V2 spec used instead: root-level `SplitScope_V2_PRODUCT_BLUEPRINT.md` (§4.3 landing brief, §4.4 interior, §9 stages S0–S11).
3. `docs/references/causality_workbench_reference.png` — **does not exist.** No reference image was available, so composition follows the blueprint text and the project skills.
4. Project skills loaded: `.agents/skills/premium-scientific-ui/SKILL.md` and `.agents/skills/visual-regression-qa/SKILL.md`.
5. Existing `README.md`, `STATUS.md`, frontend (`src/`, router, state, views) and backend (`backend/app`) inspected.

## S0 — baseline protection

- Preserved all uncommitted V1 work in a baseline commit (`4f91462`, *Baseline checkpoint: SplitScope V1 source before SplitScope V2 visual upgrade*). The unrelated stray file `import requests.txt` was deliberately left untracked and untouched.
- Created working branch `v2-premium-visual-foundation`.
- Baseline verified **before** changes: backend 218 tests, frontend 70 tests, lint, typecheck, production build, synthetic evaluation (41 cases / 61 checks), 4 Playwright journeys — all passing.
- Architecture mapped: single-page React app with hash router, views `Overview / Dataset / Audit / Evidence / Comparison / Export`; FastAPI backend with five leakage checks, dataset workflow, row evidence, split comparison and reports — **all preserved unchanged** (no backend logic modified in this session).

## S1 — landing page (new route `home`)

- `frontend/src/lib/router.ts`: added `'home'` as the default route for an empty hash; `#main` and other non-route anchors no longer switch views (fixes a pre-existing skip-link focus bug).
- `frontend/src/views/LandingView.tsx` (new): sticky product nav, hero, capability strip, three capability cards with **real** navigation into the workbench, a clearly-labelled `PLANNED FOR SPLITSCOPE V2 — NOT AVAILABLE YET` strip (unlinked chips — planned work is never presented as operational), five-step method band, a verification section quoting this repository's real suites with their exact commands, a final CTA, and a disclaimer footer.
- `frontend/src/components/HeroScene.tsx` (new): one dominant animated 660×504 SVG scene — a variable network feeding train/test record columns across a split boundary, a scanning sweep, and one detected duplicate pair arced across the boundary. Entrance staggers, scan sweep, arc pulse and halo; `IntersectionObserver` pauses all animation when out of view; `<title>`/`<desc>` labels for assistive tech. Every number in the scene is marked `SYNTHETIC · CONCEPTUAL`; the caption states explicitly that nothing in the scene is a computed analysis result.
- Hero copy: headline *"From data leakage to causal insight."*, short explanation of data integrity/trustworthy evaluation, primary action **Launch Workbench** (`#/overview`) and secondary **Explore Interactive Demo** (loads the bundled synthetic demo and lands on `#/dataset`) — both verified working by automated click-through.
- `frontend/src/styles/landing.css` (new): full `.lp-*` layout system, hero grid, `hs-*` scene primitives, entrance/scan/halo/arc keyframes, capability cards, roadmap chips, dark method + final CTA bands, responsive breakpoints (1024 / 860 / 640 / 460), and `prefers-reduced-motion` rules that hide `.hs-scan-band`, `.hs-scan-line`, `.hs-arc-pulse` and freeze the halo.
- `frontend/index.html`: updated `<title>` and meta description.
- Design restriction respected: **one** hero composition — no collage of graphs/tables/heatmaps; no fake metrics; every illustration labelled synthetic/conceptual; all buttons functional.

## S2 — interior restyle (progressive, functionality preserved)

- `frontend/src/styles/v2.css` (new), loaded after `app.css`: `:root` token overrides (navy ink, slate text, ivory sunken background, analysis teal `#0a6d7d`, focus ring) re-theme the entire workbench without restructuring the original stylesheet; plus shell (masthead, stepper nav with active state), buttons/forms, cards, tables (quiet header row, tabular numerals), findings, empty/loading/error states, and footer. Severity colours are intentionally untouched so risk levels stay recognisable.
- `frontend/src/main.tsx`: imports the two new stylesheets and `LandingView`, renders the landing route with its own nav/footer (workbench chrome stays inside the workbench), makes the brand mark a real home button, routes focus to the current view's main on every navigation (landing or workbench), and scrolls to top on view change.
- Existing views (`Overview / Dataset / Audit / Evidence / Comparison / Export`), backend API, and E2E-critical classes were not renamed or restructured — every workflow behaves as before.
- Not built (per instructions): Causal Lab, Model Lab, Visual Explorer, subgroup analysis — mentioned only in the clearly-labelled "planned" strip on the landing page.

## Verification — real commands and results

Run in this session against the modified code:

| Command | Result |
|---|---|
| `cd backend && .venv/Scripts/python -m pytest -q` | **218 passed**, 1 warning, 3.5 s |
| `cd frontend && npm run typecheck` (`tsc -b && tsc -p tsconfig.app.json --noEmit`) | **exit 0** |
| `cd frontend && npm run lint` (`eslint . --max-warnings 0`) | **exit 0, 0 warnings** |
| `cd frontend && npm run test` | **70 passed** (6 files) |
| `cd frontend && npm run build` | **exit 0** — 51 modules, 45.65 kB CSS / 335.11 kB JS |
| `cd frontend && SPLITSCOPE_E2E_PORT=8207 npm run test:e2e` | **4 passed** (10.1 s): error-recovery, happy path (demo → audit → evidence → group comparison → report downloads), upload with split column, upload without split column. Port 8123 was already in use by a pre-existing process, so the suite's documented `SPLITSCOPE_E2E_PORT` override was used; nothing outside the project was touched. |
| `python scripts/evaluate_synthetic.py` (baseline, pre-change) | **41 cases / 61 checks, exit 0** |
| `node scripts/capture-v2-screenshots.mjs` against the built app on `http://127.0.0.1:8300` | **exit 0** — checks below |

Capture-script checks (all passed, no fabricated results):

- Landing renders: h1 `From data leakage to causal insight.`
- Horizontal overflow: **0 px** at 1440×900, 768×1024 and 390×844; workbench also **0 px** at 768×1024.
- Keyboard: first `Tab` focuses the skip link with a visible ring (`solid 2px rgb(10,109,125)`).
- Real journey: landing "Explore Interactive Demo" → `#/dataset` loads the synthetic demo → "Run audit" → `#/audit` with findings.
- Reduced motion (`prefers-reduced-motion: reduce`): scan band `display=none`, scene still rendered (545×416).
- **Zero** console errors, page errors or failed requests across all pages.

## Verified screenshots (`docs/screenshots/v2/`)

| File | Content |
|---|---|
| `v2-landing-desktop.png` | Landing page, 1440×900, full page |
| `v2-landing-mobile.png` | Landing page, 390×844, full page |
| `v2-workbench-start.png` | Interior Start screen (`#/overview`) |
| `v2-workbench-dataset.png` | Interior, loaded synthetic demo dataset (`#/dataset`) |
| `v2-workbench-audit.png` | Interior, audit results with findings (`#/audit`) |

All five were captured by Playwright against the production build served by the local backend and were visually inspected.

## Source files changed

Modified:
- `frontend/src/main.tsx` — landing route, stylesheet imports, focus/scroll handling, brand home button
- `frontend/src/lib/router.ts` — `'home'` route, non-route hashes ignored
- `frontend/index.html` — title and meta description
- `frontend/e2e/happy-path.spec.ts`, `frontend/e2e/error-recovery.spec.ts`, `frontend/e2e/upload-path.spec.ts` — entry URL now `/#/overview` (the landing page owns the default route)
- `frontend/scripts/capture-screenshots.mjs` — screenshot entry URLs

Added:
- `frontend/src/views/LandingView.tsx`
- `frontend/src/components/HeroScene.tsx`
- `frontend/src/styles/v2.css`
- `frontend/src/styles/landing.css`
- `frontend/scripts/capture-v2-screenshots.mjs` (visual QA capture + smoke checks)
- `docs/screenshots/v2/*.png` (5 screenshots)
- `docs/S0_S2_IMPLEMENTATION_REPORT.md` (this file)

Unchanged: all backend source, all existing views' logic, `frontend/src/styles/app.css`.

## Git

- Branch: **`v2-premium-visual-foundation`**
- Baseline: `4f91462` — *Baseline checkpoint: SplitScope V1 source before SplitScope V2 visual upgrade*
- Session commit: `SplitScope V2 S0-S2: premium landing page and interior visual foundation` (see `git log`)
- The stray file `import requests.txt` remains untracked and was not committed.

## Local start instructions

```bash
# Backend + frontend (single command serves the built frontend)
cd backend
SPLITSCOPE_PORT=8000 SPLITSCOPE_HOST=127.0.0.1 .venv/Scripts/python -m app.main
# open http://127.0.0.1:8000/           → landing page
# open http://127.0.0.1:8000/#/overview  → workbench directly

# Frontend development (hot reload), backend running as above
cd frontend && npm install && npm run dev

# Full test suite
cd backend && .venv/Scripts/python -m pytest -q
cd frontend && npm run lint && npm run typecheck && npm run test && npm run build
cd frontend && npm run test:e2e        # use SPLITSCOPE_E2E_PORT=<free port> if 8123 is busy
```

(Windows paths: `.venv\Scripts\python -m app.main`.)

## Known limitations / not done

- `docs/V2_UX_CLARITY_ADDENDUM.md`, `docs/PRODUCT_BLUEPRINT_V2.md` and `docs/references/causality_workbench_reference.png` do not exist; the root `SplitScope_V2_PRODUCT_BLUEPRINT.md` was used as the spec of record.
- No backend or algorithm changes: the synthetic evaluation script was run at baseline only (frontend-only session).
- Interior restyle is a token/surface pass over the existing views rather than a redesign of each screen's information architecture — deeper per-screen iteration (tabs/collapsible inspectors) is future work.

## Recommended next-session work

1. **S3+ per-screen interiors:** apply the "one main task per screen" rule view by view (Dataset mapping, Evidence inspector, Comparison) with tabs/collapsible inspectors, re-running the QA capture after each.
2. Add a visual-regression baseline set (Playwright screenshots per view at 1440/768/390) so future styling changes are diffed, not eyeballed.
3. Add landing-page E2E coverage (hero CTA + capability-card navigation) to `npm run test:e2e` so regressions in the new route are caught by CI.
4. Only after S3–S11 are specified: Causal Lab / Model Lab / Visual Explorer — behind clearly-labelled routes, never linked from the landing page until they compute real results.
## Follow-up session — landing page art direction

The first landing pass solved structure but not art direction. The landing page was
redesigned from scratch around a single, deliberate concept.

### Direction: "forensic archive"

The page is a research plate at night and a printed specification by day. Palette:
bottle-ink green-black (`#080e0b` / `#0b1410`), bone ivory (`#ece3d2` / `#f6efe2`),
copper ember (`#d9793f`) reserved for anything the audit *finds*, celadon (`#a7c4b2`)
for structure. No navy, cyan, teal or default-SaaS blue. Typography is a triad: an
editorial display serif (Iowan Old Style → Palatino Linotype → Georgia) for headings,
a grotesque for body, monospace for instrument labels. The split boundary is the one
motif: a vertical rule that runs through the hero, the final band, and the ledger
hairlines. Motion is staged clip-reveals, a filament that draws across the boundary,
one slow scan pass and a breathing halo — nothing bounces.

### Hero

Replaced `HeroScene` (a framed diagram beside the copy) with `HeroField`, a
full-bleed field that *is* the hero background: 42 record rows split into train and
test registers by a dashed boundary with tick marks and a copper laser, six column
threads feeding those rows, and a single filament that leaves a training row, climbs
across the boundary and lands on the testing row that shares its information, with a
`SS-DUP-001` annotation on a leader line. The headline is set over the field in a
display serif with an italic copper phrase, deliberately indented off the grid; the
plate caption sits on dark glass in the lower right. The theme check that this is a
conceptual illustration is in the plate, the index strip and the caption copy.

### Page structure

Five bands with different compositions instead of stacked cards: hero; a capabilities
*ledger* (sticky rail + numbered hairline rows, one row carrying the five implemented
check names, the V2 roadmap reduced to a single honest footnote); a full-width method
band with a staggered five-station timeline on a drawn bus line; an evidence band built
as a hairline 12-column metric grid with a serif pull-quote and an italic caveat; and a
closing band with a manifest of the five real steps. Scroll reveals are one
IntersectionObserver pass (`useRevealOnScroll`), skipped under reduced motion.

### Files

- Rewritten: `frontend/src/views/LandingView.tsx`, `frontend/src/styles/landing.css`
- Added: `frontend/src/components/HeroField.tsx`, `frontend/src/lib/useReveal.ts`
- Removed: `frontend/src/components/HeroScene.tsx`
- Updated: `frontend/index.html` (title, description, theme-color),
  `frontend/scripts/capture-v2-screenshots.mjs` (hero/tablet captures, scroll pass,
  reveal + reduced-motion assertions)

### Verification

`npm run typecheck` 0 · `npm run lint` 0 warnings · `npm run test` 70 passed ·
`npm run build` exit 0 (52 modules, 55.7 kB CSS / 337.3 kB JS) ·
`npm run test:e2e` 4 passed · capture harness exit 0: landing h1 correct, 0px
horizontal overflow at 1440 / 768 / 390 (landing and workbench), 25 sections revealed,
visible focus ring on first Tab, CTA → demo → audit findings, reduced-motion scan band
hidden with 0 hidden sections, zero console/page/request errors.

Screenshots: `docs/screenshots/v2/v2-landing-hero.png`, `v2-landing-desktop.png`,
`v2-landing-tablet.png`, `v2-landing-mobile.png` (plus the three workbench captures).

### Limitations

Display/body faces are system stacks (no webfonts are downloaded — the product is
local-first, so no outbound font requests). The hero field is deliberately illustrative
and labelled as such; it never claims to show a computed result.
