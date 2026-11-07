# S11 — Release Handoff

**Date:** 2026-11-07 · **Branch:** `v2-premium-visual-foundation`
**Start:** `f7103ea` → **Final:** S11-D (audit `7d1e90a`, HCI `5074e2a`, this commit)

## Verdict: RELEASE READY (local/private research demo)

The intended local demo is functionally, scientifically and visually verified
with no unresolved critical or high issues. This is **not** a claim of
production security or public deployability — the server has no authentication
and is designed for localhost use.

## What S11 changed

1. **S11-A — independent audit** (`7d1e90a`, `docs/S11_INITIAL_AUDIT.md`):
   every reported S10 gate re-executed and matched; real-browser journeys;
   3 defects found. Repaired: flaky identification test, History run-count
   format. Recorded: ad-hoc motion, 589 kB main chunk, no stage transitions.
2. **S11-B — HCI** (`5074e2a`, `docs/S11_HCI_USABILITY_REVIEW.md`,
   `docs/S11_INTERACTION_AND_MOTION_SYSTEM.md`): unsaved causal drafts now
   survive navigation (regression-tested, live-verified); motion token system;
   quiet keyed stage transition with reduced-motion support; main chunk
   −31 % via route-level code splitting with labelled loading fallbacks; two
   cosmetic fixes.
3. **S11-C/D — verification** (this commit, `docs/S11_FINAL_VERIFICATION.md`):
   full gate green on the final tree; before/after evidence in
   `docs/screenshots/s11/`; security/accessibility/performance reviews written.

## Run instructions (unchanged)

```
.venv/Scripts/python -m app.main     # from the repository root's backend/ dir
# serves frontend/dist; or: cd frontend && npm run dev for development
cd frontend && npm run test          # vitest
cd frontend && npm run test:e2e      # builds, then 39 real-backend journeys
```

## Known limitations (all documented, none new to S11)

- Studies are not linked to stored runs (S10 design note).
- History/dossiers live in a bounded in-memory store with TTL; nothing
  persists across server restarts except exported downloads (by design).
- Non-estimation run kinds have metadata-only reproducibility manifests.
- Binary PDF export is absent by design; printable HTML is the document path.
- DAG canvas node *positioning* remains pointer-centric (keyboard edge method
  exists); no screen-reader session was conducted.
- Several stage-scoped style sheets keep their own long-form animation
  durations; converging them onto the S11 motion tokens is future polish.
- Backend untouched in S11; next natural stage could link studies to runs.

## Defects found → resolved in S11 (summary)

| # | Severity | Defect | Resolution |
|---|---|---|---|
| 1 | MEDIUM | Flaky identification unit test (~1-in-N runs) | Awaited assertion; stable in all reruns |
| 2 | HIGH-value | Unsaved causal drafts destroyed by navigation | Draft provider above route switch + regression test |
| 3 | LOW | "1.000 run" count format | Integer formatter |
| 4 | MEDIUM | 589 kB main chunk | Route-level code splitting → 405 kB |
| 5 | MEDIUM | Ad-hoc motion/no transitions | Motion tokens + stage transition |
| 6 | LOW | CTA wrap alignment; scrollbar overlap | CSS fixes |
| 7 | — | S7 journey raced lazy Data chunk | Test helper waits for content |

## Git state

- Untracked scratch preserved untouched (`_s9b_*` logs, `import requests.txt`,
  audit scripts, screenshot `_preview/` dirs) and `stash@{0}` (S3 checkpoint).
- Regenerated journey screenshots (byte-noise from the verification runs) are
  committed with the S11-D checkpoint together with the new `s11/` set.
