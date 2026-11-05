# S8C scientific methodology

**Stage:** S8C — Scientific Causal Identification (d-separation, backdoor
criterion, adjustment-set reasoning)
**Branch:** `v2-premium-visual-foundation` · **Starting HEAD:** `15e5df3` (S8B)

This document states precisely what S8C does, what it does **not** establish,
and which claims the application is entitled to make after this stage. It
extends — and never weakens — the S8A scientific contract.

## 1. What S8C establishes

Given a **structurally valid, saved** causal graph (schema 1.0.0) and a
treatment/outcome pair, S8C answers questions *about the assumed graph alone*:

1. **Graphical independence.** Are two variables d-separated given a
   conditioning set? This says which conditional independences the *drawn
   structure implies*. It is never an empirically established independence in
   the dataset — no data is consulted, and every payload carries that scope
   note verbatim.
2. **Backdoor admissibility.** Does a proposed adjustment set satisfy the
   classical backdoor criterion (Pearl, *Causality* 2009, §3.3.1) for the
   *total* effect?
   1. Z excludes X and Y;
   2. no member of Z is a descendant of X **in the original graph**;
   3. Z d-separates X from Y in the **backdoor graph** — the graph with every
      edge directed **out of X** removed.
3. **Adjustment-set discovery.** Which observed sets satisfy the criterion,
   with **inclusion-minimal** results: no *proper subset* of a reported set is
   also sufficient. Minimal ≠ minimum-cardinality; several minimal sets of
   different sizes can exist and all are reported.

Passing the criterion establishes **graphical admissibility under the assumed
DAG only**. It is a licence to *estimate under these assumptions* — never
empirical proof, never a causal number.

## 2. What S8C does not establish

* **No causal effect is estimated.** No ATE/ATT/CATE, no propensity scores,
  no matching, no doubly robust estimation, no bootstrap intervals, no
  mediation effects, no counterfactual prediction. No such number exists
  anywhere in the code, and no endpoint can return one.
* **No edge is evidence.** Everything follows from the edges the user drew.
  A missing confounder, a reversed edge or a wrong direction silently changes
  the identification answer — the graph being wrong is not detectable from
  within.
* **A backdoor failure is not non-identifiability.** When no observed set
  satisfies the criterion, the response says so *for the classical backdoor
  criterion on this graph*. It does **not** claim the effect is unidentifiable
  by every method: front-door, instrumental variables, generalised adjustment
  and do-calculus are outside S8C and are never simulated.
* **Graphical independence ≠ dataset independence.** d-separation is reported
  with an explicit interpretation note; the UI repeats it.
* **Unobserved variables are never measurable.** A declared-unobserved node is
  excluded from candidates, refused as an adjustment member with a structured
  violation, and never silently swapped for a proxy.
* **A truncated search is never exhaustive.** Any bound (candidate count,
  cardinality ceiling, wall clock) that stops the enumeration flips the result
  to `search_incomplete`; "no valid set exists" is claimed only after a search
  that ran to completion.

## 3. The backdoor graph and the classic confusion

Condition 3 removes the edges **leaving** the treatment. Removing the edges
*entering* the treatment would instead represent the intervention
`do(X)` — a different graph with a different meaning. Getting this backwards
keeps spurious backdoor paths "blocked" and destroys real causal information.
`DAG.without_outgoing_from` (in `app/causal/d_separation.py`) is the single
place the operation exists, is named for what it does, and is unit-tested
against the distinction (`test_backdoor_graph_keeps_incoming_and_drops_outgoing_edges`).

Treatment descendants are computed on the **original** graph, never the
backdoor graph.

## 4. Identification statuses

| Status | Meaning |
|---|---|
| `backdoor_adjustment_available` | A complete, untruncated search found ≥ 1 admissible observed set (possibly the empty set). |
| `no_eligible_backdoor_set` | The search ran to completion within all bounds and found none. Explicitly qualified as backdoor-only. |
| `search_incomplete` | A documented bound truncated the search; listed sets are verified, absence of further sets is not established. |
| `invalid_graph` | The stored graph no longer validates against the dataset in memory. |
| `invalid_scope` | Treatment/outcome missing, unknown, or identical. |
| `missing_dataset_variables` | Treatment or outcome is declared unobserved — estimation could never proceed on this dataset. |
| `unsupported_identification_method` | A method other than `backdoor` was requested; refused, never simulated. |

## 5. Explanations are rule-based

Every explanation rendered in the Causal Lab is generated server-side from
graph structure (roles, ancestors, descendants, collider status, observedness)
with explicit rules — no LLM, no dataset statistics, no correlation-derived
"insights". The current catalogue:

* `confounder_needs_adjustment` — observed common causes of X and Y.
* `mediator_not_adjusted` — why a mediator on a directed pathway must not be
  adjusted under the classical *total*-effect criterion.
* `post_treatment_forbidden` — other descendants of the treatment.
* `collider_caution` — colliders whose conditioning opens paths.
* `unobserved_confounding` — why an unmeasured common cause can defeat every
  measured adjustment set.
* `structure_not_truth` — always present: a graphically valid set is not a
  scientifically proven one.

## 6. Staleness contract

Identification results are tied to an exact **scientific signature** of the
draft (edges, analysis scope, per-node observed status — canonically sorted).
Layout drags, label edits and prose changes never invalidate a result; any
change to edges, scope or observed status marks every displayed result
visibly stale (`Results are stale` banner) and gates further runs behind a
save. Loading a different graph invalidates results outright. The backend
echoes `spec_fingerprint_sha256` in every response so a client can always
re-derive staleness from the authoritative hash.
