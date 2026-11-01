"""Health, check catalogue, demos and dataset ingestion routes."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from fastapi import APIRouter, File, Query, UploadFile

from app.api.deps import get_context
from app.api.schemas import (
    ChecksResponse,
    ColumnValueCount,
    ColumnValuesResponse,
    DatasetDetailResponse,
    DatasetLoadedResponse,
    DemoListResponse,
    PreviewResponse,
    ValidateRolesRequest,
)
from app.audit.catalogue import catalogue_payload
from app.audit.dataset import Dataset
from app.audit.io import infer_column_types, read_csv_bytes
from app.audit.roles import validate_roles
from app.audit.suggest import suggest_roles
from app.audit.types import RoleValidationResult
from app.core.errors import LimitExceededError, NotFoundError, UnsupportedInputError
from app.core.logging_config import get_logger
from app.core.version import APP_NAME, APP_VERSION, AUDIT_SCHEMA_VERSION
from app.synthetic.manifest import (
    demo_payload,
    get_demo,
    list_demos,
    recommended_audit_config,
    recommended_roles,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["datasets"])

FEATURED_JOURNEY = {
    "demo_id": "repeated_entity",
    "title": "Repeated-entity demo: entity overlap that a group holdout removes",
    "steps": [
        "Load the repeated-entity demo dataset.",
        "Audit the existing split and inspect the entity-overlap finding and its evidence rows.",
        "Open the split comparison and compare the existing split with a group holdout on the same "
        "entity column.",
        "Watch the entity overlap fall to zero and read the remaining findings and limitations.",
    ],
}

STORAGE_NOTE = (
    "Datasets, audit runs and split assignments live in this server's memory only. They expire "
    "after the configured TTL and disappear when the process restarts. Anything you want to keep "
    "must be exported as a JSON or HTML report first."
)

ALLOWED_UPLOAD_SUFFIXES = (".csv", ".txt", ".tsv")


def _column_types(dataset: Dataset):
    return infer_column_types(dataset.frame)


def _dataset_limits() -> dict[str, object]:
    return get_context().settings.upload.as_dict()


def _parsed_bytes(dataset: Dataset) -> int:
    """Estimated in-memory size of the parsed frame (not the uploaded bytes).

    Object-dtype text columns dominate this figure, which is why the byte cap
    and the parsed-memory cap are separate limits with separate messages.
    """
    return int(dataset.frame.memory_usage(deep=True).sum())


def _admit(dataset: Dataset) -> Dataset:
    """Parse-size accounting plus store admission, shared by both entry points.

    The parsed size is measured once. It is first checked against the
    per-dataset parsed-memory limit and then against the store budget, so the
    caller never reports success for something the process will not hold.
    """
    limits = get_context().settings.upload
    footprint = _parsed_bytes(dataset)
    if footprint > limits.max_parsed_bytes:
        raise LimitExceededError(
            f"Parsed, the file needs {footprint / (1024 * 1024):.1f} MB of memory, above the "
            f"{limits.max_parsed_bytes / (1024 * 1024):.0f} MB parsed-dataset limit. Nothing was "
            "stored.",
            details={
                "parsed_bytes": footprint,
                "parsed_bytes_allowed": limits.max_parsed_bytes,
                "rows": dataset.row_count,
                "columns": dataset.column_count,
                "hint": "CSV text expands several times over once every cell becomes a Python "
                "object. Split the file, or raise SPLITSCOPE_MAX_PARSED_BYTES when starting the "
                "server.",
            },
        )
    admitted = get_context().store.put_dataset(dataset, size_bytes=footprint)
    logger.info(
        "Admitted %s as dataset %s (%d rows, %d columns, ~%.1f MB parsed)",
        admitted.name,
        admitted.dataset_id,
        admitted.row_count,
        admitted.column_count,
        footprint / (1024 * 1024),
    )
    return admitted


def _sanitized_display_name(filename: str | None) -> str:
    raw = (filename or "uploaded.csv").replace("\\", "/").split("/")[-1].strip()
    return raw or "uploaded.csv"


@router.get("/health", tags=["health"])
def health() -> dict[str, object]:
    context = get_context()
    stats = context.store.stats()
    return {
        "status": "ok",
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "server_time_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "limits": context.settings.limits_payload(),
        "store": {
            "datasets": stats.datasets,
            "runs": stats.runs,
            "assignments": stats.assignments,
            "total_bytes": stats.total_bytes,
            "evictions": stats.evictions,
            "expirations": stats.expirations,
            "limits": stats.limits,
        },
        "storage_note": STORAGE_NOTE,
    }


@router.get("/checks", response_model=ChecksResponse)
def checks() -> ChecksResponse:
    payload = catalogue_payload()
    return ChecksResponse(**payload)


@router.get("/demos", response_model=DemoListResponse)
def demos() -> DemoListResponse:
    return DemoListResponse(
        demos=[demo_payload(spec.demo_id) for spec in list_demos()],
        featured_journey=FEATURED_JOURNEY,
    )


@router.post("/demos/{demo_id}/load", response_model=DatasetLoadedResponse)
def load_demo(demo_id: str) -> DatasetLoadedResponse:
    context = get_context()
    loaded = get_demo(demo_id)
    dataset = loaded.load(settings=context.settings)
    _admit(dataset)
    logger.info("Loaded demo %s as dataset %s (%d rows)", demo_id, dataset.dataset_id, dataset.row_count)

    roles = recommended_roles(demo_id)
    validation = validate_roles(dataset, roles)
    payload = demo_payload(demo_id)
    return DatasetLoadedResponse(
        dataset=dataset.summary(),
        column_types=_column_types(dataset),
        suggested_roles=roles,
        suggested_roles_confidence="recommended",
        role_suggestions={
            "reasons": {
                "note": "Roles come from the demo's own manifest, which documents what each demo "
                "plants and which columns it intends to be audited."
            },
            "metadata_columns": list(roles.metadata_excluded),
            "feature_count": len(roles.features),
            "features_not_suggested": [],
            "roles_detected": 4,
            "note": "This is the demo's documented configuration, not a name-based guess.",
        },
        validation=validation,
        dataset_limits=_dataset_limits(),
        demo=payload,
        recommended_audit_config=recommended_audit_config(demo_id, settings=context.settings),
        recommended_split=payload.get("recommended_split"),
    )


@router.post("/datasets", response_model=DatasetLoadedResponse, status_code=201)
async def upload_dataset(file: UploadFile = File(...)) -> DatasetLoadedResponse:
    """Ingest one CSV. Rejects, never truncates, anything outside the limits."""
    context = get_context()
    limits = context.settings.upload
    display_name = _sanitized_display_name(file.filename)

    if not display_name.lower().endswith(ALLOWED_UPLOAD_SUFFIXES):
        raise UnsupportedInputError(
            f"{display_name!r} is not a supported file type. SplitScope reads comma-separated text "
            "files in this version.",
            details={
                "filename": display_name,
                "supported_suffixes": list(ALLOWED_UPLOAD_SUFFIXES),
                "not_supported": ["Excel (.xlsx/.xls)", "Parquet", "PDF", "Databases"],
            },
        )

    data = await file.read(limits.max_bytes + 1)
    if len(data) > limits.max_bytes:
        raise LimitExceededError(
            f"The file is larger than the {limits.max_bytes / (1024 * 1024):.2f} MB upload limit.",
            details={
                "bytes_read": len(data),
                "bytes_allowed": limits.max_bytes,
                "filename": display_name,
            },
        )

    loaded = read_csv_bytes(
        data,
        max_bytes=limits.max_bytes,
        max_rows=limits.max_rows,
        max_columns=limits.max_columns,
        min_rows=limits.min_rows,
        min_columns=limits.min_columns,
        filename=display_name,
    )

    dataset = Dataset(
        dataset_id="pending",
        name=display_name,
        source="upload",
        is_synthetic=False,
        fingerprint_sha256=loaded.fingerprint_sha256,
        frame=loaded.frame,
        row_ids=loaded.row_ids,
        columns=loaded.columns,
        created_at=datetime.now(UTC),
        encoding=loaded.encoding,
        size_bytes=len(data),
        warnings=list(loaded.warnings),
        demo=None,
    )
    _admit(dataset)
    logger.info(
        "Accepted upload %s as dataset %s (%d rows, %d columns)",
        display_name,
        dataset.dataset_id,
        dataset.row_count,
        dataset.column_count,
    )

    column_types = _column_types(dataset)
    roles, confidence, suggestions = suggest_roles(dataset, column_types)
    validation = validate_roles(dataset, roles)

    return DatasetLoadedResponse(
        dataset=dataset.summary(),
        column_types=column_types,
        suggested_roles=roles,
        suggested_roles_confidence=confidence,
        role_suggestions=suggestions,
        validation=validation,
        dataset_limits=_dataset_limits(),
        demo=None,
        recommended_audit_config=None,
        recommended_split=None,
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def dataset_detail(dataset_id: str) -> DatasetDetailResponse:
    dataset = get_context().store.get_dataset(dataset_id)
    column_types = _column_types(dataset)
    roles, confidence, suggestions = suggest_roles(dataset, column_types)
    return DatasetDetailResponse(
        dataset=dataset.summary(),
        column_types=column_types,
        suggested_roles=roles,
        suggested_roles_confidence=confidence,
        role_suggestions=suggestions,
        validation=validate_roles(dataset, roles),
        dataset_limits=_dataset_limits(),
    )


@router.get("/datasets/{dataset_id}/preview", response_model=PreviewResponse)
def dataset_preview(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> PreviewResponse:
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    max_columns = context.settings.upload.max_columns
    columns = dataset.columns[:max_columns]
    frame = dataset.frame
    window = frame.iloc[offset : offset + limit]
    note = (
        "Values are shown exactly as they appear in the CSV. Empty cells are missing values under "
        "the documented rule; strings such as 'NA' are shown as values."
    )
    if len(dataset.columns) > max_columns:
        note += f" Only the first {max_columns} columns are shown."
    return PreviewResponse(
        dataset_id=dataset.dataset_id,
        columns=columns,
        row_ids=list(dataset.row_ids[offset : offset + limit]),
        rows=[[str(value) for value in row] for row in window.to_numpy().tolist()],
        offset=offset,
        limit=limit,
        total_rows=dataset.row_count,
        truncated_columns=len(dataset.columns) > max_columns,
        note=note,
    )


@router.get("/datasets/{dataset_id}/column-values", response_model=ColumnValuesResponse)
def column_values(
    dataset_id: str,
    column: str = Query(..., min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> ColumnValuesResponse:
    """Observed values of one column with their row counts.

    This backs the "map your labels to train/test" step: the user picks from
    values the file actually contains, with counts, instead of typing a label
    and hoping it matches. Values are reported exactly as stored.
    """
    dataset = get_context().store.get_dataset(dataset_id)
    if column not in dataset.columns:
        raise NotFoundError(
            f"The column {column!r} is not part of this dataset.",
            details={"column": column, "columns": dataset.columns[:50]},
        )

    values = dataset.values(column)
    counts = Counter(values)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    shown = ordered[:limit]
    missing_count = counts.get("", 0)

    return ColumnValuesResponse(
        dataset_id=dataset.dataset_id,
        column=column,
        total_rows=len(values),
        distinct_count=len(counts),
        missing_count=missing_count,
        values=[ColumnValueCount(value=value, count=count) for value, count in shown],
        truncated=len(ordered) > len(shown),
        note=(
            "Values appear exactly as stored in the file. An empty cell is reported as an empty "
            "value and is treated as a missing value under the documented rule; strings such as "
            "'NA' are shown as ordinary values."
        ),
    )


@router.post("/datasets/{dataset_id}/roles/validate", response_model=RoleValidationResult)
def validate_dataset_roles(dataset_id: str, request: ValidateRolesRequest) -> RoleValidationResult:
    dataset = get_context().store.get_dataset(dataset_id)
    return validate_roles(dataset, request.roles)


__all__ = ["FEATURED_JOURNEY", "STORAGE_NOTE", "router"]
