"""identification d-separation engine: known-answer fixtures and an independent oracle.

Two correctness strategies, deliberately independent of each other:

1. **Known-answer fixtures** - hand-written DAGs (chain, fork, collider,
   confounded effect, M-bias, butterfly bias, disconnected pairs) whose
   d-separation answers are written into the test by hand from the graphical
   definition, not derived from the implementation.

2. **Independent oracle cross-check** - a *moralization-based* oracle
   (ancestral graph → moralization → undirected separation), implemented
   inside this test file with its own graph code sharing nothing with
   ``app.causal.d_separation``. Both engines are compared exhaustively over
   every DAG on 4 nodes, every seeded DAG on 5 nodes, and seeded random DAGs
   on 6 nodes, for every tested pair and every conditioning subset.

The two algorithms fail in different ways by construction (Bayes-ball walks
the DAG with direction memory; moralization erases directions), so agreement
across thousands of queries is real evidence, not self-consistency.
"""

from __future__ import annotations

import itertools
import random

import pytest

from app.causal.d_separation import (
    DAG,
    DSeparationQueryError,
    d_separated,
    reachable_from,
)

# --------------------------------------------------------------------------- #
# Independent oracle: moralization of the ancestral graph
# --------------------------------------------------------------------------- #


class OracleGraph:
    """A deliberately separate, minimal DAG implementation for the oracle."""

    def __init__(self, nodes: list[str], edges: set[tuple[str, str]]) -> None:
        self.nodes = nodes
        self.edges = edges

    def parents(self, node: str) -> set[str]:
        return {s for s, t in self.edges if t == node}

    def children(self, node: str) -> set[str]:
        return {t for s, t in self.edges if s == node}

    def ancestors(self, seeds: set[str]) -> set[str]:
        seen: set[str] = set()
        stack = list(seeds)
        while stack:
            node = stack.pop()
            for parent in self.parents(node):
                if parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        return seen

    def is_acyclic(self) -> bool:
        indegree = {node: len(self.parents(node)) for node in self.nodes}
        queue = [node for node, degree in indegree.items() if degree == 0]
        seen = 0
        while queue:
            node = queue.pop()
            seen += 1
            for child in self.children(node):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        return seen == len(self.nodes)


def oracle_d_separated(graph: OracleGraph, x: str, y: str, z: set[str]) -> bool:
    """d-separation via ancestral moralization (Lauritzen et al., 1990).

    X ⊥ Y | Z in DAG G iff X and Y are disconnected in the moralized ancestral
    graph of Z and {X, Y} (with Z removed). This is a completely different route to
    the answer than the Bayes-ball walk.
    """
    assert x not in z and y not in z
    closed = {x, y, *z} | graph.ancestors({x, y, *z})
    # Ancestral graph: keep edges of G among the closed set.
    edges = {(s, t) for s, t in graph.edges if s in closed and t in closed}
    # Moralization: marry parents of common children, then drop directions.
    moral: set[frozenset[str]] = set()
    by_child: dict[str, set[str]] = {}
    for s, t in edges:
        by_child.setdefault(t, set()).add(s)
        moral.add(frozenset({s, t}))
    for parents in by_child.values():
        for a, b in itertools.combinations(sorted(parents), 2):
            moral.add(frozenset({a, b}))
    # Undirected reachability from x with all nodes of z removed.
    adjacency: dict[str, set[str]] = {node: set() for node in closed}
    for pair in moral:
        a, b = tuple(pair)
        adjacency[a].add(b)
        adjacency[b].add(a)
    seen = {x}
    stack = [x]
    while stack:
        node = stack.pop()
        for nxt in adjacency[node]:
            if nxt in z or nxt in seen:
                continue
            seen.add(nxt)
            stack.append(nxt)
    return y not in seen


def _all_dags_on(nodes: list[str]) -> list[OracleGraph]:
    """Every DAG over the given ordered node list (exhaustive on ≤4 nodes)."""
    pairs = [(a, b) for a, b in itertools.combinations(nodes, 2)]
    graphs = []
    # Three options per unordered pair: no edge, forward, backward - 3^6 = 729
    # candidates on 4 nodes, of which the 546 acyclic ones are the labelled DAGs.
    for choice in itertools.product((None, "fwd", "bwd"), repeat=len(pairs)):
        edges: set[tuple[str, str]] = set()
        for (a, b), direction in zip(pairs, choice, strict=True):
            if direction == "fwd":
                edges.add((a, b))
            elif direction == "bwd":
                edges.add((b, a))
        graph = OracleGraph(nodes, edges)
        if graph.is_acyclic():
            graphs.append(graph)
    return graphs


def _random_dag(nodes: list[str], density: float, rng: random.Random) -> OracleGraph:
    """Random DAG by random topological order + independent edge draws."""
    order = nodes[:]
    rng.shuffle(order)
    edges: set[tuple[str, str]] = set()
    for i, a in enumerate(order):
        for b in order[i + 1 :]:
            if rng.random() < density:
                edges.add((a, b))
    return OracleGraph(nodes, edges)


def _as_dag(graph: OracleGraph) -> DAG:
    return DAG(graph.nodes, sorted(graph.edges))


def _oracle_cross_check(nodes: list[str], graphs: list[OracleGraph], subset_cap: int | None) -> int:
    """Compare engine and oracle over pairs and conditioning subsets. Returns query count."""
    checked = 0
    for graph in graphs:
        dag = _as_dag(graph)
        for x, y in itertools.combinations(nodes, 2):
            others = [node for node in nodes if node not in {x, y}]
            subsets = itertools.chain.from_iterable(
                itertools.combinations(others, size) for size in range(len(others) + 1)
            )
            if subset_cap is not None:
                subsets = list(subsets)[:subset_cap]
            for conditioning in subsets:
                z = set(conditioning)
                engine = d_separated(dag, x, y, conditioning).d_separated
                reference = oracle_d_separated(graph, x, y, z)
                assert engine == reference, (
                    f"Engine/oracle disagreement on nodes={graph.nodes} "
                    f"edges={sorted(graph.edges)} x={x} y={y} z={sorted(z)}: "
                    f"engine={engine} oracle={reference}"
                )
                checked += 1
    return checked


# --------------------------------------------------------------------------- #
# Known-answer fixtures
# --------------------------------------------------------------------------- #


def test_chain_x_m_y():
    dag = DAG(["x", "m", "y"], [("x", "m"), ("m", "y")])
    assert d_separated(dag, "x", "y", []).d_separated is False
    assert d_separated(dag, "x", "y", ["m"]).d_separated is True
    assert d_separated(dag, "x", "y", ["m"]).conditioning == ["m"]


def test_fork_x_z_y():
    dag = DAG(["x", "z", "y"], [("z", "x"), ("z", "y")])
    assert d_separated(dag, "x", "y", []).d_separated is False
    assert d_separated(dag, "x", "y", ["z"]).d_separated is True


def test_collider_x_c_y():
    dag = DAG(["x", "c", "y"], [("x", "c"), ("y", "c")])
    assert d_separated(dag, "x", "y", []).d_separated is True
    assert d_separated(dag, "x", "y", ["c"]).d_separated is False


def test_collider_descendant_reopens_the_path():
    dag = DAG(["x", "c", "y", "d"], [("x", "c"), ("y", "c"), ("c", "d")])
    assert d_separated(dag, "x", "y", []).d_separated is True
    # Conditioning on a *descendant* of the collider behaves like conditioning
    # on the collider itself: the path opens.
    assert d_separated(dag, "x", "y", ["d"]).d_separated is False
    assert d_separated(dag, "x", "y", ["c"]).d_separated is False


def test_multiple_interacting_paths_m_bias():
    # M-bias: X ← A → C ← B → Y with the X→Y direct edge absent.
    dag = DAG(["x", "y", "a", "b", "c"], [("a", "x"), ("a", "c"), ("b", "c"), ("b", "y")])
    assert d_separated(dag, "x", "y", []).d_separated is True  # collider C blocks
    assert d_separated(dag, "x", "y", ["c"]).d_separated is False  # opens
    assert d_separated(dag, "x", "y", ["a"]).d_separated is True  # blocks at A
    assert d_separated(dag, "x", "y", ["b"]).d_separated is True  # blocks at B
    assert d_separated(dag, "x", "y", ["a", "b"]).d_separated is True


def test_butterfly_bias():
    # A dense mixed graph exercising chains, forks, colliders and a collider
    # descendant at once: U → A, U → B, U → C, D → C, A → X, B → Y, X → Y,
    # C → X.
    dag = DAG(
        ["u", "a", "b", "x", "y", "c", "d"],
        [
            ("u", "a"),
            ("u", "b"),
            ("u", "c"),
            ("d", "c"),
            ("a", "x"),
            ("b", "y"),
            ("x", "y"),
            ("c", "x"),
        ],
    )
    # The direct edge X → Y can never be blocked.
    assert d_separated(dag, "x", "y", []).d_separated is False
    assert d_separated(dag, "x", "y", ["a"]).d_separated is False
    # D → C → X → Y is an active directed path unconditionally.
    assert d_separated(dag, "d", "y", []).d_separated is False
    # Conditioning on C blocks the chain; but D → C ← U → B → Y then opens
    # through the now-activated collider.
    assert d_separated(dag, "d", "y", ["c"]).d_separated is False
    # A and B: connected through U or through the collider Y; conditioning on
    # U blocks the fork, and Y (a collider, unconditioned) blocks the rest.
    assert d_separated(dag, "a", "b", []).d_separated is False
    assert d_separated(dag, "a", "b", ["u"]).d_separated is True
    # D and A are separated unconditionally (X is an unconditioned collider),
    # but conditioning on Y - a descendant of X - activates X and connects them.
    assert d_separated(dag, "d", "a", []).d_separated is True
    assert d_separated(dag, "d", "a", ["y"]).d_separated is False
    # D and B are separated unconditionally (Y blocks), but conditioning on X
    # - a *descendant of the collider C* on D → C ← U → B - activates C and
    # opens that path even though X itself is not on it.
    assert d_separated(dag, "d", "b", []).d_separated is True
    assert d_separated(dag, "d", "b", ["x"]).d_separated is False


def test_direct_connection_survives_conditioning_on_colliders():
    dag = DAG(["x", "y", "c"], [("x", "y"), ("x", "c"), ("y", "c")])
    # The direct edge X → Y can never be blocked by conditioning.
    for conditioning in ([], ["c"]):
        assert d_separated(dag, "x", "y", conditioning).d_separated is False


def test_disconnected_components_are_separated():
    dag = DAG(["x", "y", "p", "q"], [("x", "p"), ("y", "q")])
    assert d_separated(dag, "x", "y", []).d_separated is True
    assert d_separated(dag, "p", "q", ["x", "y"]).d_separated is True
    # Conditioning on unrelated components does not connect anything.
    assert d_separated(dag, "x", "q", ["p", "y"]).d_separated is True


def test_empty_graph_and_single_node_queries():
    dag = DAG(["solo"], [])
    # A single node has no distinct partner to query, so only errors exist.
    with pytest.raises(DSeparationQueryError):
        d_separated(dag, "solo", "solo", [])


def test_descendant_of_chain_node_does_not_block():
    # A descendant of a *non-collider* is not on the path: conditioning on it
    # does not block a chain (in contrast to collider descendants, which do
    # open colliders). X → M → Y stays active when M2 (M's child) is observed.
    dag = DAG(["x", "m", "y", "m2"], [("x", "m"), ("m", "y"), ("m", "m2")])
    assert d_separated(dag, "x", "y", ["m2"]).d_separated is False
    assert d_separated(dag, "x", "y", ["m"]).d_separated is True


def test_query_errors_are_structured():
    dag = DAG(["x", "y", "z"], [("x", "y")])
    with pytest.raises(DSeparationQueryError) as same:
        d_separated(dag, "x", "x", [])
    assert same.value.code == "same_node"
    with pytest.raises(DSeparationQueryError) as unknown:
        d_separated(dag, "x", "nope", [])
    assert unknown.value.code == "unknown_node"
    with pytest.raises(DSeparationQueryError) as endpoint:
        d_separated(dag, "x", "y", ["x"])
    assert endpoint.value.code == "conditioning_contains_endpoint"
    with pytest.raises(DSeparationQueryError) as cond_unknown:
        d_separated(dag, "x", "y", ["ghost"])
    assert cond_unknown.value.code == "unknown_node"


def test_repeated_conditioning_ids_are_deduplicated_deterministically():
    dag = DAG(["x", "y", "z", "w"], [("x", "z"), ("z", "y"), ("x", "w")])
    once = d_separated(dag, "x", "y", ["z"])
    twice = d_separated(dag, "x", "y", ["z", "z"])
    assert once.d_separated == twice.d_separated is True
    assert twice.conditioning == ["z"]


def test_dag_container_rejects_duplicates_self_loops_and_missing_endpoints():
    with pytest.raises(DSeparationQueryError):
        DAG(["a", "a", "b"], [])
    with pytest.raises(DSeparationQueryError):
        DAG(["a"], [("a", "a")])
    with pytest.raises(DSeparationQueryError):
        DAG(["a"], [("a", "ghost")])


def test_backdoor_graph_keeps_incoming_and_drops_outgoing_edges():
    # The distinction that matters: removing edges *out of* X (backdoor graph)
    # keeps X ← Z alive and removes X → M.
    dag = DAG(["x", "y", "z", "m"], [("z", "x"), ("x", "y"), ("x", "m"), ("m", "y")])
    backdoor = dag.without_outgoing_from("x")
    assert ("z", "x") in backdoor.edges
    assert ("x", "y") not in backdoor.edges
    assert ("x", "m") not in backdoor.edges
    assert ("m", "y") in backdoor.edges
    # In the backdoor graph, X and Y are separated given {z} - the basis of
    # the backdoor criterion - but not unconditionally (path X ← Z → ? …).
    assert d_separated(backdoor, "x", "y", ["z"]).d_separated is True


def test_reachability_excludes_conditioned_nodes():
    dag = DAG(["x", "m", "y"], [("x", "m"), ("m", "y")])
    reachable = reachable_from(dag, "x", set())
    assert reachable == {"m", "y"}
    assert reachable_from(dag, "x", {"m"}) == set()


# --------------------------------------------------------------------------- #
# Independent oracle cross-checks (moralization ≠ Bayes-ball by construction)
# --------------------------------------------------------------------------- #


def test_exhaustive_cross_check_all_dags_on_four_nodes():
    nodes = ["a", "b", "c", "d"]
    graphs = _all_dags_on(nodes)
    # Sanity: the count of labelled DAGs on 4 nodes is 543 (OEIS A003024).
    assert len(graphs) == 543
    checked = _oracle_cross_check(nodes, graphs, subset_cap=None)
    # 543 graphs x 6 pairs x 4 conditioning subsets = 13 032 queries.
    assert checked == 543 * 6 * 4


def test_cross_check_seeded_dags_on_five_and_six_nodes():
    rng = random.Random(84721)
    nodes5 = ["a", "b", "c", "d", "e"]
    graphs5 = [_random_dag(nodes5, density, rng) for density in (0.15, 0.3, 0.5, 0.7) for _ in range(15)]
    checked5 = _oracle_cross_check(nodes5, graphs5, subset_cap=8)
    assert checked5 > 0

    nodes6 = ["a", "b", "c", "d", "e", "f"]
    graphs6 = [_random_dag(nodes6, density, rng) for density in (0.15, 0.35, 0.55) for _ in range(10)]
    checked6 = _oracle_cross_check(nodes6, graphs6, subset_cap=6)
    assert checked6 > 0


def test_oracle_agrees_with_known_answers_itself():
    """The oracle is not trusted blindly either: it must reproduce textbook answers."""
    chain = OracleGraph(["x", "m", "y"], {("x", "m"), ("m", "y")})
    assert oracle_d_separated(chain, "x", "y", set()) is False
    assert oracle_d_separated(chain, "x", "y", {"m"}) is True
    collider = OracleGraph(["x", "c", "y"], {("x", "c"), ("y", "c")})
    assert oracle_d_separated(collider, "x", "y", set()) is True
    assert oracle_d_separated(collider, "x", "y", {"c"}) is False
    descendant = OracleGraph(["x", "c", "y", "d"], {("x", "c"), ("y", "c"), ("c", "d")})
    assert oracle_d_separated(descendant, "x", "y", {"d"}) is False
