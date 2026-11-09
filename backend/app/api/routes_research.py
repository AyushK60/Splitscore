"""Study Card, data dictionary, profiling and provenance routes.

Every route is scoped to a dataset that already exists in the store, so a study
can never be attached to data the process no longer holds.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_context
from app.audit.catalogue import catalogue_payload
from app.core.errors import NotFoundError
from app.core.logging_config import get_logger
from app.core.store import StoredRun
from app.research.history import (
    build_manifest as build_reproducibility_manifest,
)
from app.research.history import build_run_history
from app.research.profiling import build_profile
from app.research.provenance import build_manifest, validate_manifest
from app.research.schema import MANIFEST_SCHEMA_VERSION, StudyCardDraft
from app.synthetic.manifest import recommended_roles as demo_recommended_roles
from app.research.studies import (
    STORAGE_NOTE,
    roles_from_column_roles,
    apply_role_map,
    declaration_map,
    study_payload,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["research"])


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ColumnDeclaration(_Model):
    column: str = Field(min_length=1, max_length=200)
    declared_type: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=1000)
    unit: str | None = Field(default=None, max_length=120)
    measurement_scale: str | None = Field(default=None, max_length=60)


class StudyUpdateRequest(_Model):
    card: StudyCardDraft
    split_train_value: str | None = Field(default=None, max_length=200)
    split_test_value: str | None = Field(default=None, max_length=200)
    column_declarations: list[ColumnDeclaration] = Field(default_factory=list, max_length=200)


class RoleMapRequest(_Model):
    assignments: dict[str, list[str]]
    split_train_value: str | None = Field(default=None, max_length=200)
    split_test_value: str | None = Field(default=None, max_length=200)


class ManifestImportRequest(_Model):
    manifest: dict[str, Any]
    apply: bool = False


def _record(dataset_id: str):
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    record = context.studies.get(dataset_id)
    if record is None:
        # A bundled demo declares its own roles in its manifest. Copying that
        # documented configuration is not an inference; the response says where
        # it came from, and the user can change every value. The split labels
        # are part of that same declared configuration.
        seed = None
        split_labels = None
        if dataset.demo is not None:
            demo_roles = demo_recommended_roles(dataset.demo.demo_id)
            seed = roles_from_column_roles(demo_roles)
            split_labels = (demo_roles.split_train_value, demo_roles.split_test_value)
        record = context.studies.get_or_create(
            dataset_id, seed_roles=seed, seed_split_labels=split_labels
        )
    return dataset, record


@router.get("/datasets/{dataset_id}/study")
def get_study(dataset_id: str) -> dict[str, Any]:
    dataset, record = _record(dataset_id)
    payload = study_payload(record, dataset)
    payload["storage_note"] = STORAGE_NOTE
    payload["roles_seeded_from"] = (
        "demo manifest" if dataset.demo is not None and record.role_assignments else None
    )
    return payload


@router.put("/datasets/{dataset_id}/study")
def put_study(dataset_id: str, request: StudyUpdateRequest) -> dict[str, Any]:
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    record = context.studies.get_or_create(dataset_id)
    record.card = request.card
    if request.column_declarations:
        record.column_declarations = declaration_map(
            [entry.model_dump() for entry in request.column_declarations]
        )
    if request.split_train_value is not None:
        record.split_train_value = request.split_train_value
    if request.split_test_value is not None:
        record.split_test_value = request.split_test_value
    context.studies.save(record)
    logger.info("Study %s saved (revision %d) for dataset %s", record.study_id, record.revision, dataset_id)
    return study_payload(record, dataset)


@router.get("/datasets/{dataset_id}/study/export")
def export_study(dataset_id: str) -> JSONResponse:
    dataset, record = _record(dataset_id)
    payload = study_payload(record, dataset)
    body = {
        "study_schema_version": payload["schema_version"],
        "study_id": payload["study_id"],
        "revision": payload["revision"],
        "exported_at_utc": payload["updated_at_utc"],
        "card": payload["card"],
        "roles": payload["roles"]["assignments"],
        "column_declarations": payload["column_declarations"],
        "provenance": payload["provenance"],
        "dataset": {
            "name": dataset.name,
            "sha256": dataset.fingerprint_sha256,
            "row_count": dataset.row_count,
            "columns": dataset.column_count,
        },
        "note": (
            "This file contains study metadata only. It does not contain dataset rows and cannot "
            "reconstruct the uploaded file."
        ),
    }
    return JSONResponse(
        content=body,
        headers={
            "Content-Disposition": f'attachment; filename="splitscope-study-{dataset.dataset_id}.json"',
            "X-SplitScope-Export-Note": "Study metadata only; no dataset rows are included.",
        },
    )


@router.get("/datasets/{dataset_id}/profile")
def get_profile(dataset_id: str) -> dict[str, Any]:
    dataset, record = _record(dataset_id)
    profile = build_profile(
        dataset,
        assignments=record.role_assignments,
        declarations=record.column_declarations,
    )
    profile["dataset_name"] = dataset.name
    return profile


@router.get("/datasets/{dataset_id}/dictionary")
def get_dictionary(dataset_id: str) -> dict[str, Any]:
    dataset, record = _record(dataset_id)
    profile = build_profile(
        dataset,
        assignments=record.role_assignments,
        declarations=record.column_declarations,
    )
    return {
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.name,
        "columns": profile["columns"],
        "assignments": record.role_assignments,
        "summary": profile["summary"],
        "conventions": profile["conventions"],
        "note": (
            "Types and counts are computed from the loaded file. Descriptions, units and "
            "measurement scales are yours; the role list is your declaration, not a suggestion."
        ),
    }


@router.put("/datasets/{dataset_id}/roles")
def put_roles(dataset_id: str, request: RoleMapRequest) -> dict[str, Any]:
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    record = context.studies.get_or_create(dataset_id)
    result = apply_role_map(
        record,
        dataset,
        request.assignments,
        # An omitted split label means "keep what the study already declares";
        # otherwise every save would have to resend the labels.
        split_train_value=(
            request.split_train_value
            if request.split_train_value is not None
            else record.split_train_value
        ),
        split_test_value=(
            request.split_test_value
            if request.split_test_value is not None
            else record.split_test_value
        ),
    )
    if result["ok"]:
        context.studies.save(record)
        logger.info("Role map saved for dataset %s", dataset_id)
    payload = study_payload(record, dataset)
    return {
        "ok": result["ok"],
        "errors": result["errors"],
        "warnings": result["warnings"],
        "issues": result["issues"],
        "derived_roles": result["derived_roles"],
        "assignments": result["assignments"],
        "study": payload,
    }


@router.get("/datasets/{dataset_id}/manifest")
def get_manifest(dataset_id: str) -> dict[str, Any]:
    dataset, record = _record(dataset_id)
    checks = [entry["rule_id"] for entry in catalogue_payload()["checks"]]
    return build_manifest(dataset, record, available_checks=checks)


@router.get("/datasets/{dataset_id}/manifest/export")
def export_manifest(dataset_id: str) -> JSONResponse:
    dataset, record = _record(dataset_id)
    checks = [entry["rule_id"] for entry in catalogue_payload()["checks"]]
    manifest = build_manifest(dataset, record, available_checks=checks)
    return JSONResponse(
        content=manifest,
        headers={
            "Content-Disposition": (
                f'attachment; filename="splitscope-manifest-{dataset.dataset_id}.json"'
            ),
            "X-SplitScope-Export-Note": (
                "Reproducibility manifest: dataset fingerprint and study metadata only, no rows."
            ),
        },
    )


@router.post("/datasets/{dataset_id}/manifest/validate")
def post_manifest_validate(
    dataset_id: str, request: ManifestImportRequest = Body(...)
) -> dict[str, Any]:
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    record = context.studies.get_or_create(dataset_id)
    manifest = request.manifest or {}
    if manifest.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        return {
            "status": "unsupported_version",
            "ok": False,
            "message": (
                f"This build reads manifest schema {MANIFEST_SCHEMA_VERSION!r}; the file declares "
                f"{manifest.get('manifest_schema_version')!r}."
            ),
            "checks": [],
            "applied": False,
        }

    result = validate_manifest(dataset, manifest)
    applied = False
    if result["ok"] and request.apply:
        study = manifest.get("study") or {}
        known = set(StudyCardDraft.model_fields)
        record.card = StudyCardDraft(**{key: study.get(key) for key in known})
        roles = (manifest.get("roles") or {}).get("assignments") or {}
        if isinstance(roles, dict):
            record.role_assignments = {
                column: [role for role in roles_list if isinstance(role, str)]
                for column, roles_list in roles.items()
                if isinstance(roles_list, list)
            }
        context.studies.save(record)
        applied = True
        result["study_state"] = study_payload(record, dataset)

    result["applied"] = applied
    return result


# --------------------------------------------------------------------------- #
# history - research run history and reproducibility manifests
# --------------------------------------------------------------------------- #


def _graph_fingerprint_lookup(dataset_id: str, graph_id: str) -> tuple[str, str] | None:
    """(graph_id, spec_fingerprint) for a live graph, or None when it is gone."""
    context = get_context()
    try:
        record = context.causal_graphs.get(dataset_id, graph_id)
    except NotFoundError:
        return None
    return record.graph_id, record.fingerprint


@router.get("/datasets/{dataset_id}/history")
def dataset_history(dataset_id: str) -> dict[str, Any]:
    """The typed research run history for one live dataset, newest first."""
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    listed = [
        entry
        for entry in context.store.list_runs()
        if entry["dataset_id"] == dataset.dataset_id
    ]
    stored: list[tuple[StoredRun, float]] = []
    for entry in listed:
        run = context.store.get_run(entry["run_id"])
        stored.append((run, entry["created_seconds_ago"]))
    payload = build_run_history(dataset, stored, _graph_fingerprint_lookup)
    payload["store"] = {
        "runs_used": len(stored),
        "limits": context.store.stats().limits,
    }
    return payload


@router.get("/datasets/{dataset_id}/history/{run_id}/manifest")
def dataset_run_manifest(dataset_id: str, run_id: str) -> dict[str, Any]:
    """A portable, metadata-only reproducibility manifest for one stored run."""
    context = get_context()
    dataset = context.store.get_dataset(dataset_id)
    run = context.store.get_run(run_id)
    if run.dataset_id != dataset.dataset_id:
        raise NotFoundError(
            "That run belongs to a different dataset.",
            details={"run_id": run_id, "dataset_id": dataset_id},
        )
    return build_reproducibility_manifest(run, dataset, _graph_fingerprint_lookup)


__all__ = ["router"]
