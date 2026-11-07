# S11-A — Independent Initial Audit

**Date:** 2026-11-07 · **Branch:** `v2-premium-visual-foundation` · **Start commit:** `f7103ea`
**Auditor role:** independent S11 release engineering audit. Every number below was
re-executed in this session against the working tree; reported S10 baselines were
not taken on trust.

---

## 1. Baseline verification (re-executed, not inherited)

| Gate | Reported (S10) | S11-A re-run | Verdict |
|---|---|---|---|
| Backend pytest | 620 passed | **620 passed** (410.8 s, 3 benign warnings: 1 starlette deprecation in testclient, 2 numpy RuntimeWarnings in a singular-design test) | ✅ match |
| Frontend vitest | 245 passed | **1 failed / 244 passed on first run; 245/245 on rerun** → flaky test confirmed and repaired (§3.1) | ⚠️ flake → fixed |
| Synthetic leakage oracle | 41/41, 61 checks | **41/41 cases, 41 passed, 61 checks, 0 failed** | ✅ match |
| TypeScript (`tsc -b` + app noEmit) | clean | **clean** | ✅ |
| ESLint (`--max-warnings 0`) | clean | **clean** | ✅ |
| Production Vite build | successful | **successful**; main chunk **589.16 kB (161.75 kB gzip)** — the known >500 kB warning persists | ✅ build / ⚠️ size |

Commands: `.venv/Scripts/python -m pytest backend/tests -q`; `npx vitest run`;
`.venv/Scripts/python scripts/evaluate_synthetic.py`; `npx tsc -b && npx tsc -p
tsconfig.app.json --noEmit`; `npx eslint . --max-warnings 0`; `npm run build`;
`npm run test:e2e` (fresh backend on port 8123, 39 journeys).

## 2. Repository state

- HEAD `f7103ea`, clean tracked tree. Preserved untracked scratch (`_s9b_*` logs,
  `import requests.txt`, `scripts/_patch_s3_hero.py`, audit repro scripts,
  screenshot `_preview/` dirs) and the `stash@{0}` S3 checkpoint — untouched.
- Environments: repo-root `.venv` (Python 3.11.9) and `frontend/node_modules` intact.
- Routing: hash router (`lib/router.ts`) with 14 views; `CausalLabView`,
  `EstimationView`, `ResearchView` are `React.lazy` code-split; the other
  eleven views ship in the main chunk (this is why the main bundle is large).

## 3. Confirmed defects found and repaired in S11-A

### 3.1 Flaky identification test (MEDIUM — test infrastructure)
**Evidence:** first full `vitest run` failed `CausalIdentification.test.tsx`
"runs identification and renders suggested sets with highlights" at
`expect(checkbox.checked).toBe(true)`; the same file passed 9/9 in isolation and
245/245 on immediate rerun. Same failure class as S9C AUDIT-2 (interacting before
async hydration settles under full-suite load).
**Repair:** the checked-state assertion is now awaited via `waitFor` (assertion
strength unchanged). This was the only frontend flake observed.

### 3.2 Run-count formatted like a measurement (LOW-MEDIUM — visual/functional)
**Evidence:** History view rendered "1.000 run for repeated_entity.csv" —
`formatNumber()` (the 3-decimal *estimation figure* formatter) was applied to a
run **count**.
**Repair:** `HistoryView.tsx` now uses `formatCompact()` (integer counts).
No scientific value affected; `formatNumber` users elsewhere were audited and are
all genuine continuous quantities.

### 3.3 Ad-hoc motion system (MEDIUM — design-system debt, S11-B target)
**Evidence:** 44 `transition:` declarations across `styles/*.css` with durations
from 120 ms to 1.6 s and mixed easings; no motion tokens exist; reduced-motion
support is present but per-file and inconsistent (8 separate media blocks with
both `reduce` and `no-preference` forms).

## 4. Functional audit — real-browser walkthrough (1440×900 and 390×844)

Executed against the live backend (`python -m app.main`, serving `frontend/dist`):

- **Journey 1 (first-time researcher):** landing → hero CTA → overview → open
  "Repeated-entity subscription panel" demo → Data view (4-step readiness
  checklist all green, split source honest) → Run audit → Audit results with
  1 high finding, "6 of 11 checks, 5 did not run and are listed separately" —
 PASS. The stage guidance line ("NEXT …") is present on every step.
- **Causal Lab:** lazy chunk loads with an honest empty state ("No saved graphs
  yet"), teaching examples labelled as assumed structure, and the standing
  disclaimer that a valid DAG is not evidence the assumptions are true. PASS.
- **History:** run projection shows the session's audit run with identity,
  staleness model and TTL disclosure. PASS (after §3.2 fix).
- **Mobile 390 px:** landing and workbench reflow correctly; nav collapses to the
  available stages (Start/Data before a dataset is loaded); no horizontal
  overflow observed on the audited pages. PASS.

Continuous full-workflow verification (audit → causal analysis → estimation →
research → dossier → downloads) is delegated to the real-backend Playwright
suite (39 journeys, fresh backend process), running as part of this audit; the
result is recorded in `S11_FINAL_VERIFICATION.md`.

## 5. Scientific integrity spot-checks

- Audit summary language stays honest: "A finding is evidence about this split
  and this configuration, not a verdict on the dataset"; "evaluated, no finding"
  is explicitly distinguished from "not checked". No wording found that claims
  proof.
- Causal Lab states "No causal effect is estimated anywhere in this workspace";
  Estimation/Research guidance re-derives the conditional-on-assumptions framing.
- CSV export carries documented spreadsheet-formula-injection sanitisation
  (`csv_export.py`: `=`, `+`, `-`, `@`, tab, CR prefixed with `'`, with an
  in-file header note and API note).
- Dossier HTML escapes every user-supplied value (`html.escape(..., quote=True)`,
  `dossier_html.py`); no raw interpolation of dataset content into report HTML.
- State layer (`AppState.tsx`) uses generation tokens + sequence guards so stale
  responses cannot overwrite newer results; failed estimator paths render as
  failures (verified in S9B/S9C suites, re-run above).

## 6. Defect classification / S11 backlog

**CRITICAL:** none found.
**HIGH:** none found.
**MEDIUM (open, ordered):**
1. Main chunk 589 kB — needs scoped code-splitting of eager views (§19 of the
   S11 brief). Target: move the large eager analytical views behind `lazy()`
   without changing navigation behaviour.
2. No coherent motion token system (§3.3 above) — S11-B/C deliverable.
3. Workspace switching is an instant swap; no subtle appearance transition to
   anchor the eye (S11-B deliverable, must not animate canvases or delay input).

**LOW:** landing hero card's "Run this audit on the synthetic demo" label wraps
with centred alignment at 1440 px; left-panel scrollbar can slightly overlap the
last "ADD" chip in the Causal Lab variable list. Cosmetic only.

## 7. Verdict

**CONDITIONAL PASS** — no critical or high defect; the scientific content is
honest and the workflows verified function. S11-B/C/D must address the three
MEDIUM items above before release readiness is claimed.
