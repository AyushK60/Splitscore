# S9C Audit Handoff

**Status:** audit complete, verdict **PASS**, S10 authorised to proceed.
**Repair commit:** the S9C audit checkpoint on `v2-premium-visual-foundation`.

## What this session changed

- `frontend/src/styles/s9.css` — `--est-*` palette hoisted from `.eststudio`
  to `:root` (AUDIT-1, whiskers).
- `frontend/src/research/WhatIfView.tsx` — numeric placeholder shortened
  (AUDIT-3).
- `frontend/tests/CausalIdentification.test.tsx` — hydration race fixed
  (AUDIT-2); 15/15 soak.
- `frontend/e2e/s9c-research.spec.ts` — painted-whisker regression guard in
  journey A.
- `backend/tests/test_s9c_independent_audit.py` — **new**, 15 independent
  numerical-verification tests.
- `backend/tests/test_s9c_research_api.py` — 4 new API-integrity tests
  (fingerprint 409 on all three S9C routes; malformed robustness body).
- `frontend/scripts/_s9c_audit_forest.mjs`, `_s9c_audit_colormix.mjs` —
  untracked audit probes (kept untracked like the other session scratch).
- `docs/S9C_INDEPENDENT_AUDIT.md`, `docs/S9C_FINAL_VERIFICATION.md`, this file.
- `docs/screenshots/s9c/*` — re-captured by the full Playwright run with the
  whisker repair in place.

## Decisions worth not re-litigating (S10 input)

1. **The dossier extension must be server-side and versioned.** The S7
   dossier engine (`backend/app/reports/dossier.py`) is the reporting path;
   S10 extends `SECTION_SPECS` + summarisers + renderers — never
   frontend-only report generation.
2. **Estimation runs are already first-class** (`RunKind` includes
   `"estimation"`; `estimationApi.runs/runDetail` exist). The dossier request
   simply has no estimation source fields yet — that is the integration gap.
3. **Figure exports already carry provenance** (`FigureExportMeta` with
   run_id, fingerprints, CSV of plotted values, JSON metadata). S10-C should
   consolidate this, not rebuild it.
4. **The store is bounded/in-memory by design** (max_runs=16, TTL 1 h). S10-A
   must stay within that philosophy: session history + explicit export.
5. Subgroup pseudo-outcome provenance, sensitivity-as-scenario (not bound),
   and what-if-without-intervals are settled science in this codebase —
   preserve them verbatim in any dossier text.

## Environment / runbook

Unchanged from `S9B_FINAL_HANDOFF.md`, with one operational note: Playwright
needs the **project venv on PATH** (`export PATH="/e/Splitscore V2/.venv/Scripts:$PATH"`)
because `playwright.config.ts` starts the backend with `python -m app.main`.

## Preserved, deliberately untracked

`_s9b_*.log`, `_s9b_compare.json`, `import requests.txt`,
`scripts/_patch_s3_hero.py`, `scripts/_audit_repro_subgroup_keyerror.py`,
`docs/screenshots/*/_preview/` remain untouched session scratch.
