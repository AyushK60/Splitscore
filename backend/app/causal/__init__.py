"""Causal graph foundation.

This package holds the user-declared causal graph domain model: validated,
versioned DAG specifications, the structural validation engine, the assumption
registry and the bounded in-memory graph store.

Scientific boundary: everything in this package describes *assumptions the user
declares*, not facts the application learned from data. No causal effect is
estimated here; identification and estimation belong to later stages.
"""

from app.causal.schema import (
    CAUSAL_GRAPH_SCHEMA_VERSION,
    MAX_ASSUMPTIONS,
    MAX_EDGES,
    MAX_NODES,
    AnalysisScope,
    AssumptionRecord,
    CausalEdge,
    CausalGraphSpec,
    CausalNode,
    LayoutPosition,
    canonical_scientific_json,
    graph_fingerprint,
)

__all__ = [
    "CAUSAL_GRAPH_SCHEMA_VERSION",
    "MAX_ASSUMPTIONS",
    "MAX_EDGES",
    "MAX_NODES",
    "AnalysisScope",
    "AssumptionRecord",
    "CausalEdge",
    "CausalGraphSpec",
    "CausalNode",
    "LayoutPosition",
    "canonical_scientific_json",
    "graph_fingerprint",
]
