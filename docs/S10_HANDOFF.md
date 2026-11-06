# S10 Handoff

**Status: COMPLETE.** The integrated Research Dossier, experiment history,
reproducibility infrastructure, methodology generation and publication-ready
exports are implemented, verified and committed on
`v2-premium-visual-foundation`.

## Commit plan (as made)

1. `a3e5fce` — S9C independent audit: PASS; whisker repair, flaky-test fix,
   19-test independent verification suite, audit docs.
2. `28a6a7b` — S10-A: research run history and reproducibility manifests
   (backend projection + routes, History stage, 6+4 tests).
3. `87d4832` — S10-B: integrated academic dossier (schema 1.1.0, seven new
   server-authored sections, methodology generator, Report Studio sources,
   renderers, 9+5 tests).
4. S10-C commit — DAG publication figure, S10 journeys, remaining docs
   (this checkpoint).
5. Final verification commit — STATUS/blueprint updates and the handoff.

## What an S11 auditor should check first

1. **The gate history is honest.** Every verification number in
   `S9C_FINAL_VERIFICATION.md` and `S10_FINAL_VERIFICATION.md` was executed
   in its session; re-run the matrix and expect the same outcomes modulo
   timing.
2. **The dossier cannot lie.** Try: select an estimation run, mutate the
   dataset bytes, regenerate → HTTP 422. Try a foreign run → 404. Try a
   mismatched kind → 422. Try editing the graph after estimation → the run
   stales in history and the Report Studio refuses the stale dossier source.
3. **The manifests are verifiable.** Recompute `canonical_json_sha256` from
   any returned manifest (sorted keys, compact separators, no integrity
   block) — `test_manifest_is_metadata_only_with_verifiable_integrity_hash`
   does exactly this.
4. **Nothing persists.** Restart the server: all history, runs and manifests
   vanish; only exported downloads remain. This is the documented design,
   not a bug.
5. **Responsive QA.** The S10 additions reuse existing grids; the journeys
   capture 1440-wide screenshots into `docs/screenshots/s10/`.

## Known limitations (deliberate, documented)

1. Studies are still not linked to stored runs — every history entry and
   manifest carries the explicit note. Linking them is the natural next
   stage if the product wants study-scoped histories.
2. Non-estimation run kinds (audit/comparison/model) predate structured
   reproducibility capture; their manifests say so rather than fabricating
   versions/seeds.
3. The dossier's subgroup/robustness/what-if sections take **one** run each
   (the first selected of that kind). Multiple-run comparison panels were
   deliberately out of scope for S10 to keep one-figure-per-screen and
   bounded payloads.
4. Binary PDF export remains absent by design; printable HTML is the
   document path.

## Environment / runbook

- Backend: `.venv/Scripts/python -m app.main` (serves `frontend/dist`).
- Playwright requires the project venv on PATH
  (`export PATH="/e/Splitscore V2/.venv/Scripts:$PATH"`).
- Full gate = backend pytest, `scripts/evaluate_synthetic.py`, frontend
  `vitest`/`tsc`/`eslint`/`build`, `npx playwright test`.

## Preserved, deliberately untracked

`_s9b_*.log`, `_s9b_compare.json`, `import requests.txt`,
`scripts/_patch_s3_hero.py`, `scripts/_audit_repro_*.py`,
`docs/screenshots/*/_preview/` remain untouched session scratch.
