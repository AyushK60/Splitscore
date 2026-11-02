# S5 handoff

## State

S5 delivered and verified in three checkpoints on
`v2-premium-visual-foundation`:

- `70ce5c2` **S5-A** — unified workspace identity, functional workspace entry,
  full-width responsive layout, chart legibility and containment fixes.
- `0c45cb6` **S5-B** — Integrity V2: availability ledger, proxy screen,
  identifier reuse, declared horizon, declared preprocessing fit boundary,
  session reuse, and the category risk scorecard (F04 + F06).
- `f08fab6` **S5-C** — evaluation plans (stratified CV, group CV, rolling
  origin with purge), split-comparison visuals, and the train/test similarity
  explorer with Pair Inspector (F05 + F07).

S5-D verification passed (see `docs/S5_VERIFICATION.md`); the final S5-D
documentation commit follows this file. **S6 has not been started.**

## Where things are

```
backend/app/audit/rules/{feature_availability,target_proxy,entity_memorization,
                          temporal_horizon,preprocessing_fit,validation_reuse}.py
                  six typed F04 rules; originals untouched
backend/app/audit/scorecard.py    F06 category scorecard (no numeric score)
backend/app/splits/plans.py       F05 evaluation plans + feasibility gates
backend/app/splits/comparison.py  fold-by-fold plan audits + aggregates
backend/app/explore/similarity.py F07 bounded Chebyshev pair service
backend/tests/test_integrity_v2.py        32 tests
backend/tests/test_plans_similarity.py    15 tests
frontend/src/views/OverviewView.tsx       S5 workspace entry (no 2nd landing)
frontend/src/components/RiskScorecard.tsx Results scorecard
frontend/src/components/SplitVisual.tsx   comparison visuals
frontend/src/components/explore/SimilarityExplorer.tsx  F07 tab + inspector
frontend/src/components/AuditConfigEditor.tsx  S5 declarations editor
docs/S5_*.md, docs/screenshots/s5/{before,after}
```

## Decisions a future stage must respect

1. **Declaration principle.** Availability, horizon and preprocessing fit are
   user declarations. Undeclared ⇒ NOT EVALUATED with the reason; never
   inferred, never a pass. S6 must not weaken this.
2. **No scores.** The scorecard is categorical by design. No 0–100 trust
   number, ever.
3. **Plans audit per fold.** A plan is not a split; its folds are audited
   through `run_audit` with exact stored row ids, bounded by
   `MAX_TOTAL_FOLDS = 20` per comparison.
4. **Similarity is screening.** The explorer shares SS-NEAR-001's method and
   its ban on calling near neighbours leakage; the row-bound sample is seeded
   and its scope sentence is carried verbatim.
5. **One selection engine** (S4 rule, still true): charts read/write
   `ExploreState`; the similarity tab highlights via `highlightedId`.
6. **Landing page is frozen** (owner-approved). The workbench token layer
   lives in `app.css` `:root` + `.rs`/`.we`/`.xw` scopes; the old S0–S2
   overrides are gone from `v2.css`.

## Known gaps (S6 candidates)

- Playwright specs for the similarity tab and plan flows (backend-tested +
  manually verified; browser specs are the natural next step).
- Violin plots, faceted distributions, time-axis distributions (F08
  optional items) remain unbuilt.
- Print/DPI controls and dossier integration (F22) remain open.
- The comparison view keeps the legacy textual table beside the new visuals;
  a future pass can retire or merge them.
- Causal Lab / Model Lab are still intentionally absent — no fake pages.

## Running it locally (Windows PowerShell)

```powershell
# from the repository root
cd backend
$env:SPLITSCOPE_PORT = "8000"
..\.venv\Scripts\python.exe -m app.main
# http://127.0.0.1:8000/            landing
# http://127.0.0.1:8000/#/overview  workspace entry
```

```powershell
cd frontend
npm run test        # component/unit tests (82)
npm run typecheck   # tsc
npm run lint        # eslint, zero warnings
npm run build       # production bundle served by the backend
$env:SPLITSCOPE_E2E_PORT = "8180"   # 8123 is held by another process on this machine
npx playwright test # 11 browser journeys (rebuilds dist first)
```

```powershell
# repository root
python scripts/evaluate_synthetic.py   # 41/41 cases, 61/61 checks
```

## Verification ledger

| Suite | Result |
|---|---|
| Backend pytest | 340 passed |
| Synthetic oracle | 41/41 cases, 61/61 checks, exit 0 |
| Frontend vitest | 82 passed |
| TypeScript / ESLint / build | clean |
| Playwright E2E | 11 passed |
| Browser journeys (§16) | 10/10 exercised, screenshots in `docs/screenshots/s5/after/` |
