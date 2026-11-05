# S8A scientific contract

This document states precisely what the S8A causal foundation does, what it
does **not** establish, and which claims the application is and is not entitled
to make. It is the contract every later stage (S8B editor, S8C identification)
must preserve.

## 1. What graph validation establishes

A passing validation establishes **only** that:

* the payload parses as schema `1.0.0` of the causal-graph contract;
* node identifiers are unique and every edge endpoint names a defined node;
* there are no self-loops, duplicate directed edges, or directed cycles;
* every node anchored to a dataset column names a column that exists in the
  dataset the graph is bound to;
* the analysis scope, when given, names two distinct defined nodes.

That is a statement about the *internal form of the user's assumption*, not
about the world, the data, or the truth of any edge.

## 2. What graph validation does not establish

* **No causal effect is estimated.** S8A computes no ATE, ATT, CATE,
  counterfactual, mediation effect, or confidence interval. None of these
  numbers exist anywhere in the code.
* **No edge is evidence.** Edges are recorded assumptions. Nothing in S8A
  infers a direction or an arrow from correlation, and no correlation from the
  dataset is consulted during validation.
* **A valid DAG is not a true DAG.** Validation cannot detect a missing
  confounder, a reversed edge, or a wrong direction; it can only reject
  internally inconsistent structure.
* **Structure-derived labels are conditional.** `is_collider`,
  `ancestors`, `descendants` and on-path status are true *of the drawn graph*.
  They describe the user's assumption, not a property the data exhibited.
* **Conceptual annotations are not proof.** A node the user labels `mediator`,
  `treatment` or `outcome` is an annotation. The engine reports contradictions
  between annotations and drawn structure as warnings (`declared_role_unsupported`,
  `declared_kind_disagrees_with_scope`) and never resolves them silently in
  either direction.

## 3. Assumptions and their states

Assumptions are recorded per graph with a category (temporal ordering,
hypothesised causal relationships, unmeasured confounding, consistency,
exchangeability, positivity, selection/sampling, measurement limitations,
target population) and a user-chosen status:

| Status | Meaning |
|---|---|
| `declared` | Asserted by the user. **Not verified** — the state is descriptive, not evidential. |
| `not_assessed` | Recorded; the user has not judged it. |
| `flagged_for_review` | The user marks it as doubtful. |
| `unsupported` | The user judges it unsupported by available information. |

There is deliberately **no** `verified` state and no path that promotes a
status automatically. A checkbox or recorded assumption is never presented as
empirical proof; the API echoes the stored status verbatim.

Scientific warnings are issued for missing assumption rationales and for a
missing target population, because these omissions weaken the study's
documentation. They are warnings, never errors: an incomplete dossier is a
study the user is still writing, not an invalid graph.

## 4. Warning catalogue (all non-blocking)

| Code | Meaning |
|---|---|
| `analysis_incomplete` | Treatment or outcome not yet selected. |
| `no_directed_path` | The assumed structure implies no causal effect of the treatment on the outcome. May be intentional. |
| `isolated_node` | A node participates in no edge. |
| `unobserved_variable_present` | A declared-unobserved variable cannot be checked against data. |
| `edge_missing_rationale` | An assumed edge lacks a written justification. |
| `assumption_missing_rationale` | A recorded assumption lacks a written justification. |
| `no_target_population` | The intended target population is undocumented. |
| `declared_role_unsupported` | A conceptual role contradicts the drawn structure. |
| `declared_kind_disagrees_with_scope` | Node annotations disagree with the analysis scope. |
| `unobserved_kind_marked_observed` | The `unobserved` role is used while `observed` is true. |
| `dataset_schema_drift` | The graph was created against a different version of the dataset than the one currently in memory. |
| `empty_graph` | No nodes yet. |

## 5. Error catalogue (all blocking)

`unsupported_schema_version`, `duplicate_node_id`, `self_loop`,
`edge_endpoint_missing`, `duplicate_edge`, `directed_cycle`, `unknown_column`,
`analysis_node_missing`, `analysis_same_node`, `duplicate_assumption_id`.
An error means the payload is refused and nothing is stored or mutated.

## 6. Absolute boundaries of this stage

S8A contains **no** implementation — and no stub producing output — of: ATE/ATT
estimation, propensity weighting, doubly robust estimation, counterfactual
prediction, automated causal discovery, backdoor identification, d-separation,
adjustment-set evaluation, or mediation analysis. Any such capability the
frontend might display before S8C would be fabrication, and the API surface
makes it impossible: there is no route it could be fetched from.

Intended future interfaces are documented (`S8A_ARCHITECTURE.md` §5) but not
faked.

## 7. Honesty of the numbers that do exist

The fingerprint (`spec_fingerprint_sha256`) is a deterministic hash of the
canonical scientific content — it identifies the graph, it does not validate
it. `revision` counts accepted updates. `validation.ok` means exactly §1.
Path enumeration is capped at 1000 directed paths and discloses when the cap
was reached (`path_enumeration_bounded`), so a truncated enumeration is never
presented as exhaustive.
