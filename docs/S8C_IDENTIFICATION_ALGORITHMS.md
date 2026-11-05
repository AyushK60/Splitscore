# S8C identification algorithms

Implementation notes for the three engines introduced in S8C. All live in
`backend/app/causal/` and are independent of the schema layer so the test
suite can drive them with hand-built graphs.

## 1. d-separation — Bayes-ball reachability

* Module: `app/causal/d_separation.py`, contract version `1.0.0`.
* Algorithm: the linear-time reachability formulation of the Bayes-ball walk
  (Koller & Friedman, *Probabilistic Graphical Models*, 2009, Algorithm 3.1,
  "Reachable").
* Two phases: (1) collect Z and all ancestors of Z (the "activated" set — a
  collider passes a trail exactly when it, or one of its descendants, is
  conditioned on); (2) walk (node, direction) states from X, tracking whether
  the trail arrived from a child (`up`) or a parent (`down`). Y is reachable
  iff an active trail exists, i.e. X and Y are d-connected.
* **Complexity:** O(|V| + |E|) time and space per query. With the S8A schema
  limits (60 nodes, 240 edges) a query is microseconds; no search bounds are
  needed for d-separation itself.
* There is **no path enumeration** and **no undirected-connectivity
  shortcut** — direction memory plus the ancestor set is what makes colliders
  and collider descendants exact.
* Query validation (all structured, none silent): unknown nodes, identical
  endpoints, conditioning containing an endpoint. Repeated conditioning ids
  are deduplicated deterministically (set semantics make the answer
  identical).

### Independent verification

The test suite (`tests/test_causal_d_separation.py`) contains a
**moralization-based oracle** implemented from scratch inside the test file
(ancestral graph → moralization → undirected separation; Lauritzen et al.
1990) sharing no code with the engine. Both are compared over:

* **Every labelled DAG on 4 nodes** — 543 graphs (OEIS A003024), every pair,
  every conditioning subset: **13,032 exhaustive queries**;
* seeded random DAGs on 5 and 6 nodes across density 0.15–0.7, hundreds more
  queries;
* hand-written known-answer fixtures (chain, fork, collider, collider
  descendant, M-bias, butterfly bias, disconnected pairs, direct edges,
  query errors).

The two algorithms fail in different ways by construction, so agreement is
real evidence, not self-consistency.

## 2. Backdoor evaluation — `app/causal/adjustment.py`

`evaluate_adjustment_set(dag, x, y, z, observed)` reports **all** violations
at once (never first-failure-wins):

| Code | Condition |
|---|---|
| `unknown_variable` | id not a node of the graph |
| `adjustment_contains_scope` | Z contains X or Y |
| `unobserved_variable` | member declared unobserved — nothing could ever be conditioned on |
| `post_treatment_variable` | member is a descendant of X in the original graph |
| `open_backdoor_path` | d-separation fails in the backdoor graph |

When the open-path violation fires, up to 50 backdoor paths are enumerated
over the *undirected skeleton of the backdoor graph* (a backdoor path begins
with an edge **into** X, so walking only directed children would miss every
one) and filtered to the still-active ones via a per-path d-separation
restatement — for *explanation only*; the verdict always comes from the exact
reachability test. Hitting the listing bound sets `path_listing_bounded`.

## 3. Adjustment-set search — bounds and honesty

`search_adjustment_sets(dag, x, y, observed)`:

1. **Empty set first** — cheapest possible answer; returned immediately when
   valid (verified, inclusion-minimal by definition).
2. **Exhaustive enumeration** when the eligible observed candidate count
   `k ≤ MAX_EXHAUSTIVE_CANDIDATES = 14`: subsets enumerated by
   (cardinality, lexicographic) order; a candidate is kept only when no
   already-accepted smaller set is its subset, which guarantees every reported
   set is inclusion-minimal and every minimal set is reported.
3. **Greedy candidates** when `k > 14` (2^k explodes): documented starting
   points — the canonical `Pa(X) ∪ Pa(Y)` observed non-forbidden set, then the
   full eligible set — each verified, then reduced by deterministic greedy
   descent (each removal re-verified). Every reported set is verified and
   inclusion-minimal by construction, but the list is **not exhaustive**.
4. **Bounds**: `MAX_CANDIDATE_SETS = 200 000` evaluations and
   `MAX_SEARCH_SECONDS = 10` wall clock. Any truncation — or the skipped
   enumeration in strategy 3 — flips the result to
   `search_status="incomplete"` with an explicit reason. "No set exists" is
   claimed only when the enumeration finished: status `complete` with an
   empty list carries a fixed caveat stating this is a backdoor-criterion
   statement only.

Determinism: identical graphs yield identical result order (sorted
candidates, (size, lex) enumeration).

## 4. Identification status — `app/causal/identification.py`

`identify_backdoor(spec, treatment, outcome, method)` composes the pipeline:
scope validation → measured-scope check → search → status mapping → rule-based
explanations → fixed caveats. The scope pair defaults to the graph's saved
analysis scope and can be overridden per request (both must be distinct nodes
of the graph; the measured check refuses unobserved scope pairs with
`missing_dataset_variables`).

Routes (`app/api/routes_causal_identification.py`) re-validate the stored spec
against the dataset currently in memory before any computation, run entirely
read-only (verified by a dedicated test that asserts revision and fingerprint
are unchanged after all four endpoints), and return the single structured
error envelope for unanswerable queries.

## 5. Known limitations

* d-separation assumes the payload is a DAG; cycles are impossible in stored
  graphs (S8A rejects them) and the `DAG` container re-checks endpoints,
  self-loops and duplicates.
* The greedy strategy (strategy 3) finds *a* minimal set, not all of them;
  the response labels this honestly rather than approximating exhaustiveness.
* Backdoor path listing for explanations is capped at 50 paths (disclosed via
  `path_listing_bounded`).
* No front-door / IV / generalised-adjustment logic exists, even as a stub.
