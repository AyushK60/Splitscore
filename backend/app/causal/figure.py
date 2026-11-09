"""Publication-grade SVG figure of the stored causal graph.

A deterministic, self-contained rendering of the graph **specification** -
not a screenshot of the interactive canvas. The figure is drawn from the
same data the dossier reports: node roles, edges, recorded assumptions,
treatment/outcome highlighting, and a caption that carries the graph
fingerprint, the generation time and the standing caveat that the drawn
structure is an assumption, not empirical proof.

Layout: recorded canvas positions (a display-only concern, deliberately
excluded from the scientific fingerprint) are used when present and sane;
otherwise a deterministic layered layout is derived from the graph topology
(longest-path layering with alphabetical tie-breaking). Unobserved nodes are
rendered dashed, so the figure never silently presents an imputed variable
as a measured one.
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape

FIGURE_SCHEMA_VERSION = "1.0.0"

FIGURE_CAVEAT = (
    "This figure depicts the assumed causal structure as recorded in SplitScope. Every edge is "
    "an assumption about how the world works, not empirical proof; identification and estimation "
    "results inherit these assumptions."
)

NODE_W, NODE_H = 148.0, 40.0
CANVAS_MARGIN = 48.0
LAYER_GAP = 120.0
ROW_GAP = 58.0


def _layered_positions(spec: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Deterministic topological layering for nodes without recorded layout."""
    node_ids = [str(node["node_id"]) for node in spec.get("nodes", [])]
    edges = [(str(edge["source"]), str(edge["target"])) for edge in spec.get("edges", [])]
    incoming: dict[str, int] = {node_id: 0 for node_id in node_ids}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for source, target in edges:
        if source in incoming and target in incoming:
            incoming[target] += 1
            adjacency[source].append(target)
    # Kahn layering with deterministic tie-breaks.
    layer: dict[str, int] = {}
    frontier = sorted(node_id for node_id, degree in incoming.items() if degree == 0)
    depth = 0
    seen = 0
    while frontier:
        for node_id in frontier:
            layer[node_id] = depth
        seen += len(frontier)
        nxt: set[str] = set()
        for node_id in frontier:
            for target in adjacency[node_id]:
                nxt.add(target)
        frontier = sorted(nxt)
        depth += 1
        if seen > len(node_ids) * 4:  # cycle guard; validation rejects cycles anyway
            break
    for node_id in node_ids:
        layer.setdefault(node_id, depth)
    by_layer: dict[int, list[str]] = {}
    for node_id, layer_index in layer.items():
        by_layer.setdefault(layer_index, []).append(node_id)
    positions: dict[str, tuple[float, float]] = {}
    for layer_index in sorted(by_layer):
        for row, node_id in enumerate(sorted(by_layer[layer_index])):
            positions[node_id] = (
                CANVAS_MARGIN + layer_index * LAYER_GAP,
                CANVAS_MARGIN + row * ROW_GAP,
            )
    return positions


def _positions(spec: dict[str, Any]) -> dict[str, tuple[float, float]]:
    recorded: dict[str, tuple[float, float]] = {}
    for node in spec.get("nodes", []):
        layout = node.get("layout")
        if isinstance(layout, dict):
            try:
                x = float(layout.get("x"))
                y = float(layout.get("y"))
            except (TypeError, ValueError):
                continue
            recorded[str(node["node_id"])] = (x, y)
    if set(recorded) >= {str(node["node_id"]) for node in spec.get("nodes", [])} and recorded:
        return recorded
    derived = _layered_positions(spec)
    # Merge: recorded positions win for the nodes that have them.
    derived.update(recorded)
    return derived


def _edge_path(x1: float, y1: float, x2: float, y2: float) -> str:
    """A straight arrow clipped to the node boxes."""
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / length, dy / length
    start_x = x1 + ux * (NODE_W / 2)
    start_y = y1 + uy * (NODE_H / 2)
    end_x = x2 - ux * (NODE_W / 2 + 6)
    end_y = y2 - uy * (NODE_H / 2 + 6)
    return f"M {start_x:.1f} {start_y:.1f} L {end_x:.1f} {end_y:.1f}"


def build_graph_figure_svg(spec: dict[str, Any], record: dict[str, Any]) -> str:
    """The complete standalone SVG document for one stored graph."""
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])
    analysis = spec.get("analysis") or {}
    treatment = analysis.get("treatment")
    outcome = analysis.get("outcome")
    positions = _positions(spec)
    if not positions:
        return ""
    xs = [x for x, _ in positions.values()]
    ys = [y for y, _ in positions.values()]
    width = max(xs) + NODE_W + CANVAS_MARGIN
    height = max(ys) + NODE_H + CANVAS_MARGIN + 88.0

    def node_label(node: dict[str, Any]) -> str:
        return str(node.get("label") or node.get("node_id"))

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="ui-monospace, monospace">',
        "<defs>"
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#57534e"/>'
        "</marker></defs>",
        '<rect width="100%" height="100%" fill="#faf6f0"/>',
        f'<text x="{CANVAS_MARGIN:.0f}" y="28" font-size="15" font-weight="600" fill="#1c1917">'
        f"{escape(str(spec.get('name') or 'Causal graph'))}</text>",
        f'<text x="{CANVAS_MARGIN:.0f}" y="46" font-size="11" fill="#78716c">'
        f"assumed structure · spec fingerprint {escape(str(record.get('spec_fingerprint_sha256') or ''))[:16]}…"
        "</text>",
    ]
    for edge in edges:
        source, target = str(edge["source"]), str(edge["target"])
        if source not in positions or target not in positions:
            continue
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        parts.append(
            f'<path d="{_edge_path(x1, y1, x2, y2)}" fill="none" stroke="#57534e" '
            'stroke-width="1.4" marker-end="url(#arrow)"/>'
        )
    for node in nodes:
        node_id = str(node["node_id"])
        if node_id not in positions:
            continue
        x, y = positions[node_id]
        observed = node.get("observed", True)
        role_class = ""
        if node_id == treatment:
            role_class = "#0a6d7d"
        elif node_id == outcome:
            role_class = "#b4562a"
        rect_fill = "#ffffff"
        rect_stroke = role_class or "#1c1917"
        dash = "" if observed else ' stroke-dasharray="4 3"'
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{NODE_W:.0f}" height="{NODE_H:.0f}" rx="8" '
            f'fill="{rect_fill}" stroke="{rect_stroke}" stroke-width="1.6"{dash}/>'
        )
        label = node_label(node)
        parts.append(
            f'<text x="{x + NODE_W / 2:.1f}" y="{y + 18:.1f}" text-anchor="middle" '
            f'font-size="12.5" fill="#1c1917">{escape(label)}</text>'
        )
        role = "treatment" if node_id == treatment else "outcome" if node_id == outcome else (
            "unobserved" if not observed else ""
        )
        if role:
            parts.append(
                f'<text x="{x + NODE_W / 2:.1f}" y="{y + 32:.1f}" text-anchor="middle" '
                f'font-size="9.5" fill="#78716c">{escape(role)}</text>'
            )
    assumptions = spec.get("assumptions") or []
    caption_y = max(ys) + NODE_H + 34.0
    parts.append(
        f'<text x="{CANVAS_MARGIN:.0f}" y="{caption_y:.0f}" font-size="10.5" fill="#44403c">'
        f"Edges recorded: {len(edges)} · nodes: {len(nodes)} · "
        f"assumptions documented: {len(assumptions)}</text>"
    )
    parts.append(
        f'<text x="{CANVAS_MARGIN:.0f}" y="{caption_y + 16:.0f}" font-size="9.5" fill="#78716c">'
        f"{escape(FIGURE_CAVEAT)}</text>"
    )
    parts.append(
        f'<text x="{CANVAS_MARGIN:.0f}" y="{caption_y + 32:.0f}" font-size="9.5" fill="#78716c">'
        f"SplitScope causal graph figure · schema {FIGURE_SCHEMA_VERSION} · "
        f"generated from the stored graph only</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


__all__ = ["FIGURE_CAVEAT", "FIGURE_SCHEMA_VERSION", "build_graph_figure_svg"]
