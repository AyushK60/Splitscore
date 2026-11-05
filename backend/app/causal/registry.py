"""Bounded in-memory causal-graph registry with dataset ownership.

A causal graph belongs to the dataset it was drawn for, in the same way a Study
Card does. The registry enforces that ownership on every read and write, keeps
a bounded number of graphs, and — because the underlying store expires datasets
— makes graph lifetime follow dataset lifetime: a graph whose dataset is no
longer in memory is unreachable, and dataset eviction prunes its graphs.

Nothing is persisted. That is stated in every payload rather than discovered
after a restart. The safe durability story is the versioned JSON export/import
contract in :mod:`app.causal.io`, which is validated server-side and can never
execute code or carry dataset rows.

Validation happens *before* any mutation, so an invalid create or update
request raises and leaves the previously stored graph untouched.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.audit.dataset import Dataset
from app.core.errors import NotFoundError, ValidationFailure
from app.causal.io import build_export, parse_export
from app.causal.schema import (
    MAX_GRAPHS,
    CausalGraphSpec,
    graph_fingerprint,
    normalise_assumptions,
)
from app.causal.validation import validate_spec

STORAGE_NOTE = (
    "Causal graphs live in this server's memory alongside the dataset. They expire with it and "
    "are lost when the process restarts, so export a graph you need to keep. The export contains "
    "graph metadata and assumptions only — never dataset rows."
)


@dataclass
class CausalGraphRecord:
    graph_id: str
    dataset_id: str
    dataset_fingerprint_sha256: str
    spec: CausalGraphSpec
    revision: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def fingerprint(self) -> str:
        return graph_fingerprint(self.spec)


class CausalGraphRegistry:
    """Thread-safe, bounded registry of causal graphs keyed by graph id."""

    def __init__(self, max_entries: int = MAX_GRAPHS) -> None:
        self._records: dict[str, CausalGraphRecord] = {}
        self._max = max_entries
        self._lock = threading.RLock()

    # -- internal helpers ---------------------------------------------------- #

    def _prune_orphaned(self, live_dataset_ids: set[str]) -> list[str]:
        removed = [
            graph_id
            for graph_id, record in self._records.items()
            if record.dataset_id not in live_dataset_ids
        ]
        for graph_id in removed:
            del self._records[graph_id]
        return removed

    def _enforce_bound(self) -> None:
        while len(self._records) >= self._max:
            oldest = min(self._records, key=lambda key: self._records[key].updated_at)
            del self._records[oldest]

    def _validated_spec(
        self,
        spec: CausalGraphSpec,
        dataset: Dataset,
        *,
        stored_fingerprint: str | None = None,
    ) -> CausalGraphSpec:
        spec = spec.model_copy(update={"assumptions": normalise_assumptions(spec.assumptions)})
        result = validate_spec(
            spec,
            dataset_columns=list(dataset.columns),
            stored_dataset_fingerprint=stored_fingerprint,
            current_dataset_fingerprint=dataset.fingerprint_sha256,
        )
        if not result.ok:
            raise ValidationFailure(
                "The causal graph specification failed validation and was not stored.",
                details={
                    **result.to_payload(),
                    "fix": "Resolve the listed errors and resubmit. Nothing was changed.",
                },
            )
        return spec

    # -- operations ----------------------------------------------------------- #

    def create(self, dataset: Dataset, spec: CausalGraphSpec) -> CausalGraphRecord:
        with self._lock:
            validated = self._validated_spec(spec, dataset)
            graph_id = f"cgraph-{uuid.uuid4().hex[:10]}"
            record = CausalGraphRecord(
                graph_id=graph_id,
                dataset_id=dataset.dataset_id,
                dataset_fingerprint_sha256=dataset.fingerprint_sha256,
                spec=validated,
            )
            self._enforce_bound()
            self._records[graph_id] = record
            return record

    def import_spec(self, dataset: Dataset, payload: dict[str, Any]) -> CausalGraphRecord:
        """Import an export-file payload as a *new* graph for this dataset.

        The imported file never carries a graph id or revision: those belong to
        the receiving registry. Cross-dataset reuse is caught by the ordinary
        column-reference validation, because an import target with different
        columns fails with ``unknown_column``.
        """
        spec = parse_export(payload)
        return self.create(dataset, spec)

    def get(self, dataset_id: str, graph_id: str) -> CausalGraphRecord:
        with self._lock:
            record = self._records.get(graph_id)
            if record is None or record.dataset_id != dataset_id:
                raise NotFoundError(
                    "No causal graph with that id exists for this dataset.",
                    details={
                        "graph_id": graph_id,
                        "dataset_id": dataset_id,
                        "fix": "List the dataset's causal graphs to see valid ids.",
                    },
                )
            return record

    def list_for_dataset(self, dataset_id: str) -> list[CausalGraphRecord]:
        with self._lock:
            return sorted(
                (record for record in self._records.values() if record.dataset_id == dataset_id),
                key=lambda record: record.created_at,
            )

    def update(
        self,
        dataset: Dataset,
        graph_id: str,
        spec: CausalGraphSpec,
    ) -> CausalGraphRecord:
        with self._lock:
            record = self.get(dataset.dataset_id, graph_id)
            validated = self._validated_spec(
                spec,
                dataset,
                stored_fingerprint=record.dataset_fingerprint_sha256,
            )
            record.spec = validated
            record.revision += 1
            record.updated_at = datetime.now(UTC)
            return record

    def delete(self, dataset_id: str, graph_id: str) -> bool:
        with self._lock:
            self.get(dataset_id, graph_id)
            del self._records[graph_id]
            return True

    def prune_for_datasets(self, live_dataset_ids: set[str]) -> list[str]:
        """Drop graphs whose dataset is gone. Called when datasets expire."""
        with self._lock:
            return self._prune_orphaned(live_dataset_ids)

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


def graph_payload(record: CausalGraphRecord, dataset: Dataset) -> dict[str, Any]:
    """Serialise a graph record for the API, including validation and derived structure."""
    from app.core.version import APP_NAME, APP_VERSION
    from app.causal.schema import CAUSAL_GRAPH_SCHEMA_VERSION, assumptions_payload

    validation = validate_spec(
        record.spec,
        dataset_columns=list(dataset.columns),
        stored_dataset_fingerprint=record.dataset_fingerprint_sha256,
        current_dataset_fingerprint=dataset.fingerprint_sha256,
    )

    column_types = {
        str(column): dataset.frame[column].dtype.name for column in dataset.columns
    }
    nodes = []
    for node in record.spec.nodes:
        item = node.model_dump(mode="json")
        if node.column:
            item["resolved_column_type"] = column_types.get(node.column)
        derived = validation.derived["nodes"].get(node.node_id, {})
        item["derived_structure"] = derived
        nodes.append(item)

    return {
        "graph_id": record.graph_id,
        "dataset_id": record.dataset_id,
        "dataset_name": dataset.name,
        "dataset_fingerprint_sha256": record.dataset_fingerprint_sha256,
        "schema_version": CAUSAL_GRAPH_SCHEMA_VERSION,
        "revision": record.revision,
        "created_at_utc": record.created_at.astimezone(UTC).isoformat(timespec="seconds"),
        "updated_at_utc": record.updated_at.astimezone(UTC).isoformat(timespec="seconds"),
        "spec_fingerprint_sha256": record.fingerprint,
        "name": record.spec.name,
        "description": record.spec.description,
        "nodes": nodes,
        "edges": [edge.model_dump(mode="json") for edge in record.spec.edges],
        "analysis": record.spec.analysis.model_dump(mode="json"),
        "assumptions": assumptions_payload(record.spec.assumptions),
        "validation": validation.to_payload(),
        "validation_scope_note": (
            "A passing validation establishes only that the graph is a well-formed directed "
            "acyclic graph whose references resolve. It is not evidence that the assumed causal "
            "structure is true, and no causal effect is estimated at this stage."
        ),
        "storage_note": STORAGE_NOTE,
        "app": {"name": APP_NAME, "version": APP_VERSION},
    }


def graph_summary(record: CausalGraphRecord, dataset: Dataset) -> dict[str, Any]:
    validation = validate_spec(
        record.spec,
        dataset_columns=list(dataset.columns),
        stored_dataset_fingerprint=record.dataset_fingerprint_sha256,
        current_dataset_fingerprint=dataset.fingerprint_sha256,
    )
    return {
        "graph_id": record.graph_id,
        "name": record.spec.name,
        "description": record.spec.description,
        "revision": record.revision,
        "node_count": len(record.spec.nodes),
        "edge_count": len(record.spec.edges),
        "analysis": record.spec.analysis.model_dump(mode="json"),
        "spec_fingerprint_sha256": record.fingerprint,
        "created_at_utc": record.created_at.astimezone(UTC).isoformat(timespec="seconds"),
        "updated_at_utc": record.updated_at.astimezone(UTC).isoformat(timespec="seconds"),
        "validation_ok": validation.ok,
        "error_count": len(validation.errors),
        "warning_count": len(validation.warnings),
    }


def export_payload(record: CausalGraphRecord, dataset: Dataset) -> dict[str, Any]:
    """Versioned export envelope; metadata and assumptions only, never rows."""
    return build_export(record, dataset)


__all__ = [
    "CausalGraphRecord",
    "CausalGraphRegistry",
    "MAX_GRAPHS",
    "STORAGE_NOTE",
    "export_payload",
    "graph_payload",
    "graph_summary",
]
