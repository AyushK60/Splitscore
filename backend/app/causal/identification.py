"""Graphical identification status for one treatment/outcome pair (S8C).

This module answers exactly one question, from the *assumed graph alone*:

    "Under the classical backdoor criterion, which observed adjustment sets —
    if any — are admissible for the total effect of X on Y, and what does the
    drawn structure say about why?"

What it deliberately does **not** answer:

* whether the effect is identifiable by *some other* method (front-door,
  instrumental variables, generalised adjustment, do-calculus) — a backdoor
  failure is reported as a backdoor failure, never as proof of general
  non-identifiability;
* the size or sign of any effect — S8C produces no causal numbers.

Every explanation is rule-based on graph structure (roles, colliders,
descendants, observedness). No LLM, no correlation, no dataset statistics.

Possible identification outcomes (``status``):

* ``backdoor_adjustment_available`` — a complete search found ≥1 admissible
  observed set (possibly the empty set).
* ``no_eligible_backdoor_set`` — the search ran to completion within all
  bounds and found none. Qualified explicitly as backdoor-only.
* ``search_incomplete`` — a documented bound truncated the search.
* ``invalid_graph`` — the graph failed structural validation.
* ``invalid_scope`` — treatment/outcome missing, unknown, or identical.
* ``missing_dataset_variables`` — treatment or outcome is declared unobserved,
  so no adjustment could ever support estimation on the dataset.
* ``unsupported_identification_method`` — a method other than ``backdoor``
  was requested (S8C implements only the classical backdoor criterion).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.causal.adjustment import (
    AdjustmentSearchResult,
    search_adjustment_sets,
)
from app.causal.d_separation import DAG
from app.causal.schema import CausalGraphSpec

#: Version of the identification contract, echoed in every payload.
IDENTIFICATION_VERSION = "1.0.0"

IDENTIFICATION_STATUSES = {
    "backdoor_adjustment_available",
    "no_eligible_backdoor_set",
    "search_incomplete",
    "invalid_graph",
    "invalid_scope",
    "missing_dataset_variables",
    "unsupported_identification_method",
}

#: Scope note carried verbatim in every identification payload.
IDENTIFICATION_SCOPE_NOTE = (
    "Identification here is graphical: it uses only the assumed DAG and the "
    "observed/unobserved declarations. A valid adjustment set is graphically "
    "admissible, not scientifically proven; exchanging the drawn edges for "
    "different assumptions yields different answers. No causal effect is "
    "estimated and no data is consulted."
)

SUPPORTED_METHODS = {"backdoor"}


@dataclass
class Explanation:
    """One rule-based, human-readable scientific explanation."""

    code: str
    title: str
    body: str
    node_ids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "body": self.body,
            "node_ids": list(self.node_ids),
        }


@dataclass
class IdentificationResult:
    status: str
    treatment: str | None
    outcome: str | None
    explanations: list[Explanation]
    search: AdjustmentSearchResult | None
    caveats: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "treatment": self.treatment,
            "outcome": self.outcome,
            "explanations": [e.to_payload() for e in self.explanations],
            "caveats": list(self.caveats),
            "interpretation_note": IDENTIFICATION_SCOPE_NOTE,
        }
        if self.search is not None:
            payload["search"] = self.search.to_payload()
        return payload


def build_dag(spec: CausalGraphSpec) -> DAG:
    """The validated DAG over the spec's nodes and assumed edges."""
    return DAG(
        [node.node_id for node in spec.nodes],
        [(edge.source, edge.target) for edge in spec.edges],
    )


def observed_node_ids(spec: CausalGraphSpec) -> set[str]:
    return {node.node_id for node in spec.nodes if not node.is_unobserved}


def _explain_structure(
    spec: CausalGraphSpec,
    dag: DAG,
    treatment: str,
    outcome: str,
    search: AdjustmentSearchResult,
) -> list[Explanation]:
    """Rule-based explanations for the drawn structure around the scope pair."""
    explanations: list[Explanation] = []
    forbidden = set(search.forbidden_variables)
    eligible = set(search.eligible_candidates)
    nodes_by_id = {node.node_id: node for node in spec.nodes}

    descendants_of_x = dag.descendants_of(treatment)
    treatment_descendants = [n for n in sorted(descendants_of_x) if n not in (treatment, outcome)]

    # 1. Confounders: observed common causes of X and Y that are eligible.
    confounders = sorted(
        node
        for node in eligible
        if node in dag.ancestors_of_set({treatment})
        and node in dag.ancestors_of_set({outcome})
    )
    if confounders:
        names = ", ".join(nodes_by_id[n].label for n in confounders)
        explanations.append(
            Explanation(
                code="confounder_needs_adjustment",
                title="Common causes need adjustment for the total effect",
                body=(
                    f"{names} cause(s) both the treatment and the outcome in the assumed "
                    "graph, so the backdoor paths they carry would otherwise leave a "
                    "spurious association between treatment and outcome. Adjusting for them "
                    "blocks those paths — under the assumed structure and the classical "
                    "total-effect criterion."
                ),
                node_ids=confounders,
            )
        )

    # 2. Post-treatment variables: forbidden, each with its structural reason.
    post_treatment = sorted(n for n in treatment_descendants if n in forbidden)
    if post_treatment:
        mediator_like = sorted(
            n
            for n in post_treatment
            if n in _nodes_on_directed_paths(dag, treatment, outcome)
        )
        if mediator_like:
            mediator_names = ", ".join(nodes_by_id[n].label for n in mediator_like)
            explanations.append(
                Explanation(
                    code="mediator_not_adjusted",
                    title="Mediators are not adjusted for the total effect",
                    body=(
                        f"{mediator_names} lie(s) on a directed path from the treatment to "
                        "the outcome. Adjusting for a mediator removes the part of the total "
                        "effect that travels through it, so the classical backdoor criterion "
                        "for the *total* effect forbids it. (Mediation analysis is a separate "
                        "question, outside S8C.)"
                    ),
                    node_ids=mediator_like,
                )
            )
        other_post = [n for n in post_treatment if n not in mediator_like]
        if other_post:
            other_names = ", ".join(nodes_by_id[n].label for n in other_post)
            explanations.append(
                Explanation(
                    code="post_treatment_forbidden",
                    title="Descendants of the treatment are forbidden",
                    body=(
                        f"{other_names} descend(s) from the treatment '{nodes_by_id[treatment].label}' "
                        "in the assumed graph. Conditioning on any post-treatment variable can "
                        "distort the total effect (blocking causal pathways or opening collider "
                        "paths), so the classical criterion excludes them outright."
                    ),
                    node_ids=other_post,
                )
            )

    # 3. Colliders on backdoor structure: warn against conditioning on them.
    collider_warnings: list[str] = []
    backdoor_nodes = _nodes_on_backdoor_paths(dag, treatment, outcome)
    for node in sorted(eligible):
        is_collider = len(dag.parents(node)) >= 2
        if is_collider and (node in dag.descendants_of(treatment) or node in backdoor_nodes):
            collider_warnings.append(node)
    if collider_warnings:
        names = ", ".join(nodes_by_id[n].label for n in collider_warnings)
        explanations.append(
            Explanation(
                code="collider_caution",
                title="Conditioning on these colliders would open paths",
                body=(
                    f"{names} receive(s) two or more incoming edges in the assumed graph, so "
                    "conditioning on them can induce association where the assumed structure "
                    "has none (collider bias) — including opening otherwise-blocked backdoor "
                    "paths. This is why some candidate sets fail the criterion even though "
                    "every member looks like an ordinary covariate."
                ),
                node_ids=collider_warnings,
            )
        )

    # 4. Unobserved variables that block adjustment.
    unobserved = sorted(
        node.node_id
        for node in spec.nodes
        if node.is_unobserved and node.node_id not in (treatment, outcome)
    )
    if unobserved:
        names = ", ".join(nodes_by_id[n].label for n in unobserved)
        explanations.append(
            Explanation(
                code="unobserved_confounding",
                title="Unobserved variables cannot be adjusted for",
                body=(
                    f"{names} is/are declared unobserved (no measured column). If such a "
                    "variable is a common cause of treatment and outcome, no measured "
                    "adjustment set can block its backdoor paths, and the criterion fails "
                    "honestly: SplitScope will not pretend a measured covariate can stand in "
                    "for a variable the dataset never recorded."
                ),
                node_ids=unobserved,
            )
        )

    # 5. Structural validity is not scientific correctness.
    explanations.append(
        Explanation(
            code="structure_not_truth",
            title="A graphically valid set is not a scientifically proven one",
            body=(
                "Every statement above follows from the edges you drew. If an edge is "
                "missing, reversed, or wrongly directed in the world, the identification "
                "answer inherits that error. A passing backdoor criterion licenses an "
                "estimation *under these assumptions*; it does not validate the assumptions."
            ),
        )
    )
    return explanations


def _nodes_on_directed_paths(dag: DAG, treatment: str, outcome: str) -> set[str]:
    """Intermediate nodes on some directed treatment→outcome path (bounded)."""
    paths, _ = _enumerate_directed(dag, treatment, outcome, max_paths=200)
    on_path: set[str] = set()
    for path in paths:
        on_path.update(path)
    on_path.discard(treatment)
    on_path.discard(outcome)
    return on_path


def _nodes_on_backdoor_paths(dag: DAG, treatment: str, outcome: str) -> set[str]:
    backdoor = dag.without_outgoing_from(treatment)
    paths, _ = _enumerate_directed(backdoor, treatment, outcome, max_paths=200)
    on_path: set[str] = set()
    for path in paths:
        on_path.update(path)
    on_path.discard(treatment)
    on_path.discard(outcome)
    return on_path


def _enumerate_directed(
    dag: DAG,
    start: str,
    goal: str,
    *,
    max_paths: int,
) -> tuple[list[list[str]], bool]:
    paths: list[list[str]] = []
    stack: list[tuple[str, list[str]]] = [(start, [start])]
    bounded = False
    while stack:
        node, path = stack.pop()
        for nxt in dag.children(node):
            if nxt in path:
                continue
            if nxt == goal:
                paths.append([*path, nxt])
                if len(paths) >= max_paths:
                    return paths, True
                continue
            stack.append((nxt, [*path, nxt]))
    return paths, bounded


def identify_backdoor(
    spec: CausalGraphSpec,
    *,
    treatment: str | None = None,
    outcome: str | None = None,
    method: str = "backdoor",
    max_candidates: int | None = None,
    max_seconds: float | None = None,
) -> IdentificationResult:
    """Run the full graphical identification pipeline for one scope pair.

    ``spec`` must already be structurally validated (the API layer validates
    before calling). The scope pair defaults to the graph's saved analysis
    scope and can be overridden per request.
    """
    if method not in SUPPORTED_METHODS:
        return IdentificationResult(
            status="unsupported_identification_method",
            treatment=treatment,
            outcome=outcome,
            explanations=[
                Explanation(
                    code="unsupported_identification_method",
                    title="Identification method not supported",
                    body=(
                        f"S8C implements the classical backdoor criterion only; '{method}' is "
                        "not available. Front-door, instrumental variables, generalised "
                        "adjustment and do-calculus are outside this stage, and SplitScope "
                        "will not simulate them."
                    ),
                )
            ],
            search=None,
        )

    treatment = treatment or spec.analysis.treatment
    outcome = outcome or spec.analysis.outcome

    if not treatment or not outcome:
        return IdentificationResult(
            status="invalid_scope",
            treatment=treatment,
            outcome=outcome,
            explanations=[
                Explanation(
                    code="analysis_incomplete",
                    title="Select a treatment and an outcome first",
                    body=(
                        "Graphical identification needs one treatment and one distinct "
                        "outcome. Select both — here or in the graph's analysis scope — and "
                        "run identification again."
                    ),
                )
            ],
            search=None,
        )

    known = {node.node_id for node in spec.nodes}
    if treatment not in known or outcome not in known:
        return IdentificationResult(
            status="invalid_scope",
            treatment=treatment,
            outcome=outcome,
            explanations=[
                Explanation(
                    code="scope_node_missing",
                    title="The scope names variables this graph does not contain",
                    body=(
                        "Both the treatment and the outcome must be nodes of the graph "
                        "under test. Re-select them from the graph's variables."
                    ),
                )
            ],
            search=None,
        )
    if treatment == outcome:
        return IdentificationResult(
            status="invalid_scope",
            treatment=treatment,
            outcome=outcome,
            explanations=[
                Explanation(
                    code="analysis_same_node",
                    title="Treatment and outcome must be distinct",
                    body=(
                        "A causal effect is defined between two different variables; the "
                        "same node cannot be both."
                    ),
                )
            ],
            search=None,
        )

    dag = build_dag(spec)
    observed = observed_node_ids(spec)
    nodes_by_id = {node.node_id: node for node in spec.nodes}

    # The scope pair itself must be measurable for any future estimation.
    unmeasured_scope = [n for n in (treatment, outcome) if n not in observed]
    if unmeasured_scope:
        names = ", ".join(nodes_by_id[n].label for n in unmeasured_scope)
        return IdentificationResult(
            status="missing_dataset_variables",
            treatment=treatment,
            outcome=outcome,
            explanations=[
                Explanation(
                    code="scope_unobserved",
                    title="The treatment or the outcome is not measured",
                    body=(
                        f"{names} is/are declared unobserved, so no adjustment based on this "
                        "graph could ever support effect estimation on this dataset. Draw the "
                        "scope pair on measured variables (or anchor them to columns) to "
                        "make identification meaningful."
                    ),
                )
            ],
            search=None,
            caveats=[
                "Graphical identification is reported only for measurable scope pairs; this "
                "refusal is about estimation feasibility, not about the drawn structure."
            ],
        )

    kwargs: dict[str, Any] = {}
    if max_candidates is not None:
        kwargs["max_candidates"] = max_candidates
    if max_seconds is not None:
        kwargs["max_seconds"] = max_seconds
    search = search_adjustment_sets(dag, treatment, outcome, observed, **kwargs)

    if search.status == "incomplete":
        status = "search_incomplete"
    elif search.minimal_sets:
        status = "backdoor_adjustment_available"
    else:
        status = "no_eligible_backdoor_set"

    caveats = [
        (
            "Adjusting for the reported set is licensed by the drawn graph only. If the graph "
            "misstates the world, the licensed conclusion changes with it."
        )
    ]
    if status == "no_eligible_backdoor_set":
        caveats.append(
            "This failure is specific to the classical backdoor criterion. It does not prove "
            "the effect is unidentifiable by every method; S8C does not implement front-door, "
            "instrumental-variable or generalised-adjustment strategies, and will not claim to."
        )

    return IdentificationResult(
        status=status,
        treatment=treatment,
        outcome=outcome,
        explanations=_explain_structure(spec, dag, treatment, outcome, search),
        search=search,
        caveats=caveats,
    )


__all__ = [
    "IDENTIFICATION_SCOPE_NOTE",
    "IDENTIFICATION_STATUSES",
    "IDENTIFICATION_VERSION",
    "SUPPORTED_METHODS",
    "Explanation",
    "IdentificationResult",
    "build_dag",
    "identify_backdoor",
    "observed_node_ids",
]
