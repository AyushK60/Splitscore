# S8C test results

**Date:** 2026-11-06 · **Branch:** `v2-premium-visual-foundation` ·
**Starting HEAD:** `15e5df3` (S8B) · **Python:** 3.11.9 (repo venv `.venv`)
**Environment note:** NetworkX is **not** installed in the pinned environment;
per the S8C brief the engines are implemented in-house and cross-checked
against an independently written oracle rather than an external library.

## 1. Commands executed and actual results

| # | Command | Result |
|---|---|---|
| 1 | `.venv/Scripts/python -m pytest tests -q` (backend, from `backend/`) | **454 passed** (406 S8A/S8B baseline + 48 new S8C), 3 warnings (pre-existing deprecations), 13.6 s |
| 2 | `npx vitest run` (frontend, from `frontend/`) | **145 passed** (14 files; 136 baseline + 9 new S8C) |
| 3 | `npx tsc -p tsconfig.app.json --noEmit` | clean |
| 4 | `npm run lint` (ESLint flat config) | clean |
| 5 | `npm run build` (production build) | succeeds, 1.08 s |
| 6 | `npx playwright test` (Chromium, real backend, production build served by `python -m app.main`) | **29 passed** (25 baseline journeys + 4 new S8C journeys), 1.0 min |

Synthetic oracle evaluation: the S8C brief's "synthetic oracle" role is
fulfilled by the independent moralization oracle in
`tests/test_causal_d_separation.py` — **13,032 exhaustive engine-vs-oracle
queries** over every labelled DAG on 4 nodes (543 graphs; OEIS A003024),
plus seeded 5- and 6-node random DAGs at densities 0.15–0.7, plus
hand-derived known-answer checks of the oracle itself. All agree.

## 2. New backend tests (48)

`tests/test_causal_d_separation.py` (18 tests):

* Known answers: chain (X→M→Y), fork (X←Z→Y), collider (X→C←Y), collider
  descendant reopening, M-bias graph, butterfly-bias graph (chains, forks,
  colliders and collider-descendant activation in one graph), direct edges
  surviving conditioning, disconnected components, query error codes,
  conditioning deduplication, DAG container rejections (duplicates, self
  loops, missing endpoints), backdoor-graph edge semantics
  (`without_outgoing_from` keeps X's parents, drops X's children),
  reachability diagnostics.
* Oracle cross-checks: exhaustive 4-node sweep, seeded 5/6-node sweeps, and
  oracle self-checks against textbook answers.

`tests/test_causal_identification.py` (30 tests):

* **Brief cases 1–10**, each labelled in the test name:
  1. chain — empty set valid; M forbidden as post-treatment;
  2. fork — Z the unique minimal set;
  3. collider — empty set admissible; conditioning C refused (C is also a
     treatment descendant, so the post-treatment rule fires first; the pure
     open-path violation is covered in case 7);
  4. confounded effect — empty set insufficient, {Z} minimal, X→Y edge
     untouched;
  5. unobserved confounding — complete search, honest empty result, U never
     eligible, fixed "not unidentifiable by every method" caveat;
  6. post-treatment bias — M forbidden despite a naive regression's
     willingness;
  7. collider bias path — {C} opens the path; sets blocking at A or B remain
     valid even when they contain C;
  8. multiple confounders — {Z1, Z2} minimal, byte-identical deterministic
     re-run;
  9. search limits — 15 eligible candidates → `incomplete` with verified
     greedy sets and an explicit NOT-exhaustive reason;
  10. invalid queries — same-node scope, unknown scope node → structured
      refusals.
* Additional §7 requirements: treatment with no parents, disconnected pairs,
  all-violations-at-once reporting, inclusion-minimality verified directly
  (every proper subset of every reported set is re-tested and fails),
  bound reporting (max_candidates=1 → incomplete), identification status
  lifecycle, missing/unmeasured scope, unobserved-confounder honesty,
  unsupported method refusal, scope override.
* API level (real upload path, real registry, real envelope): provenance
  echo, structured d-separation query errors, all-violations rendering,
  honest unobserved search, identification status + explanations, unsupported
  method + scope-less graphs, **no-mutation guarantee** (revision +
  fingerprint unchanged after all four endpoints), cross-dataset 404, unknown
  id 404, eviction 410 with graph pruning, fingerprint rotation after a PUT.

## 3. New frontend tests (9 unit + 4 browser)

Unit (`tests/CausalIdentification.test.tsx`, mocked API boundary with
documented payload shapes; view/reducer logic real): mode switching, save
gate for dirty drafts, run + suggested sets, custom-set evaluation
(admissible + structured violations), d-separation probe, unobserved-
confounder honesty, staleness after a scientific edit and un-staleness after
restoring it, saving through the gate, explanation accordion behaviour.

Browser (`e2e/s8c-identification.spec.ts`, real backend, no mocks):

* **Journey A** — confounder identification: build confounded graph → save →
  identify → `backdoor_adjustment_available` with {support_tickets} →
  inspect set → on-canvas copper highlight on the real React Flow node +
  legend → explicit evaluation → d-separation probe on an isolated variable
  (`d-separated given nothing`).
* **Journey B** — M-structure collider: empty set correctly reported as the
  minimal set; conditioning on the collider refused with
  `open_backdoor_path`; hypothetical unobserved confounder added → honest
  `no_eligible_backdoor_set`, U never offered as a covariate, rule-based
  explanation rendered.
* **Journey C** — invalidation: layout drag does **not** mark results stale;
  adding a directed edge into the outcome does; save through the gate →
  rerun → the empty set is no longer admissible, verified sets replace it,
  staleness cleared.
* Responsive journey — tablet 768 and mobile 390 (no horizontal overflow,
  controls reachable).

All 25 prior journeys (S0–S8B: dataset, leakage, modelling, reporting,
causal authoring) still pass unchanged.

## 4. Coverage limits (documented, not hidden)

* The moralization oracle is itself tested against textbook answers before
  being trusted as a reference.
* Greedy (non-exhaustive) search is exercised by the 15-candidate fixture;
  exhaustive-vs-greedy parity is not proven beyond the reported sets being
  individually verified and inclusion-minimal by construction.
* d-separation cross-checks are exhaustive only up to 4 nodes; 5/6-node
  coverage is seeded-random, not exhaustive (29 281 labelled DAGs on 5 nodes).
* Playwright runs Chromium only (unchanged project convention; no
  Firefox/WebKit runs).
