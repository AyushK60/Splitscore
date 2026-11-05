# S8C handoff

**Status: COMPLETE for the S8C exit gate.**
**Branch:** `v2-premium-visual-foundation` · **Starting HEAD:** `15e5df3` (S8B) ·
**Implementation commit:** the single commit that adds the S8C files (hash in
the final response and `git log`).

## What shipped

* **Exact d-separation engine** (`causal/d_separation.py`) — Bayes-ball
  reachability (Koller & Friedman Alg. 3.1), O(V+E), colliders and collider
  descendants exact; cross-checked against an independent moralization oracle
  over all 543 labelled 4-node DAGs (13,032 exhaustive queries) plus seeded
  5/6-node random DAGs. NetworkX deliberately not used (not in the pinned
  environment).
* **Classical backdoor evaluation** (`causal/adjustment.py`) — all violations
  reported at once; open backdoor paths enumerated for explanation only;
  `without_outgoing_from` nails the remove-outgoing (not remove-incoming)
  distinction.
* **Bounded, honest adjustment search** — deterministic (size, lex)
  enumeration to inclusion-minimal sets under 14 eligible candidates; verified
  greedy candidates above; candidate/time bounds; truncation always reports
  `search_incomplete`, never a false "no set exists".
* **Identification status + rule-based explanations** (`causal/identification.py`)
  — seven statuses; explanations generated from graph structure only, no LLM,
  no data; backdoor failure explicitly qualified as backdoor-only.
* **Four read-only API routes** (`api/routes_causal_identification.py`),
  registered in `main.py`; provenance fingerprint in every payload; no
  mutation (test-pinned); dataset expiry/cross-dataset rules inherited from
  S8A.
* **Identification mode in the Causal Lab** — `Authoring | Identification`
  segmented switch; scope selects; run button; suggested inclusion-minimal
  sets; custom-set tester with structured verdicts; d-separation probe;
  explanation accordion; caveats; on-canvas copper highlight for the tested
  set + legend; scientific-signature staleness (drags never stale, structural
  edits always stale, save gate for dirty drafts).
* 48 new backend tests + 9 new frontend unit tests + 4 new real-backend
  Playwright journeys; 8 reviewed screenshots; one visual defect found and
  fixed (global button hover overriding the selected mode tab).

## Not done (by design)

* No effect estimation of any kind (ATE/ATT, propensity, matching, doubly
  robust, bootstrap, mediation, counterfactuals) — S9 territory.
* No front-door / instrumental-variable / generalised adjustment / do-calculus
  — a backdoor failure is never presented as general non-identifiability.
* No automatic causal discovery; no LLM-generated reasoning anywhere.
* Identification runs only against **saved** graphs (explicit save gate) —
  deliberate, per "prefer explicit identification runs".

## Known limitations

* Greedy search (candidates > 14) yields verified minimal *examples*, not the
  complete minimal-set list; the payload says so.
* d-separation cross-checks exhaustive only to 4 nodes; 5/6-node coverage is
  seeded-random.
* Chromium-only browser runs (unchanged convention).
* The frontend staleness signature is a client-side canonical JSON (edges,
  scope, observed status); the authoritative check remains the backend
  fingerprint echoed in every response.

## S9 readiness

**Ready.** S9 (numerical estimation) can build directly on:

* verified, exact identification with inclusion-minimal admissible sets
  (`search_adjustment_sets` results are safe to consume as estimation
  preconditions);
* the provenance block (graph id, revision, fingerprint) that every
  identification payload carries — an estimation run should pin the same
  fingerprint and refuse to proceed on drift;
* the dataset-scoped store rules and structured error envelope, unchanged.

S9 must add: exchangeability/positivity assessment surfaces, effect estimation
with its own numerical oracle tests, and honest confidence-interval machinery.
Nothing in S8C needs to be rewritten for that.

## Git

* Branch: `v2-premium-visual-foundation`
* Single implementation commit containing only the S8C files; pre-existing
  untracked scratch files (`docs/screenshots/s3/_preview/`,
  `docs/screenshots/s5/_preview/`, `import requests.txt`,
  `scripts/_patch_s3_hero.py`) and the S3 stash untouched.
