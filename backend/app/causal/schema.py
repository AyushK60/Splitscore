"""Versioned, validated causal graph specifications.

The specification is the *scientific* object: nodes, directed assumed edges,
the analysis scope and the recorded assumptions. Screen coordinates live on the
node as an optional, display-only ``layout`` block and are excluded from the
graph fingerprint, so a graph's scientific identity never depends on how it was
last arranged on a canvas (S8B will edit positions freely without silently
changing what the graph claims).

Conventions mirrored from the research module:

* Pydantic models with ``extra="forbid"`` so a typo in a payload is an error,
  never a silently ignored field.
* A single ``CAUSAL_GRAPH_SCHEMA_VERSION`` echoed in every payload and enforced
  on import.
* Explicit size limits; oversized input is rejected with a reason, never
  silently truncated.

What a node's ``kind`` means: it is a *user-declared conceptual annotation*
("I hypothesise this is a mediator"). The validation engine separately derives
structural properties (ancestors, descendants, colliders, on-path status) from
the graph itself and reports both. A declared kind is never treated as proof of
the corresponding structural property.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: Version of the serialized causal-graph contract. Bump when the shape of the
#: specification changes in a backwards-incompatible way; imports of files
#: declaring another version are rejected rather than guessed at.
CAUSAL_GRAPH_SCHEMA_VERSION = "1.0.0"

#: Marker written into export files so an import endpoint can refuse foreign
#: JSON instead of interpreting it as a graph.
EXPORT_KIND = "splitscope-causal-graph"

MAX_NODES = 60
MAX_EDGES = 240
MAX_ASSUMPTIONS = 64
#: Bound on stored graphs per registry (mirrors MAX_STUDIES in the research module).
MAX_GRAPHS = 32

NODE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$")

NodeKind = Literal[
    "treatment",
    "outcome",
    "covariate",
    "mediator",
    "effect_modifier",
    "unobserved",
]

AssumptionCategory = Literal[
    "temporal_ordering",
    "causal_relationships",
    "unmeasured_confounding",
    "consistency",
    "exchangeability",
    "positivity",
    "selection",
    "measurement",
    "target_population",
]

#: User-declared assumption states. There is deliberately no "verified" state:
#: a declared assumption is a claim, and SplitScope never promotes it to an
#: empirical result.
AssumptionStatus = Literal[
    "declared",
    "not_assessed",
    "flagged_for_review",
    "unsupported",
]

ASSUMPTION_CATEGORY_LABELS: dict[str, str] = {
    "temporal_ordering": "Temporal ordering",
    "causal_relationships": "Hypothesised causal relationships",
    "unmeasured_confounding": "Potential unmeasured confounding",
    "consistency": "Consistency / well-defined intervention",
    "exchangeability": "(Conditional) exchangeability",
    "positivity": "Positivity / overlap",
    "selection": "Selection or sampling",
    "measurement": "Measurement limitations",
    "target_population": "Intended target population",
}

ASSUMPTION_STATUS_LABELS: dict[str, str] = {
    "declared": "Declared by you; not verified",
    "not_assessed": "Recorded, not yet assessed",
    "flagged_for_review": "Flagged for review",
    "unsupported": "Unsupported by the available information",
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LayoutPosition(_StrictModel):
    """Display-only canvas position. Never part of the scientific fingerprint."""

    x: float
    y: float


class CausalNode(_StrictModel):
    """One variable in the assumed causal structure."""

    node_id: str = Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$")
    label: str = Field(min_length=1, max_length=120)
    #: Dataset column this node is anchored to, if any. Hypothesised variables
    #: that have no measured column are legitimate and stay ``None``.
    column: str | None = Field(default=None, max_length=200)
    #: False only when the user explicitly declares a variable as unobserved.
    observed: bool = True
    #: Conceptual role as the user declares it. Reported separately from the
    #: structure-derived properties; never treated as evidence of them.
    kind: NodeKind = "covariate"
    description: str | None = Field(default=None, max_length=1000)
    layout: LayoutPosition | None = None

    @property
    def is_unobserved(self) -> bool:
        return not self.observed or self.kind == "unobserved"


class CausalEdge(_StrictModel):
    """One *assumed* directed causal relationship. Never a learned correlation."""

    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)
    rationale: str | None = Field(default=None, max_length=1000)
    reference: str | None = Field(default=None, max_length=500)


class AnalysisScope(_StrictModel):
    """The one treatment / one outcome pair the first causal workflow studies.

    Kept as its own object so multiple exposures or outcomes can be added later
    without reshaping the specification.
    """

    treatment: str | None = Field(default=None, max_length=80)
    outcome: str | None = Field(default=None, max_length=80)


class AssumptionRecord(_StrictModel):
    """One recorded scientific assumption behind the graph."""

    assumption_id: str = Field(min_length=1, max_length=80)
    category: AssumptionCategory
    status: AssumptionStatus = "not_assessed"
    source: str | None = Field(default=None, max_length=200)
    rationale: str | None = Field(default=None, max_length=1000)


class CausalGraphSpec(_StrictModel):
    """The complete, versioned causal graph specification."""

    schema_version: str = CAUSAL_GRAPH_SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    dataset_id: str = Field(min_length=1, max_length=80)
    nodes: list[CausalNode] = Field(default_factory=list, max_length=MAX_NODES)
    edges: list[CausalEdge] = Field(default_factory=list, max_length=MAX_EDGES)
    analysis: AnalysisScope = Field(default_factory=AnalysisScope)
    assumptions: list[AssumptionRecord] = Field(
        default_factory=list, max_length=MAX_ASSUMPTIONS
    )


def canonical_scientific_json(spec: CausalGraphSpec) -> str:
    """Deterministic JSON of the scientific content, layout coordinates excluded.

    Nodes are sorted by id, edges by (source, target) and assumptions by id, so
    two specifications that make the same scientific claims share a fingerprint
    regardless of the order they were entered in. Layout positions are display
    state, not science, and are excluded on purpose.
    """
    data = spec.model_dump(mode="json")
    data["nodes"] = sorted(data["nodes"], key=lambda node: node["node_id"])
    data["edges"] = sorted(data["edges"], key=lambda edge: (edge["source"], edge["target"]))
    data["assumptions"] = sorted(data["assumptions"], key=lambda item: item["assumption_id"])
    for node in data["nodes"]:
        node.pop("layout", None)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def graph_fingerprint(spec: CausalGraphSpec) -> str:
    """SHA-256 of the canonical scientific content."""
    return hashlib.sha256(canonical_scientific_json(spec).encode("utf-8")).hexdigest()


def new_assumption_id() -> str:
    import uuid

    return f"asmp-{uuid.uuid4().hex[:10]}"


def normalise_assumptions(
    assumptions: list[AssumptionRecord] | None,
) -> list[AssumptionRecord]:
    """Fill in generated ids for assumptions the client left unnamed."""
    result: list[AssumptionRecord] = []
    for item in assumptions or []:
        if not item.assumption_id or item.assumption_id.startswith("auto:"):
            item = item.model_copy(update={"assumption_id": new_assumption_id()})
        result.append(item)
    return result


def assumptions_payload(items: list[AssumptionRecord]) -> list[dict[str, Any]]:
    """Serialise assumptions with their human-readable labels."""
    return [
        {
            **item.model_dump(mode="json"),
            "category_label": ASSUMPTION_CATEGORY_LABELS.get(item.category, item.category),
            "status_label": ASSUMPTION_STATUS_LABELS.get(item.status, item.status),
        }
        for item in items
    ]


__all__ = [
    "ASSUMPTION_CATEGORY_LABELS",
    "ASSUMPTION_STATUS_LABELS",
    "AnalysisScope",
    "AssumptionCategory",
    "AssumptionRecord",
    "AssumptionStatus",
    "CAUSAL_GRAPH_SCHEMA_VERSION",
    "CausalEdge",
    "CausalGraphSpec",
    "CausalNode",
    "EXPORT_KIND",
    "LayoutPosition",
    "MAX_ASSUMPTIONS",
    "MAX_EDGES",
    "MAX_NODES",
    "NODE_ID_PATTERN",
    "NodeKind",
    "assumptions_payload",
    "canonical_scientific_json",
    "graph_fingerprint",
    "new_assumption_id",
    "normalise_assumptions",
]
