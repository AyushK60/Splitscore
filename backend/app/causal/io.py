"""Versioned JSON export/import contract for causal graphs.

The contract is deliberately narrow, in both directions:

* **Export** writes a schema-versioned envelope with a marker ``export_kind``.
  It carries graph metadata, assumptions and display layout only - never
  dataset rows, never the dataset itself.
* **Import** accepts only JSON that declares the marker and the exact schema
  version this build reads, and parses it through the same Pydantic models the
  API uses. There is no pickle, no templating language and no executable
  definition anywhere in the contract: a malformed or foreign file fails with a
  structured validation error.

Import always creates a *new* graph in the receiving registry. The file's
original graph id, revision history and dataset identity are not carried over,
so an import can never overwrite another graph or quietly bind a graph to a
dataset it was not written for - column references are validated against the
receiving dataset and fail with ``unknown_column`` when they do not resolve.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from pydantic import ValidationError

from app.audit.dataset import Dataset
from app.core.errors import ValidationFailure
from app.causal.schema import (
    CAUSAL_GRAPH_SCHEMA_VERSION,
    EXPORT_KIND,
    CausalGraphSpec,
    graph_fingerprint,
)

EXPORT_NOTE = (
    "Causal graph export: graph structure, assumptions and layout only. No dataset rows are "
    "included and the file cannot recreate the uploaded data. Re-importing binds the graph to "
    "the dataset you import it against."
)


def build_export(record, dataset: Dataset) -> dict[str, Any]:
    """Build the export envelope from a stored graph record."""
    return {
        "export_kind": EXPORT_KIND,
        "causal_graph_schema_version": CAUSAL_GRAPH_SCHEMA_VERSION,
        "exported_at_utc": record.updated_at.astimezone(UTC).isoformat(timespec="seconds"),
        "graph": record.spec.model_dump(mode="json"),
        "origin": {
            "source_graph_id": record.graph_id,
            "source_revision": record.revision,
            "dataset_name": dataset.name,
            "dataset_fingerprint_sha256": record.dataset_fingerprint_sha256,
            "spec_fingerprint_sha256": record.fingerprint,
        },
        "note": EXPORT_NOTE,
    }


def parse_export(payload: dict[str, Any]) -> CausalGraphSpec:
    """Validate an import payload and return its specification.

    Raises :class:`~app.core.errors.ValidationFailure` with actionable details
    for anything that is not a graph this build understands.
    """
    if not isinstance(payload, dict):
        raise ValidationFailure(
            "The import payload must be a JSON object, not another JSON type.",
            details={"received_type": type(payload).__name__},
        )
    if payload.get("export_kind") != EXPORT_KIND:
        raise ValidationFailure(
            "This file is not a SplitScope causal-graph export, so it will not be interpreted "
            "as one.",
            details={
                "expected_export_kind": EXPORT_KIND,
                "received_export_kind": payload.get("export_kind"),
            },
        )
    declared_version = payload.get("causal_graph_schema_version")
    if declared_version != CAUSAL_GRAPH_SCHEMA_VERSION:
        raise ValidationFailure(
            f"This build imports causal graph schema {CAUSAL_GRAPH_SCHEMA_VERSION!r}; the file "
            f"declares {declared_version!r}.",
            details={
                "expected_schema_version": CAUSAL_GRAPH_SCHEMA_VERSION,
                "received_schema_version": declared_version,
            },
        )
    graph = payload.get("graph")
    if not isinstance(graph, dict):
        raise ValidationFailure(
            "The export file has no 'graph' object to import.",
            details={"fix": "Re-export the graph from the build that created it."},
        )
    try:
        spec = CausalGraphSpec.model_validate(graph)
    except ValidationError as exc:
        problems = [
            {
                "location": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", "invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        raise ValidationFailure(
            "The imported graph specification does not match the schema this build reads.",
            details={"problems": problems[:20], "problem_count": len(problems)},
        ) from exc
    return spec


__all__ = ["EXPORT_NOTE", "build_export", "parse_export"]
