# S3 handoff

## State

S3 delivered and verified: the observatory hero and identity calibration, F01
(Study Card and provenance), F02 (profiling, data dictionary, research roles) and
the foundational portion of F19 (dataset/schema fingerprints and the
reproducibility manifest). S4 has not been started.

Result details and exact command output live in `docs/S3_VERIFICATION.md`.
Fixes made during the verification pass: a demo-seeded study now carries the
manifest's declared split labels (a first save of the role map no longer fails
on `audit_missing_split_values`), profile examples are distinct values in file
order (a boolean no longer reads "no · no · no"), the S3 E2E journey opens the
demo disclosure before clicking Load, and the mobile/tablet full-page captures
scroll first so scroll-reveal sections are visible.

## Where things are

```
backend/app/research/
  schema.py       Study Card model, field list, role vocabulary, conflict matrix,
                  build_role_map (research roles -> V1 ColumnRoles)
  studies.py      in-memory StudyRegistry, payloads, role application, seeding
  profiling.py    computed dataset/column profile
  provenance.py   schema fingerprint, manifest build, manifest validation
backend/app/api/routes_research.py
                  /api/datasets/{id}/{study,roles,dictionary,profile,manifest...}
backend/tests/test_research.py
                  34 tests: card, roles, profiling, provenance
frontend/src/views/StudyView.tsx
frontend/src/components/research/{StudyCardEditor,DataDictionary,DataProfile,ProvenancePanel}.tsx
frontend/src/styles/research.css
frontend/src/lib/useHeroSequence.ts, components/HeroField.tsx, styles/s3.css
frontend/scripts/capture-s3-screenshots.mjs
frontend/e2e/s3-study.spec.ts
docs/screenshots/s3/*.png
```

## Decisions a future stage must respect

1. **One authoritative role map.** The research map lives in the study record and
   yields `derived_roles`; the audit consumes that object. Do not introduce a
   second editable role state in a new screen.
2. **Declared ≠ computed ≠ inferred.** Study fields are declared and never
   auto-filled. Profiles are computed. `inferred` stays empty until a feature
   deliberately produces suggestions with visible provenance.
3. **Manifests carry identity, not data.** No rows, no cell values, no secrets.
   Any S4 artifact should reference a manifest rather than embed data.
4. **A mismatch is not an import.** `dataset_mismatch` and `schema_mismatch` must
   keep blocking application.
5. **The bridge roles.** `future_only`, `sensitive` and `excluded` exist so later
   feature-availability and fairness work has a declared vocabulary; they must
   not become name-based detectors.

## Known gaps (next stages)

- Visual Explorer (F08), Model Lab (F09–F11), Causal Lab (F12–F16), experiment
  history (F20) and the dossier (F21) are not built and are not linked as if
  they were.
- Pattern CSV ingest is unchanged; TSV is accepted by suffix but not yet profiled
  separately for delimiter diagnostics. XLSX and SPSS are not supported.
- Only one study per dataset; no study version history beyond a revision counter.
- Profiling is recomputed per request (bounded input, no cache).
- The manifest records `checks_run: []` until an audit run is bound to it.

## Recommended S4 entry point

Start with the **Visual Explorer (F08)** on top of the S3 data foundation:

1. Read `backend/app/research/profiling.py` and reuse its type detection and
   conventions so charts label axes with the same missing/parse rules.
2. Add `backend/app/explore/{specs,aggregates,sampling}.py` returning bounded,
   deterministic series keyed to immutable row ids.
3. Keep the study role map as the filter vocabulary (target/predictors/entity),
   and expose "sampled N of M" plus the seed with every series.
4. Verify cross-filtering against the same row ids the audit evidence uses, so a
   brushed selection can open the corresponding finding.

Do not add a chart that renders fabricated values, and do not advertise Model
Lab or Causal Lab controls before those engines exist.

## Running it locally

```powershell
# from the repository root
cd backend
$env:SPLITSCOPE_PORT = "8000"
..\.venv\Scripts\python.exe -m app.main
# http://127.0.0.1:8000/            landing
# http://127.0.0.1:8000/#/study     study workspace
```

```powershell
cd frontend
npm run dev        # hot reload against the backend
npm run test       # component tests
npm run test:e2e   # browser journeys (SPLITSCOPE_E2E_PORT if 8123 is taken)
```
