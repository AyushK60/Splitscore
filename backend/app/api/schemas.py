"""Request and response models for the HTTP layer.

Every response body the frontend consumes is declared here, so the API contract is
inspectable in ``/openapi.json`` and in the generated TypeScript types.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.splits.plans import PlanConfig
from app.audit.types import (
    AuditConfig,
    AuditResult,
    ColumnRoles,
    ColumnTypeInfo,
    ComparisonResult,
    DatasetSummary,
    RoleValidationResult,
    SplitConfig,
    SplitSummary,
)

MAX_STRATEGIES_PER_COMPARISON = 8


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Health and catalogue
# --------------------------------------------------------------------------- #


class HealthResponse(_Model):
    status: Literal["ok"]
    app_name: str
    app_version: str
    audit_schema_version: str
    server_time_utc: str
    limits: dict[str, Any]
    store: dict[str, Any]
    storage_note: str


class ChecksResponse(_Model):
    checks: list[dict[str, Any]]
    what_this_app_does_not_do: list[str]
    no_findings_means: str


# --------------------------------------------------------------------------- #
# Demos
# --------------------------------------------------------------------------- #


class DemoListResponse(_Model):
    demos: list[dict[str, Any]]
    featured_journey: dict[str, Any]


# --------------------------------------------------------------------------- #
# Datasets
# --------------------------------------------------------------------------- #


class DatasetDetailResponse(_Model):
    dataset: DatasetSummary
    column_types: dict[str, ColumnTypeInfo]
    suggested_roles: ColumnRoles
    suggested_roles_confidence: str
    role_suggestions: dict[str, Any]
    validation: RoleValidationResult
    dataset_limits: dict[str, Any]


class DatasetLoadedResponse(_Model):
    dataset: DatasetSummary
    column_types: dict[str, ColumnTypeInfo]
    suggested_roles: ColumnRoles
    suggested_roles_confidence: str
    role_suggestions: dict[str, Any]
    validation: RoleValidationResult
    dataset_limits: dict[str, Any]
    demo: dict[str, Any] | None = None
    recommended_audit_config: AuditConfig | None = None
    recommended_split: dict[str, Any] | None = None


class PreviewResponse(_Model):
    dataset_id: str
    columns: list[str]
    row_ids: list[str]
    rows: list[list[str]]
    offset: int
    limit: int
    total_rows: int
    truncated_columns: bool
    note: str


class ColumnValueCount(_Model):
    value: str
    count: int


class ColumnValuesResponse(_Model):
    dataset_id: str
    column: str
    total_rows: int
    distinct_count: int
    missing_count: int
    values: list[ColumnValueCount]
    truncated: bool
    note: str


class ValidateRolesRequest(_Model):
    roles: ColumnRoles


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


class AuditRequest(_Model):
    """Run the audit on either the split in the file or a generated split.

    ``generate`` is optional. When it is present the server builds the split
    with the same strategies the comparison uses, records strategy/seed/row
    assignments, and audits *that* assignment; when it is absent the split
    column named in ``roles`` is read from the file, exactly as before.
    """

    dataset_id: str = Field(min_length=1)
    roles: ColumnRoles
    config: AuditConfig = Field(default_factory=AuditConfig)
    generate: SplitConfig | None = None


class AssignmentHandle(_Model):
    strategy_id: str
    assignment_id: str
    label: str
    kind: str
    train_rows: int
    test_rows: int
    download_path: str


class AuditResponse(_Model):
    run_id: str
    result: AuditResult
    export_hint: str
    assignment: AssignmentHandle | None = None


# --------------------------------------------------------------------------- #
# Split comparison
# --------------------------------------------------------------------------- #


class CompareRequest(_Model):
    dataset_id: str = Field(min_length=1)
    roles: ColumnRoles
    config: AuditConfig = Field(default_factory=AuditConfig)
    strategies: list[SplitConfig] = Field(default_factory=list, max_length=MAX_STRATEGIES_PER_COMPARISON)
    #: F05 evaluation plans (CV / rolling origin), audited fold by fold.
    plans: list[PlanConfig] = Field(default_factory=list, max_length=4)
    include_existing_split: bool = True


class CompareResponse(_Model):
    run_id: str
    result: ComparisonResult
    assignments: list[AssignmentHandle]
    sanitization_note: str
    selection_note: str


class ExistingSplitSummaryResponse(_Model):
    split: SplitSummary


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


class ReportRequest(_Model):
    run_id: str = Field(min_length=1)


class DossierRequest(_Model):
    """Explicit sources for a composite S7 dossier.

    Nothing is inferred from "latest" state: the client names the run IDs it has
    in scope. Sections are ordered server-side regardless of request order.
    """

    sections: list[str] | None = Field(default=None, max_length=10)
    audit_run_id: str | None = Field(default=None, min_length=1, max_length=160)
    comparison_run_id: str | None = Field(default=None, min_length=1, max_length=160)
    model_run_ids: list[str] = Field(default_factory=list, max_length=8)


class RunListResponse(_Model):
    runs: list[dict[str, Any]]
    store: dict[str, Any]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ErrorBody(_Model):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(_Model):
    error: ErrorBody


__all__ = [
    "MAX_STRATEGIES_PER_COMPARISON",
    "AssignmentHandle",
    "AuditRequest",
    "AuditResponse",
    "ChecksResponse",
    "ColumnValueCount",
    "ColumnValuesResponse",
    "CompareRequest",
    "CompareResponse",
    "DatasetDetailResponse",
    "DatasetLoadedResponse",
    "DossierRequest",
    "ErrorResponse",
    "ExistingSplitSummaryResponse",
    "HealthResponse",
    "PreviewResponse",
    "ReportRequest",
    "RunListResponse",
    "ValidateRolesRequest",
]
