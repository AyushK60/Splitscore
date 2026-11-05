"""Graph validation engine: blocking errors, scientific warnings, derived structure.

Two kinds of output, never mixed:

* **Errors** (blocking) — the payload is not a well-formed directed acyclic
  graph under this schema, or its references point outside the dataset. The
  registry refuses to store or update a specification that has any of these, so
  an invalid request can never replace a stored, valid graph.
* **Warnings** (non-blocking, scientific) — the graph is well-formed but the
  study around it is incomplete or has internal tensions. Warnings are
  information for the researcher, not failures.

This module also derives structural properties *from the graph itself*
(parents, children, ancestors, descendants, colliders, directed-path status).
Those are the only properties the application is entitled to claim: they follow
from the edges the user drew. The user-declared conceptual ``kind`` is reported
separately and, where it contradicts the drawn structure, a warning says so —
the contradiction is reported, never resolved in either direction, and never
presented as proof that the declaration or the structure is correct.

Cycle detection is an iterative depth-first search with an explicit stack, so
deep chains cannot hit Python's recursion limit. Path enumeration for mediator
analysis is bounded so a dense graph cannot make the endpoint unresponsive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.causal.schema import CausalGraphSpec, NodeKind

#: Bound on enumerated directed treatment→outcome paths used for mediator
#: detection. Reaching the bound degrades to a disclosure, not a wrong answer.
MAX_ENUMERATED_PATHS = 1000

ERROR_CODES = {
    "duplicate_node_id",
    "duplicate_edge",
    "self_loop",
    "edge_endpoint_missing",
    "directed_cycle",
    "unknown_column",
    "analysis_node_missing",
    "analysis_same_node",
    "unsupported_schema_version",
    "duplicate_assumption_id",
}

WARNING_CODES = {
    "analysis_incomplete",
    "no_directed_path",
    "isolated_node",
    "unobserved_variable_present",
    "edge_missing_rationale",
    "assumption_missing_rationale",
    "no_target_population",
    "declared_role_unsupported",
    "declared_kind_disagrees_with_scope",
    "unobserved_kind_marked_observed",
    "dataset_schema_drift",
    "empty_graph",
}

_ERROR = "error"
_WARNING = "warning"


@dataclass
class GraphIssue:
    """One structured validation finding, ready for the future frontend."""

    code: str
    severity: str
    message: str
    hint: str | None = None
    node_id: str | None = None
    edge_index: int | None = None
    assumption_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "hint": self.hint,
            "node_id": self.node_id,
            "edge_index": self.edge_index,
            "assumption_id": self.assumption_id,
        }


@dataclass
class ValidationResult:
    ok: bool
    errors: list[GraphIssue] = field(default_factory=list)
    warnings: list[GraphIssue] = field(default_factory=list)
    derived: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [issue.to_payload() for issue in self.errors],
            "warnings": [issue.to_payload() for issue in self.warnings],
            "derived": self.derived,
        }


def _adjacency(
    node_ids: list[str], edges: list[tuple[str, str]]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    children: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    parents: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    known = set(node_ids)
    for source, target in edges:
        if source in known and target in known:
            children[source].append(target)
            parents[target].append(source)
    return children, parents


def _find_cycle(node_ids: list[str], edges: list[tuple[str, str]]) -> list[str] | None:
    """Return one directed cycle as an ordered node list, or ``None``."""
    children, _ = _adjacency(node_ids, edges)
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {node_id: WHITE for node_id in node_ids}
    parent: dict[str, str | None] = {node_id: None for node_id in node_ids}

    for start in node_ids:
        if colour[start] != WHITE:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        colour[start] = GREY
        while stack:
            node, index = stack.pop()
            if index < len(children[node]):
                stack.append((node, index + 1))
                nxt = children[node][index]
                if colour[nxt] == GREY:
                    cycle = [nxt]
                    cursor = node
                    while cursor != nxt:
                        cycle.append(cursor)
                        cursor = parent[cursor]  # type: ignore[assignment]
                    cycle.reverse()
                    return cycle
                if colour[nxt] == WHITE:
                    colour[nxt] = GREY
                    parent[nxt] = node
                    stack.append((nxt, 0))
            else:
                colour[node] = BLACK
    return None


def _reachable(starts: set[str], adjacency: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(starts)
    while stack:
        node = stack.pop()
        for nxt in adjacency.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _directed_paths(
    treatment: str, outcome: str, children: dict[str, list[str]]
) -> tuple[list[list[str]], bool]:
    """All simple directed paths from treatment to outcome, bounded.

    Returns ``(paths, bound_reached)``. When the bound is reached the path list
    is incomplete but ``bound_reached`` discloses it, so consumers never present
    a truncated enumeration as exhaustive.
    """
    paths: list[list[str]] = []
    bound_reached = False
    stack: list[tuple[str, list[str]]] = [(treatment, [treatment])]
    while stack:
        node, path = stack.pop()
        if node == outcome:
            paths.append(path)
            if len(paths) >= MAX_ENUMERATED_PATHS:
                return paths, True
            continue
        for nxt in children.get(node, ()):
            if nxt not in path:
                stack.append((nxt, [*path, nxt]))
    return paths, bound_reached


def derive_structure(spec: CausalGraphSpec) -> dict[str, Any]:
    """Graph-derived properties. These follow from the drawn edges alone."""
    node_ids = [node.node_id for node in spec.nodes]
    edges = [(edge.source, edge.target) for edge in spec.edges]
    children, parents = _adjacency(node_ids, edges)

    treatment = spec.analysis.treatment
    outcome = spec.analysis.outcome
    has_scope = bool(treatment) and bool(outcome) and treatment in parents and outcome in parents

    descendants: dict[str, set[str]] = {}
    ancestors: dict[str, set[str]] = {}
    for node_id in node_ids:
        descendants[node_id] = _reachable({node_id}, children)
        descendants[node_id].discard(node_id)
        ancestors[node_id] = _reachable({node_id}, parents)
        ancestors[node_id].discard(node_id)

    on_path: set[str] = set()
    path_bound_reached = False
    if has_scope:
        paths, path_bound_reached = _directed_paths(treatment, outcome, children)  # type: ignore[arg-type]
        for path in paths:
            on_path.update(path)

    per_node: dict[str, dict[str, Any]] = {}
    for node_id in node_ids:
        per_node[node_id] = {
            "parents": sorted(parents[node_id]),
            "children": sorted(children[node_id]),
            "ancestors": sorted(ancestors[node_id]),
            "descendants": sorted(descendants[node_id]),
            "is_collider": len(parents[node_id]) >= 2,
            "on_directed_treatment_outcome_path": node_id in on_path,
        }

    return {
        "node_count": len(node_ids),
        "edge_count": len(edges),
        "is_dag": _find_cycle(node_ids, edges) is None,
        "has_directed_treatment_outcome_path": bool(on_path),
        "path_enumeration_bounded": path_bound_reached,
        "treatment": treatment,
        "outcome": outcome,
        "nodes": per_node,
        "note": (
            "These properties are derived from the drawn edges only. They describe the assumed "
            "structure, not any property of the data."
        ),
    }


def _structure_conflicts(spec: CausalGraphSpec, derived: dict[str, Any]) -> list[GraphIssue]:
    """Where a user-declared conceptual role contradicts the drawn structure."""
    issues: list[GraphIssue] = []
    per_node = derived["nodes"]
    treatment = spec.analysis.treatment
    outcome = spec.analysis.outcome

    for node in spec.nodes:
        info = per_node[node.node_id]
        if node.kind == "mediator" and derived["has_directed_treatment_outcome_path"]:
            if not info["on_directed_treatment_outcome_path"]:
                issues.append(
                    GraphIssue(
                        code="declared_role_unsupported",
                        severity=_WARNING,
                        node_id=node.node_id,
                        message=(
                            f"Node '{node.label}' is declared as a mediator, but no directed path "
                            "from the selected treatment to the selected outcome passes through it."
                        ),
                        hint=(
                            "Either draw a directed treatment→…→outcome path through this node, or "
                            "re-declare its role. SplitScope reports the contradiction; it does not "
                            "decide which side is right."
                        ),
                    )
                )
        if node.kind == "treatment" and treatment and treatment != node.node_id:
            issues.append(
                GraphIssue(
                    code="declared_kind_disagrees_with_scope",
                    severity=_WARNING,
                    node_id=node.node_id,
                    message=(
                        f"Node '{node.label}' carries the 'treatment' annotation, but the analysis "
                        f"scope selects '{treatment}' as the treatment."
                    ),
                    hint="Align the analysis scope with the node annotations, or re-declare the role.",
                )
            )
        if node.kind == "outcome" and outcome and outcome != node.node_id:
            issues.append(
                GraphIssue(
                    code="declared_kind_disagrees_with_scope",
                    severity=_WARNING,
                    node_id=node.node_id,
                    message=(
                        f"Node '{node.label}' carries the 'outcome' annotation, but the analysis "
                        f"scope selects '{outcome}' as the outcome."
                    ),
                    hint="Align the analysis scope with the node annotations, or re-declare the role.",
                )
            )
        if node.kind == "unobserved" and node.observed:
            issues.append(
                GraphIssue(
                    code="unobserved_kind_marked_observed",
                    severity=_WARNING,
                    node_id=node.node_id,
                    message=(
                        f"Node '{node.label}' uses the 'unobserved' role but is still marked as "
                        "observed."
                    ),
                    hint="Set observed=false for variables with no measured column.",
                )
            )
    return issues


def validate_spec(
    spec: CausalGraphSpec,
    *,
    dataset_columns: list[str] | None = None,
    stored_dataset_fingerprint: str | None = None,
    current_dataset_fingerprint: str | None = None,
) -> ValidationResult:
    """Validate a full specification against the schema and, when supplied, the dataset.

    ``dataset_columns`` enables dataset-column reference checks. Providing both
    fingerprints enables the schema-drift warning used when a stored graph is
    re-validated against the dataset currently in memory.
    """
    errors: list[GraphIssue] = []
    warnings: list[GraphIssue] = []

    if spec.schema_version != "1.0.0":
        errors.append(
            GraphIssue(
                code="unsupported_schema_version",
                severity=_ERROR,
                message=(
                    f"This build reads causal graph schema '1.0.0'; the payload declares "
                    f"{spec.schema_version!r}."
                ),
                hint="Re-export the graph from a compatible build, or hand-edit the version.",
            )
        )

    # -- nodes -------------------------------------------------------------- #
    seen_ids: set[str] = set()
    for node in spec.nodes:
        if node.node_id in seen_ids:
            errors.append(
                GraphIssue(
                    code="duplicate_node_id",
                    severity=_ERROR,
                    node_id=node.node_id,
                    message=f"Node id '{node.node_id}' is used more than once.",
                    hint="Node ids must be unique within a graph.",
                )
            )
        seen_ids.add(node.node_id)

    # -- edges -------------------------------------------------------------- #
    seen_edges: set[tuple[str, str]] = set()
    for index, edge in enumerate(spec.edges):
        if edge.source == edge.target:
            errors.append(
                GraphIssue(
                    code="self_loop",
                    severity=_ERROR,
                    edge_index=index,
                    node_id=edge.source,
                    message=f"Edge {index} loops from '{edge.source}' back to itself.",
                    hint="A causal graph cannot contain self-loops.",
                )
            )
        if edge.source not in seen_ids or edge.target not in seen_ids:
            missing = sorted({edge.source, edge.target} - seen_ids)
            errors.append(
                GraphIssue(
                    code="edge_endpoint_missing",
                    severity=_ERROR,
                    edge_index=index,
                    message=(
                        f"Edge {index} ({edge.source} → {edge.target}) references undefined "
                        f"node(s): {', '.join(missing)}."
                    ),
                    hint="Define every node an edge connects, or remove the edge.",
                )
            )
            continue
        pair = (edge.source, edge.target)
        if pair in seen_edges:
            errors.append(
                GraphIssue(
                    code="duplicate_edge",
                    severity=_ERROR,
                    edge_index=index,
                    message=(
                        f"Edge {index} duplicates the directed edge {edge.source} → {edge.target}."
                    ),
                    hint="A directed edge appears at most once.",
                )
            )
        seen_edges.add(pair)

    # -- cycles ------------------------------------------------------------- #
    if not errors or all(issue.code != "edge_endpoint_missing" for issue in errors):
        acyclic_candidates = [pair for pair in seen_edges if pair[0] != pair[1]]
        cycle = _find_cycle([node.node_id for node in spec.nodes], acyclic_candidates)
        if cycle:
            errors.append(
                GraphIssue(
                    code="directed_cycle",
                    severity=_ERROR,
                    message="The graph contains a directed cycle: " + " → ".join([*cycle, cycle[0]]) + ".",
                    hint="Remove one edge from the cycle. Causal DAGs are acyclic.",
                )
            )

    # -- dataset-column references ------------------------------------------ #
    if dataset_columns is not None:
        known = set(dataset_columns)
        for node in spec.nodes:
            if node.column is not None and node.column not in known:
                errors.append(
                    GraphIssue(
                        code="unknown_column",
                        severity=_ERROR,
                        node_id=node.node_id,
                        message=(
                            f"Node '{node.label}' is anchored to column '{node.column}', which is "
                            "not present in this dataset."
                        ),
                        hint="Anchor the node to an existing column, or clear the column to keep it "
                        "as a hypothesised, unmeasured variable.",
                    )
                )

    # -- analysis scope ------------------------------------------------------ #
    treatment = spec.analysis.treatment
    outcome = spec.analysis.outcome
    if treatment is not None and treatment not in seen_ids:
        errors.append(
            GraphIssue(
                code="analysis_node_missing",
                severity=_ERROR,
                node_id=treatment,
                message=f"The analysis scope selects treatment '{treatment}', which is not a node.",
            )
        )
    if outcome is not None and outcome not in seen_ids:
        errors.append(
            GraphIssue(
                code="analysis_node_missing",
                severity=_ERROR,
                node_id=outcome,
                message=f"The analysis scope selects outcome '{outcome}', which is not a node.",
            )
        )
    if (
        treatment is not None
        and outcome is not None
        and treatment == outcome
        and treatment in seen_ids
    ):
        errors.append(
            GraphIssue(
                code="analysis_same_node",
                severity=_ERROR,
                node_id=treatment,
                message="The treatment and the outcome are the same node.",
                hint="A causal effect needs two distinct variables.",
            )
        )

    # -- assumptions --------------------------------------------------------- #
    seen_assumptions: set[str] = set()
    for assumption in spec.assumptions:
        if assumption.assumption_id in seen_assumptions:
            errors.append(
                GraphIssue(
                    code="duplicate_assumption_id",
                    severity=_ERROR,
                    assumption_id=assumption.assumption_id,
                    message=(
                        f"Assumption id '{assumption.assumption_id}' is used more than once."
                    ),
                )
            )
        seen_assumptions.add(assumption.assumption_id)
        if assumption.rationale is None or not assumption.rationale.strip():
            warnings.append(
                GraphIssue(
                    code="assumption_missing_rationale",
                    severity=_WARNING,
                    assumption_id=assumption.assumption_id,
                    message=(
                        f"Assumption '{assumption.assumption_id}' "
                        f"({assumption.category.replace('_', ' ')}) has no written rationale."
                    ),
                    hint="Record why you believe the assumption holds for this study.",
                )
            )

    # -- scientific warnings -------------------------------------------------- #
    if treatment is None or outcome is None:
        warnings.append(
            GraphIssue(
                code="analysis_incomplete",
                severity=_WARNING,
                message=(
                    "The analysis scope is incomplete: select one treatment and one outcome node "
                    "before requesting any causal identification (a later stage)."
                ),
            )
        )
    if treatment and outcome and treatment in seen_ids and outcome in seen_ids:
        derived = derive_structure(spec)
        if not derived["has_directed_treatment_outcome_path"]:
            warnings.append(
                GraphIssue(
                    code="no_directed_path",
                    severity=_WARNING,
                    message=(
                        "There is no directed path from the treatment to the outcome in this graph, "
                        "so the assumed structure implies no causal effect of the treatment on the "
                        "outcome."
                    ),
                    hint=(
                        "This may be intentional (a null structure) or a missing edge. It is not an "
                        "error."
                    ),
                )
            )

    children, parents = _adjacency(
        [node.node_id for node in spec.nodes],
        [(edge.source, edge.target) for edge in spec.edges if edge.source in seen_ids and edge.target in seen_ids],
    )
    for node in spec.nodes:
        if not children[node.node_id] and not parents[node.node_id] and len(spec.nodes) > 1:
            warnings.append(
                GraphIssue(
                    code="isolated_node",
                    severity=_WARNING,
                    node_id=node.node_id,
                    message=f"Node '{node.label}' has no edges.",
                    hint="An isolated variable cannot participate in the assumed structure.",
                )
            )
        if not node.observed or node.kind == "unobserved":
            warnings.append(
                GraphIssue(
                    code="unobserved_variable_present",
                    severity=_WARNING,
                    node_id=node.node_id,
                    message=(
                        f"Node '{node.label}' is declared unobserved; any role it plays in "
                        "confounding or mediation cannot be checked against the data."
                    ),
                )
            )
    for index, edge in enumerate(spec.edges):
        if edge.rationale is None or not edge.rationale.strip():
            warnings.append(
                GraphIssue(
                    code="edge_missing_rationale",
                    severity=_WARNING,
                    edge_index=index,
                    message=f"Edge {index} ({edge.source} → {edge.target}) has no written rationale.",
                    hint="Record why you assume this causal relationship exists.",
                )
            )

    if not any(item.category == "target_population" for item in spec.assumptions):
        warnings.append(
            GraphIssue(
                code="no_target_population",
                severity=_WARNING,
                message="No target population has been documented for this study.",
                hint="Record who the assumed causal relationships are meant to describe.",
            )
        )

    if len(spec.nodes) == 0:
        warnings.append(
            GraphIssue(
                code="empty_graph",
                severity=_WARNING,
                message="The graph has no nodes yet.",
            )
        )

    derived = derive_structure(spec)
    warnings.extend(_structure_conflicts(spec, derived))

    if (
        stored_dataset_fingerprint is not None
        and current_dataset_fingerprint is not None
        and stored_dataset_fingerprint != current_dataset_fingerprint
    ):
        warnings.append(
            GraphIssue(
                code="dataset_schema_drift",
                severity=_WARNING,
                message=(
                    "This graph was created against a different version of the dataset than the "
                    "one currently in memory. Column references may no longer match."
                ),
                hint="Re-check every node's column reference against the current dataset.",
            )
        )

    return ValidationResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        derived=derived,
    )


__all__ = [
    "ERROR_CODES",
    "GraphIssue",
    "MAX_ENUMERATED_PATHS",
    "ValidationResult",
    "WARNING_CODES",
    "derive_structure",
    "validate_spec",
]
