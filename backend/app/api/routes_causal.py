"""Causal graph routes (S8A foundation).

Every route is scoped to a dataset that still exists in the store, so a graph
can never be created against, read from, or attached to data the process no
longer holds — the same rule the study routes apply.

The routes expose only graph *authoring*: create, read, update, delete, list,
validate and export/import. No identification, adjustment-set or effect-estimation
endpoint exists at this stage; those belong to S8C and are deliberately absent.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.api.deps import get_context
from app.audit.dataset import Dataset
from app.causal.registry import (
    STORAGE_NOTE,
    CausalGraphRecord,
    export_payload,
    graph_payload,
    graph_summary,
)
from app.causal.schema import CAUSAL_GRAPH_SCHEMA_VERSION, CausalGraphSpec
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["causal"])


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GraphCreateRequest(_Model):
    graph: CausalGraphSpec


class GraphImportRequest(_Model):
    export_file: dict[str, Any]


def _dataset(dataset_id: str) -> Dataset:
    """Resolve the dataset or raise the store's typed expiry/not-found errors.

    Resolution also prunes graphs whose dataset has expired or been evicted, so
    graph lifetime follows dataset lifetime exactly as the payloads state.
    """
    context = get_context()
    # Prune graph orphans first: a dataset that has expired or been evicted is
    # not in the live set, so its graphs are removed before the lookup below
    # raises the store's typed 410.
    context.causal_graphs.prune_for_datasets(set(context.store.stats().dataset_ids))
    return context.store.get_dataset(dataset_id)


def _created_response(record: CausalGraphRecord, dataset: Dataset) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=graph_payload(record, dataset),
    )


@router.post("/datasets/{dataset_id}/causal-graphs", status_code=201)
def create_causal_graph(dataset_id: str, request: GraphCreateRequest) -> JSONResponse:
    context = get_context()
    dataset = _dataset(dataset_id)
    spec = request.graph.model_copy(update={"dataset_id": dataset.dataset_id})
    record = context.causal_graphs.create(dataset, spec)
    logger.info(
        "Causal graph %s created for dataset %s (%d nodes, %d edges)",
        record.graph_id,
        dataset_id,
        len(record.spec.nodes),
        len(record.spec.edges),
    )
    return _created_response(record, dataset)


@router.get("/datasets/{dataset_id}/causal-graphs")
def list_causal_graphs(dataset_id: str) -> dict[str, Any]:
    context = get_context()
    dataset = _dataset(dataset_id)
    records = context.causal_graphs.list_for_dataset(dataset.dataset_id)
    return {
        "dataset_id": dataset.dataset_id,
        "schema_version": CAUSAL_GRAPH_SCHEMA_VERSION,
        "graphs": [graph_summary(record, dataset) for record in records],
        "storage_note": STORAGE_NOTE,
    }


@router.get("/datasets/{dataset_id}/causal-graphs/{graph_id}")
def get_causal_graph(dataset_id: str, graph_id: str) -> dict[str, Any]:
    context = get_context()
    dataset = _dataset(dataset_id)
    record = context.causal_graphs.get(dataset.dataset_id, graph_id)
    return graph_payload(record, dataset)


@router.put("/datasets/{dataset_id}/causal-graphs/{graph_id}")
def update_causal_graph(
    dataset_id: str, graph_id: str, request: GraphCreateRequest
) -> dict[str, Any]:
    context = get_context()
    dataset = _dataset(dataset_id)
    spec = request.graph.model_copy(update={"dataset_id": dataset.dataset_id})
    record = context.causal_graphs.update(dataset, graph_id, spec)
    logger.info("Causal graph %s updated to revision %d", record.graph_id, record.revision)
    return graph_payload(record, dataset)


@router.delete("/datasets/{dataset_id}/causal-graphs/{graph_id}")
def delete_causal_graph(dataset_id: str, graph_id: str) -> dict[str, Any]:
    context = get_context()
    _dataset(dataset_id)
    context.causal_graphs.delete(dataset_id, graph_id)
    return {"deleted": True, "graph_id": graph_id, "dataset_id": dataset_id}


@router.get("/datasets/{dataset_id}/causal-graphs/{graph_id}/validation")
def validate_causal_graph(dataset_id: str, graph_id: str) -> dict[str, Any]:
    """Re-run validation against the dataset currently in memory. Read-only."""
    context = get_context()
    dataset = _dataset(dataset_id)
    record = context.causal_graphs.get(dataset.dataset_id, graph_id)
    payload = graph_payload(record, dataset)
    return {
        "graph_id": record.graph_id,
        "revision": record.revision,
        "schema_version": payload["schema_version"],
        "validation": payload["validation"],
        "validation_scope_note": payload["validation_scope_note"],
    }


@router.get("/datasets/{dataset_id}/causal-graphs/{graph_id}/export")
def export_causal_graph(dataset_id: str, graph_id: str) -> JSONResponse:
    context = get_context()
    dataset = _dataset(dataset_id)
    record = context.causal_graphs.get(dataset.dataset_id, graph_id)
    return JSONResponse(
        content=export_payload(record, dataset),
        headers={
            "Content-Disposition": (
                f'attachment; filename="splitscope-causal-graph-{record.graph_id}.json"'
            ),
            "X-SplitScope-Export-Note": (
                "Graph structure, assumptions and layout only; no dataset rows are included."
            ),
        },
    )


@router.post("/datasets/{dataset_id}/causal-graphs/import", status_code=201)
def import_causal_graph(dataset_id: str, request: GraphImportRequest) -> JSONResponse:
    """Import an export file as a new graph bound to *this* dataset."""
    context = get_context()
    dataset = _dataset(dataset_id)
    record = context.causal_graphs.import_spec(dataset, request.export_file)
    logger.info("Causal graph %s imported for dataset %s", record.graph_id, dataset_id)
    return _created_response(record, dataset)


__all__ = ["router"]
