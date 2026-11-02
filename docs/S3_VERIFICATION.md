# S3 verification — Study/data foundation

Run on 2026-11-02 against the production build served by the local backend
(`SPLITSCOPE_PORT=8300`), on branch `v2-premium-visual-foundation`.
Windows, Python 3.13 venv at the repository root, Node 24.

**Verdict: PASS.** Every gate below was executed on the final state of the
code; nothing was skipped, and no number on this page is projected.

## 1. Gates

| Gate | Command | Result |
| --- | --- | --- |
| Backend tests (incl. 34 new research tests) | `cd backend && ../.venv/Scripts/python -m pytest -q` | **252 passed** (baseline 218 + 34) |
| Frontend typecheck | `cd frontend && npm run typecheck` | exit 0 |
| Frontend lint (zero warnings enforced) | `cd frontend && npm run lint` | exit 0 |
| Frontend unit tests | `cd frontend && npm run test` | **70 passed** (6 files) |
| Production build | `cd frontend && npm run build` | exit 0 — 79.35 kB CSS / 368.86 kB JS |
| Playwright E2E (4 pre-existing journeys + 1 new S3 journey) | `SPLITSCOPE_E2E_PORT=8207 npx playwright test` | **5 passed** |
| Synthetic oracle harness (V1 preservation) | `python ../scripts/evaluate_synthetic.py` | **41 cases / 61 checks — 0 failed, exit 0** |
| S3 visual + behavioural capture | `node scripts/capture-s3-screenshots.mjs` | **19/19 checks passed** (output in §4) |

The S3 E2E journey (`e2e/s3-study.spec.ts`) exercises the real backend with no
mocks: loads the bundled demo, saves a Study Card (revision 1, 5/5 fields),
triggers a real `future_only × predictor` conflict in the dictionary and watches
the save get refused, saves the corrected map, reads the computed profile,
verifies the SHA-256 fingerprint, exports the manifest to disk through the API,
imports it back through the file input, applies the metadata and confirms the
round trip, then runs the original audit with the derived roles.

## 2. Defects found during verification and fixed

1. **Demo-seeded studies could not save their role map.** Seeding copied the
   demo manifest's role assignments but dropped its declared
   `split_train_value`/`split_test_value`, and a `put_roles` request that
   omitted the labels overwrote the stored ones with `None`. Any first save on
   a demo dataset failed with `audit_missing_split_values`. Fixed in
   `backend/app/research/studies.py` (seed labels on create) and
   `backend/app/api/routes_research.py` (omitted labels keep the stored ones).
   Regression test: `test_demo_seeded_study_carries_the_declared_split_labels`.
2. **Profile examples repeated one label.** A boolean column showed
   "no · no · no" because examples were the first rows in file order. Examples
   are now distinct values in first-appearance order
   (`backend/app/research/profiling.py`); high-cardinality columns are
   unchanged. Regression test:
   `test_profile_examples_are_distinct_values_in_file_order`.
3. **S3 E2E journey could not reach the demo Load button.** The chooser is a
   collapsed disclosure on the Start screen; the spec now opens it first
   (`frontend/e2e/s3-study.spec.ts`).
4. **Mobile/tablet full-page captures showed blank sections.** The landing
   reveals sections through IntersectionObserver; the capture now performs the
   scroll pass before full-page screenshots
   (`frontend/scripts/capture-s3-screenshots.mjs`). Verified in-browser that
   real scrolling reveals everything at 390×844.

Also corrected during verification: the landing's "Verified on this build"
proof counters (218→252 backend tests, 4→5 browser journeys) so the page
continues to state only verified facts.

## 3. Interaction verification (real browser, Chromium)

Driven with Playwright against the production build:

- **Hero phases**: clicking each rail step sets `data-phase` to
  `forming|scanning|discovery|evidence`; Replay returns to `forming`; the
  sequence advances on its own afterwards (asserted by the capture script).
- **Inspect pair**: `aria-pressed` toggles `false → true` on click.
- **Phase rail**: 4 buttons, `aria-current` on the active step, first Tab stop
  reaches `01 Registers`; the readout title is an `aria-live="polite"` region.
- **Reduced motion**: scanner `display: none`, scene pinned to the `evidence`
  still frame, implicated pair present (2 plates).
- **Study Card**: fields save as revision 1 with a 5/5 completeness counter;
  nothing is auto-filled (warnings list every missing required field).
- **Dictionary**: computed columns are read-only; the role editor refuses the
  `future_only × predictor` conflict with the server's own message and keeps
  the previous map; the corrected map saves.
- **Profile**: 240 rows × 8 columns with ranges/medians matching the demo's
  documented generator; no fabricated numbers.
- **Provenance**: dataset SHA-256 (64 hex), schema fingerprint, row-ID scheme;
  manifest export → import → Match → apply restores the card.

## 4. Capture script output (final run)

```
 * hero phase forming: forming
 * hero phase scanning: scanning
 * hero phase discovery: discovery
 * hero phase evidence: evidence
 * replay returns to the first phase
 * the sequence advances on its own
 * landing overflow at 1440: 0px
 * no console or page errors on landing
 * landing overflow at 1920: 0px
 * landing overflow at 768: 0px
 * no errors at 768
 * landing overflow at 390: 0px
 * no errors at 390
 * reduced motion hides the scanner: none
 * reduced motion shows the evidence frame: evidence
 * reduced motion keeps the implicated pair: 2 plates
 * manifest shows a sha256: c4992126471b…
 * study workspace overflow: 0px
 * no console errors in the study workspace

All S3 capture checks passed.
```

## 5. Evidence

Screenshots in `docs/screenshots/s3/` (all re-captured on the final build):
hero phases `s3-hero-{forming,scanning,discovery,evidence}.png`,
`s3-hero-reduced-motion.png`, landing at 1440/1920/768/390
(`s3-landing-*.png`), and the four study tabs
(`s3-study-{card,dictionary,profile,provenance}.png`).

## 6. Known limitations

See `docs/S3_HANDOFF.md` (§ Known gaps): Visual Explorer, Model Lab and Causal
Lab do not exist and are not advertised; TSV/SPSS ingest unchanged; one study
per dataset; profiling recomputed per request; manifest `checks_run` fills only
when an audit binds to it. The hero is a labelled illustrative fixture, not a
computed result.

## 7. Repository notes

- Interim scratch scripts from the interrupted session
  (`scripts/_patch_s3_hero.py`, `frontend/scripts/_s3_preview.mjs`,
  `frontend/scripts/_s3_qa.mjs`) are superseded by
  `capture-s3-screenshots.mjs`; they remain on disk but are not committed.
- The pre-existing stray `import requests.txt` remains untracked, untouched.
