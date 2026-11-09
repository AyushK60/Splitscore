"""Classical backdoor adjustment: evaluation, explanation and bounded search.

The criterion implemented (Pearl, *Causality*, 2009, §3.3.1): an adjustment
set Z qualifies for the *total* causal effect of treatment X on outcome Y in
DAG G when

1. Z contains neither X nor Y;
2. no member of Z is a descendant of X in G (the classical, stricter form -
   this forbids mediators and post-treatment colliders alike);
3. Z d-separates X from Y in the *backdoor graph* G_X̲ - the graph with every
   edge directed **out of** X removed. Removing edges *into* X would model an
   intervention do(X) and is a different graph with a different meaning; the
   confusion is a classic identification bug and this module's docstrings name
   it on purpose.

Passing the criterion establishes **graphical admissibility under the assumed
DAG only**. It is not empirical proof: the edges are assumptions, and no data
is consulted anywhere in this module.

Search bounds are explicit and disclosed. Whenever a bound truncates the
search the result is flagged ``search_status="incomplete"`` - a truncated
search is never reported as exhaustive, and "no set found" is never claimed
from an incomplete search.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from itertools import combinations

from app.causal.d_separation import DAG

#: Version of the adjustment engine contract, echoed in every payload.
ADJUSTMENT_VERSION = "1.0.0"

#: Above this many eligible candidates, exhaustive enumeration is skipped in
#: favour of verified greedy candidates (with an honest "incomplete" flag).
#: 2^14 = 16 384 subsets per level keeps worst-case work at a few million
#: d-separation checks *per cardinality level*, each O(|V|+|E|) on ≤60-node
#: graphs.
MAX_EXHAUSTIVE_CANDIDATES = 14

#: Hard cap on evaluated candidate sets per search, across all cardinalities.
MAX_CANDIDATE_SETS = 200_000

#: Wall-clock cap for one search, in seconds.
MAX_SEARCH_SECONDS = 10.0

#: Scope note carried verbatim in every adjustment payload.
ADJUSTMENT_SCOPE_NOTE = (
    "Backdoor admissibility is a property of the assumed graph: it means the "
    "drawn structure, taken as given, blocks every unblocked backdoor path. It "
    "is not empirical proof that the adjustment removes confounding, and no "
    "data is consulted. No causal effect is estimated."
)

VIOLATION_CODES = {
    "unknown_variable",
    "adjustment_contains_scope",
    "unobserved_variable",
    "post_treatment_variable",
    "open_backdoor_path",
}


@dataclass
class Violation:
    """One structured reason a proposed adjustment set fails the criterion."""

    code: str
    node_id: str | None
    message: str

    def to_payload(self) -> dict[str, object]:
        return {"code": self.code, "node_id": self.node_id, "message": self.message}


@dataclass
class AdjustmentEvaluation:
    """Verdict on one proposed adjustment set under the backdoor criterion."""

    treatment: str
    outcome: str
    adjustment_set: list[str]
    valid: bool
    violations: list[Violation] = field(default_factory=list)
    #: Backdoor paths still open when d-separation fails (bounded, for explanation).
    open_backdoor_paths: list[list[str]] = field(default_factory=list)
    #: True when the open-path listing hit the enumeration bound (diagnostic only).
    path_listing_bounded: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "treatment": self.treatment,
            "outcome": self.outcome,
            "adjustment_set": list(self.adjustment_set),
            "valid": self.valid,
            "violations": [v.to_payload() for v in self.violations],
            "open_backdoor_paths": [list(p) for p in self.open_backdoor_paths],
            "path_listing_bounded": self.path_listing_bounded,
            "interpretation": (
                "Every backdoor path from "
                f"'{self.treatment}' to '{self.outcome}' is blocked by this set under the "
                "assumed DAG, and no member is a descendant of the treatment."
                if self.valid
                else "This set does not satisfy the classical backdoor criterion under the "
                "assumed DAG; see the listed violations."
            ),
            "interpretation_note": ADJUSTMENT_SCOPE_NOTE,
        }


@dataclass
class AdjustmentSetCandidate:
    """One verified adjustment-set candidate, with its verification provenance."""

    variables: list[str]
    #: Every reported set has been verified against the criterion by exact
    #: d-separation; `verification` names how it was found.
    verification: str  # "verified" | "verified_greedy_minimised" | "verified_canonical_candidate"
    inclusion_minimal: bool | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "set": list(self.variables),
            "verification": self.verification,
            "inclusion_minimal": self.inclusion_minimal,
        }


@dataclass
class AdjustmentSearchResult:
    """Outcome of an adjustment-set search, honest about completeness."""

    treatment: str
    outcome: str
    status: str  # "complete" | "incomplete"
    minimal_sets: list[AdjustmentSetCandidate]
    forbidden_variables: list[str]
    eligible_candidates: list[str]
    candidates_considered: int = 0
    bounds: dict[str, object] = field(default_factory=dict)
    status_reason: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "treatment": self.treatment,
            "outcome": self.outcome,
            "search_status": self.status,
            "sets": [s.to_payload() for s in self.minimal_sets],
            "forbidden_variables": list(self.forbidden_variables),
            "eligible_candidates": list(self.eligible_candidates),
            "candidates_considered": self.candidates_considered,
            "bounds": dict(self.bounds),
            "interpretation_note": ADJUSTMENT_SCOPE_NOTE,
        }
        if self.status == "incomplete":
            payload["status_reason"] = self.status_reason or (
                "The candidate enumeration reached a documented bound before finishing. "
                "The listed sets are verified, but absence of further sets is NOT established."
            )
        if not self.minimal_sets and self.status == "complete":
            payload["status_reason"] = (
                "The enumeration finished within all bounds and found no observed set "
                "satisfying the classical backdoor criterion. This is a statement about "
                "the backdoor criterion on this assumed graph only: it does not prove the "
                "effect is unidentifiable by every method (front-door, instrumental "
                "variables and generalised adjustment are outside identification)."
            )
        return payload


class AdjustmentQueryError(ValueError):
    """The adjustment query itself is not answerable on the supplied graph."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def forbidden_for_adjustment(dag: DAG, treatment: str, outcome: str) -> list[str]:
    """Variables that may never enter the set: X, Y, and descendants of X.

    Descendants are computed on the *original* graph, not the backdoor graph.
    """
    excluded = {treatment, outcome} | dag.descendants_of(treatment)
    return sorted(excluded)


def eligible_candidates(
    dag: DAG,
    treatment: str,
    outcome: str,
    observed: set[str],
) -> list[str]:
    """Observed, non-forbidden variables eligible for consideration."""
    forbidden = set(forbidden_for_adjustment(dag, treatment, outcome))
    return sorted(node for node in dag.nodes if node in observed and node not in forbidden)


def _backdoor_paths(
    dag: DAG,
    treatment: str,
    outcome: str,
    *,
    max_paths: int = 50,
) -> tuple[list[list[str]], bool]:
    """Enumerate backdoor paths (X ← … Y), bounded, for explanation only.

    A backdoor path begins with an edge *into* the treatment, so the walk runs
    over the undirected skeleton of the backdoor graph (the graph with X's
    outgoing edges removed) - walking only directed children would miss every
    path that starts X ← …. The blocking verdict itself never comes from this
    listing; it is the exact d-separation test. Reaching the bound sets the
    disclosure flag.
    """
    backdoor = dag.without_outgoing_from(treatment)
    neighbours: dict[str, set[str]] = {node: set() for node in dag.nodes}
    for s, t in backdoor.edges:
        neighbours[s].add(t)
        neighbours[t].add(s)
    paths: list[list[str]] = []
    stack: list[tuple[str, list[str]]] = [(treatment, [treatment])]
    bounded = False
    while stack:
        node, path = stack.pop()
        for nxt in sorted(neighbours[node]):
            if nxt in path:
                continue
            if nxt == outcome:
                paths.append([*path, nxt])
                if len(paths) >= max_paths:
                    return paths, True
                continue
            stack.append((nxt, [*path, nxt]))
    return paths, bounded


def evaluate_adjustment_set(
    dag: DAG,
    treatment: str,
    outcome: str,
    adjustment: list[str],
    observed: set[str],
) -> AdjustmentEvaluation:
    """Classical backdoor evaluation of one proposed set, with structured reasons.

    Violations are reported all at once (not first-failure-wins) so the
    researcher sees every problem with their proposed set in one round trip.
    """
    known = set(dag.nodes)
    if treatment not in known or outcome not in known:
        raise AdjustmentQueryError(
            "unknown_scope_node",
            "The treatment and outcome must both be nodes of the graph.",
        )
    if treatment == outcome:
        raise AdjustmentQueryError(
            "same_node",
            "The treatment and the outcome must be distinct variables.",
        )

    # Deduplicate deterministically: a repeated id asks the same thing twice.
    proposed: list[str] = []
    for node in adjustment:
        if node not in proposed:
            proposed.append(node)

    violations: list[Violation] = []
    for node in proposed:
        if node not in known:
            violations.append(
                Violation(
                    "unknown_variable",
                    node,
                    f"'{node}' is not a node of this graph.",
                )
            )
            continue
        if node in (treatment, outcome):
            violations.append(
                Violation(
                    "adjustment_contains_scope",
                    node,
                    f"The adjustment set must not contain the treatment or the outcome "
                    f"('{node}').",
                )
            )
            continue
        if node not in observed:
            violations.append(
                Violation(
                    "unobserved_variable",
                    node,
                    f"'{node}' is declared unobserved (no measured column): it cannot be an "
                    "adjustment covariate, because nothing could ever be conditioned on it in "
                    "the data.",
                )
            )
            continue
        if node in dag.descendants_of(treatment):
            violations.append(
                Violation(
                    "post_treatment_variable",
                    node,
                    f"'{node}' is a descendant of the treatment '{treatment}'. Adjusting for a "
                    "post-treatment variable biases the total effect (it can block part of the "
                    "causal pathway or open collider paths).",
                )
            )

    # Condition 3: exact d-separation in the backdoor graph. Only attempted
    # when the set is otherwise structurally admissible, so the answer states
    # the *first-order* problems cleanly.
    structural = [
        v
        for v in violations
        if v.code in {"unknown_variable", "adjustment_contains_scope", "unobserved_variable", "post_treatment_variable"}
    ]
    open_paths: list[list[str]] = []
    bounded = False
    if not structural:
        from app.causal.d_separation import d_separated as _dsep

        backdoor_graph = dag.without_outgoing_from(treatment)
        sep = _dsep(backdoor_graph, treatment, outcome, proposed)
        if not sep.d_separated:
            violations.append(
                Violation(
                    "open_backdoor_path",
                    None,
                    "With this set, at least one backdoor path from "
                    f"'{treatment}' to '{outcome}' remains open under the assumed DAG "
                    "(d-separation fails in the backdoor graph).",
                )
            )
            listed, bounded = _backdoor_paths(dag, treatment, outcome)
            open_paths = [p for p in listed if _path_is_open(dag, proposed, p)]

    return AdjustmentEvaluation(
        treatment=treatment,
        outcome=outcome,
        adjustment_set=sorted(proposed),
        valid=not violations,
        violations=violations,
        open_backdoor_paths=open_paths,
        path_listing_bounded=bounded,
    )


def _path_is_open(
    dag: DAG,
    z: list[str],
    path: list[str],
) -> bool:
    """Whether one listed path is active given z (explanation helper only).

    Collider status: both neighbouring path edges point into the node.
    A collider blocks unless conditioned on or descended-from-conditioned; a
    chain/fork node blocks when conditioned on. This is the per-path restatement
    of d-separation, used to name which enumerated backdoor paths stay open -
    the blocking verdict itself always comes from the exact reachability test.
    """
    edges = set(dag.edges)
    zset = set(z)
    for index in range(1, len(path) - 1):
        prev_node, node, next_node = path[index - 1], path[index], path[index + 1]
        is_collider = (prev_node, node) in edges and (next_node, node) in edges
        if is_collider:
            if node not in zset and not (dag.descendants_of(node) & zset):
                return False  # blocked collider
        elif node in zset:
            return False  # blocked chain / fork
    return True


def _greedy_minimise(
    dag: DAG,
    treatment: str,
    outcome: str,
    observed: set[str],
    start: list[str],
    counter: list[int],
) -> list[str] | None:
    """Reduce a verified set to an inclusion-minimal one by deterministic descent.

    Each removal is re-verified by exact d-separation; a removal that breaks
    the criterion is rejected. The result is inclusion-minimal by construction.
    """
    current = sorted(start)
    while True:
        removed_something = False
        for node in current:
            counter[0] += 1
            trial = [item for item in current if item != node]
            if evaluate_adjustment_set(dag, treatment, outcome, trial, observed).valid:
                current = trial
                removed_something = True
                break
        if not removed_something:
            return current


def search_adjustment_sets(
    dag: DAG,
    treatment: str,
    outcome: str,
    observed: set[str],
    *,
    max_candidates: int = MAX_CANDIDATE_SETS,
    max_seconds: float = MAX_SEARCH_SECONDS,
) -> AdjustmentSearchResult:
    """Deterministic search for inclusion-minimal backdoor adjustment sets.

    *Inclusion-minimal* is precise: no *proper subset* of a reported set also
    satisfies the criterion. Minimal sets are not minimum-cardinality sets -
    several minimal sets of different sizes can exist, and all are reported.

    Determinism: candidates are enumerated by (cardinality, lexicographic
    order) over the sorted eligible list, so identical graphs yield identical
    result order.

    Bounds and honesty: if the candidate budget, cardinality ceiling or clock
    truncates the enumeration, the result is flagged
    ``search_status="incomplete"`` and no completeness claim is made.
    """
    started = time.monotonic()
    if treatment not in set(dag.nodes) or outcome not in set(dag.nodes):
        raise AdjustmentQueryError(
            "unknown_scope_node",
            "The treatment and outcome must both be nodes of the graph.",
        )
    if treatment == outcome:
        raise AdjustmentQueryError(
            "same_node",
            "The treatment and the outcome must be distinct variables.",
        )

    forbidden = forbidden_for_adjustment(dag, treatment, outcome)
    candidates = eligible_candidates(dag, treatment, outcome, observed)
    counter = [0]

    # The empty set: cheapest possible answer, checked first.
    counter[0] += 1
    if evaluate_adjustment_set(dag, treatment, outcome, [], observed).valid:
        return AdjustmentSearchResult(
            treatment=treatment,
            outcome=outcome,
            status="complete",
            minimal_sets=[AdjustmentSetCandidate([], "verified", True)],
            forbidden_variables=forbidden,
            eligible_candidates=candidates,
            candidates_considered=counter[0],
            bounds=_bounds_payload(max_candidates, max_seconds),
        )

    found: list[AdjustmentSetCandidate] = []

    def _budget_exceeded() -> bool:
        return counter[0] >= max_candidates or (time.monotonic() - started) >= max_seconds

    exhaustive = len(candidates) <= MAX_EXHAUSTIVE_CANDIDATES
    truncated = False

    if exhaustive:
        # Enumerate by (size, lex). A candidate is kept only when no
        # already-accepted smaller set is its subset - this guarantees every
        # reported set is inclusion-minimal, and every minimal set appears.
        for size in range(1, len(candidates) + 1):
            for combo in combinations(candidates, size):
                counter[0] += 1
                if _budget_exceeded():
                    truncated = True
                    break
                if any(set(accepted.variables) <= set(combo) for accepted in found):
                    # A verified subset already suffices; this set cannot be minimal.
                    continue
                if evaluate_adjustment_set(dag, treatment, outcome, list(combo), observed).valid:
                    found.append(AdjustmentSetCandidate(sorted(combo), "verified", True))
            if truncated:
                break
    else:
        # Documented non-exhaustive strategy: verified greedy candidates, each
        # minimised and individually re-verified. Absence of further sets is
        # never claimed.
        parents_of_x = [p for p in dag.parents(treatment) if p in observed]
        parents_of_y = [p for p in dag.parents(outcome) if p in observed]
        canonical = sorted(
            {p for p in [*parents_of_x, *parents_of_y] if p not in set(forbidden)}
        )
        starts: list[tuple[list[str], str]] = []
        if canonical:
            starts.append((canonical, "verified_canonical_candidate"))
        full = list(candidates)
        if full:
            starts.append((full, "verified_greedy_minimised"))
        for start, provenance in starts:
            counter[0] += 1
            if _budget_exceeded():
                truncated = True
                break
            if evaluate_adjustment_set(dag, treatment, outcome, start, observed).valid:
                minimal = _greedy_minimise(dag, treatment, outcome, observed, start, counter)
                if minimal is not None and not any(set(kept.variables) <= set(minimal) for kept in found):
                    found.append(AdjustmentSetCandidate(minimal, provenance, True))
            if _budget_exceeded():
                truncated = True
                break

    if truncated:
        status = "incomplete"
        reason = (
            "The search stopped at a documented bound "
            f"({max_candidates} candidate evaluations or {max_seconds} s) before the "
            "enumeration finished. Every listed set has been individually verified, but "
            "the list is NOT exhaustive and no 'no valid set exists' claim is made."
        )
    elif not exhaustive:
        status = "incomplete"
        reason = (
            f"The graph has {len(candidates)} eligible observed candidates, above the "
            f"exhaustive-enumeration bound of {MAX_EXHAUSTIVE_CANDIDATES}, so full "
            "enumeration was skipped in favour of verified greedy candidates. Every listed "
            "set has been individually verified against the criterion, but the list is NOT "
            "exhaustive and no 'no further valid sets' claim is made."
        )
    else:
        status = "complete"
        reason = None

    return AdjustmentSearchResult(
        treatment=treatment,
        outcome=outcome,
        status=status,
        minimal_sets=found,
        forbidden_variables=forbidden,
        eligible_candidates=candidates,
        candidates_considered=counter[0],
        bounds=_bounds_payload(max_candidates, max_seconds),
        status_reason=reason,
    )


def _bounds_payload(max_candidates: int, max_seconds: float) -> dict[str, object]:
    return {
        "max_exhaustive_candidates": MAX_EXHAUSTIVE_CANDIDATES,
        "max_candidate_evaluations": max_candidates,
        "max_search_seconds": max_seconds,
    }


__all__ = [
    "ADJUSTMENT_SCOPE_NOTE",
    "ADJUSTMENT_VERSION",
    "MAX_CANDIDATE_SETS",
    "MAX_EXHAUSTIVE_CANDIDATES",
    "MAX_SEARCH_SECONDS",
    "VIOLATION_CODES",
    "AdjustmentEvaluation",
    "AdjustmentQueryError",
    "AdjustmentSearchResult",
    "AdjustmentSetCandidate",
    "eligible_candidates",
    "evaluate_adjustment_set",
    "forbidden_for_adjustment",
    "search_adjustment_sets",
]
