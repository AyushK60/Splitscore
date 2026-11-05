# S8B handoff

**Status: COMPLETE for the S8B exit gate.**
**Branch:** `v2-premium-visual-foundation` · **Starting HEAD:** `1f44c7f` (S8A) ·
**Implementation commit:** the commit that adds the S8B files (hash in the final
response and `git log`).

The Causal Lab is a real, interactive, scientifically bounded DAG editor on top
of the S8A backend. S0–S7 surfaces are unchanged visually and behaviourally;
all 22 prior browser journeys still pass.

## What shipped

* `#/causal` route (nav step 7, lazy-loaded chunk, CSS eager) — canvas, rail,
  contextual inspector, toolbar, empty state, teaching examples.
* Typed S8A client (`causalApi`) and contract types; all eight endpoints used.
* Draft/saved/validation state separation with dirty indicator, explicit Save,
  structured 422 rendering that never loses edits, undo/redo, keyboard
  authoring and deletion, import/export.
* 32 new unit tests + 3 real-backend Playwright journeys + 8 reproducible
  screenshots. Full-suite results: `docs/S8B_TEST_RESULTS.md`.
* Visual pass with defect log: `docs/S8B_VISUAL_VERIFICATION.md`.
* One pre-existing defect fixed for all views: the mobile context-band stretch
  (`app.css`, `.app-crumb__next` flex basis in the ≤760 px column layout).

## Not done (by design)

* No identification, adjustment sets, d-separation, effects or any causal
  numbers anywhere in the UI. The lab is authoring + validation only (S8C).
* No autosave (explicit Save, per brief).
* No Firefox/WebKit runs; Chromium only (unchanged project convention).
* Graph deletion of another dataset's graphs remains impossible by backend
  ownership rules; the UI exposes only "Delete current".

## Known limitations

* A browser reload intentionally returns to the dataset entry: datasets are
  session state, and a saved graph binds to that dataset instance. Restoring a
  saved graph is exercised by re-entering the route (the journey does this).
* The connect-by-handle pointer gesture works, but the inspector's connect
  select is the keyboard path; pointer edge drawing still creates edges
  through the same reducer/backend rules.
* Very wide graphs at tablet width may need a pan (auto-fit zoom floor keeps
  node text readable).

## S8C readiness

Ready. The lab always carries the backend's `validation.derived` structure for
the saved graph, and the analysis scope (one treatment, one outcome) is part of
every save. S8C can add an identification panel that consumes the same payload
without touching the authoring contracts. The `validation_scope_note` and
scope-footer text are the honesty contracts S8C must keep.

## Git

* Branch: `v2-premium-visual-foundation`
* Commit: single commit with only the S8B files listed in
  `S8B_IMPLEMENTATION.md` §6; pre-existing untracked scratch files and stashes
  untouched.
