"""Exact d-separation for directed acyclic graphs (S8C).

The algorithm is the linear-time *reachability* formulation of the Bayes-ball
walk (Koller & Friedman, *Probabilistic Graphical Models*, 2009, Algorithm 3.1,
"Reachable"). It is exact for every DAG: a node Y is reported reachable from X
given Z if and only if there exists an active trail from X to Y given Z, i.e.
X and Y are d-connected given Z. There is no path enumeration and no
undirected-connectivity shortcut — the walk tracks travel direction (arriving
at a node "from a child" vs "from a parent") and consults the set of Z's
ancestors, which is precisely what makes colliders and collider-descendants
behave correctly.

Complexity: O(|V| + |E|) time and space per query. With the S8A schema limits
(60 nodes, 240 edges) every query is effectively instantaneous, so no further
search bounds are needed here; the bounded-enumeration concerns of S8A apply
to *listing* paths, which this engine never does.

Honesty contract (mirrors S8A): a d-separation result is a statement about
*the assumed graph*. It is never a statement about the data, and the response
payloads carry that scope note verbatim.

The module is deliberately independent of :mod:`app.causal.schema`: it takes
plain node ids and directed edges, so the test suite can drive it with
hand-built DAGs and cross-check it against an independently written oracle.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

#: Version of the d-separation engine contract, echoed in every payload.
D_SEPARATION_VERSION = "1.0.0"

#: Machine-readable name of the algorithm, for provenance in API responses.
ALGORITHM_NAME = "bayes-ball-reachability"
ALGORITHM_REFERENCE = "Koller & Friedman (2009), Algorithm 3.1 (Reachable)"

#: Scope note carried verbatim in every d-separation payload.
D_SEPARATION_SCOPE_NOTE = (
    "d-separation is a property of the assumed graph: it says which conditional "
    "independences the drawn structure implies. It is not an empirically "
    "established independence in the dataset, and no data was consulted."
)


class DSeparationQueryError(ValueError):
    """The d-separation query itself is not answerable on the supplied graph."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DAG:
    """A minimal validated directed graph over immutable node ids.

    Endpoints are checked at construction so every downstream algorithm can
    index safely. This is a *structural* container: it knows nothing about
    datasets, columns or user declarations.
    """

    __slots__ = ("_children", "_parents", "edges", "nodes")

    def __init__(self, nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> None:
        self.nodes: tuple[str, ...] = tuple(nodes)
        known = set(self.nodes)
        if len(known) != len(self.nodes):
            duplicates = sorted(
                {node for node in self.nodes if self.nodes.count(node) > 1}
            )
            raise DSeparationQueryError(
                "duplicate_node",
                f"Node identifiers must be unique; repeated: {', '.join(duplicates)}.",
            )
        clean_edges: list[tuple[str, str]] = []
        for source, target in edges:
            if source not in known or target not in known:
                raise DSeparationQueryError(
                    "edge_endpoint_missing",
                    f"Edge ({source} → {target}) references a node not in the graph.",
                )
            if source == target:
                raise DSeparationQueryError(
                    "self_loop",
                    f"Edge ({source} → {source}) is a self-loop; DAGs cannot have one.",
                )
            clean_edges.append((source, target))
        self.edges: tuple[tuple[str, str], ...] = tuple(clean_edges)

        self._children: dict[str, list[str]] = {node: [] for node in self.nodes}
        self._parents: dict[str, list[str]] = {node: [] for node in self.nodes}
        for source, target in clean_edges:
            self._children[source].append(target)
            self._parents[target].append(source)

    def children(self, node: str) -> list[str]:
        return self._children[node]

    def parents(self, node: str) -> list[str]:
        return self._parents[node]

    def ancestors_of_set(self, seeds: Iterable[str]) -> set[str]:
        """All strict ancestors of any node in ``seeds`` (the seeds excluded)."""
        seen: set[str] = set()
        stack = list(seeds)
        while stack:
            node = stack.pop()
            for parent in self._parents[node]:
                if parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        return seen

    def descendants_of(self, node: str) -> set[str]:
        """All strict descendants of ``node`` (the node itself excluded)."""
        seen: set[str] = set()
        stack = [node]
        while stack:
            current = stack.pop()
            for child in self._children[current]:
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        return seen

    def without_outgoing_from(self, node: str) -> DAG:
        """A copy of this DAG with every edge directed *out of* ``node`` removed.

        This is the backdoor graph: removing edges entering the node would
        instead represent intervening on it, which is a different operation
        with a different scientific meaning (see S8C methodology doc §3).
        """
        kept = [(s, t) for s, t in self.edges if s != node]
        return DAG(self.nodes, kept)


@dataclass
class DSeparationResult:
    """Structured answer to one d-separation query."""

    x: str
    y: str
    conditioning: list[str]
    d_separated: bool
    algorithm: str = ALGORITHM_NAME
    algorithm_version: str = D_SEPARATION_VERSION
    #: Nodes reachable from X given Z under an active trail (diagnostic only).
    reachable: set[str] = field(default_factory=set, repr=False)

    def to_payload(self) -> dict[str, object]:
        return {
            "x": self.x,
            "y": self.y,
            "conditioning": list(self.conditioning),
            "d_separated": self.d_separated,
            "interpretation": (
                f"Under the assumed DAG, '{self.x}' and '{self.y}' are "
                + ("d-separated" if self.d_separated else "d-connected")
                + (
                    " given the conditioning set."
                    if self.conditioning
                    else " given no conditioning variables."
                )
            ),
            "algorithm": {
                "name": self.algorithm,
                "version": self.algorithm_version,
                "reference": ALGORITHM_REFERENCE,
            },
            "interpretation_note": D_SEPARATION_SCOPE_NOTE,
        }


def _validate_query(dag: DAG, x: str, y: str, conditioning: Iterable[str]) -> list[str]:
    """Reject unanswerable queries before any graph walk.

    Deduplication of the conditioning set is deliberate: a repeated identifier
    asks the same question twice, and the set semantics of d-separation make
    the answer identical. The deduplicated (sorted) set is returned.
    """
    known = set(dag.nodes)
    if x not in known:
        raise DSeparationQueryError("unknown_node", f"Node '{x}' is not in the graph.")
    if y not in known:
        raise DSeparationQueryError("unknown_node", f"Node '{y}' is not in the graph.")
    if x == y:
        raise DSeparationQueryError(
            "same_node",
            "d-separation is defined for two distinct variables; x and y are the same.",
        )
    z: list[str] = []
    for node in conditioning:
        if node not in known:
            raise DSeparationQueryError(
                "unknown_node",
                f"Conditioning variable '{node}' is not in the graph.",
            )
        if node not in z:
            z.append(node)
    if x in z or y in z:
        raise DSeparationQueryError(
            "conditioning_contains_endpoint",
            "The conditioning set must exclude the tested variables themselves.",
        )
    return sorted(z)


def reachable_from(dag: DAG, x: str, z: set[str]) -> set[str]:
    """Nodes reachable from ``x`` over active trails given conditioning set ``z``.

    Exact implementation of Koller & Friedman (2009) Algorithm 3.1. ``z`` must
    not contain ``x`` (enforced by the public query entry point).
    """
    # Step 1: Z and all ancestors of Z. A collider is "activated" by
    # conditioning on it or on any of its descendants — equivalently, when the
    # walk arrives downward at a node in Z or in An(Z), the trail may continue
    # upward through it.
    activated = set(z) | dag.ancestors_of_set(z)  # Z plus An(Z): collider activation set

    # Step 2: walk over (node, direction) states. `up` = the trail entered the
    # node from one of its children (or is the start); `down` = entered from a
    # parent.
    UP, DOWN = "up", "down"
    pending: list[tuple[str, str]] = [(x, UP)]
    visited: set[tuple[str, str]] = set()
    reachable: set[str] = set()

    while pending:
        node, direction = pending.pop()
        state = (node, direction)
        if state in visited:
            continue
        visited.add(state)
        if node not in z:
            reachable.add(node)
        if direction == UP and node not in z:
            # Trail may pass straight through a non-conditioned node in either
            # direction.
            for parent in dag.parents(node):
                pending.append((parent, UP))
            for child in dag.children(node):
                pending.append((child, DOWN))
        elif direction == DOWN:
            if node not in z:
                # A chain or fork node that is not conditioned passes the trail
                # downward to its children.
                for child in dag.children(node):
                    pending.append((child, DOWN))
            if node in activated:
                # A collider (both edges into the node) passes the trail only
                # when conditioned on or descended-from-conditioned; arriving
                # downward at such a node, the trail may bounce upward. This
                # branch is exactly what distinguishes Bayes-ball from naive
                # undirected reachability.
                for parent in dag.parents(node):
                    pending.append((parent, UP))

    reachable.discard(x)
    return reachable


def d_separated(dag: DAG, x: str, y: str, conditioning: Iterable[str] = ()) -> DSeparationResult:
    """Exact d-separation test for two distinct nodes given a conditioning set."""
    z = _validate_query(dag, x, y, conditioning)
    reachable = reachable_from(dag, x, set(z))
    return DSeparationResult(
        x=x,
        y=y,
        conditioning=z,
        d_separated=y not in reachable,
        reachable=reachable,
    )


__all__ = [
    "ALGORITHM_NAME",
    "ALGORITHM_REFERENCE",
    "DAG",
    "D_SEPARATION_SCOPE_NOTE",
    "D_SEPARATION_VERSION",
    "DSeparationQueryError",
    "DSeparationResult",
    "d_separated",
    "reachable_from",
]
