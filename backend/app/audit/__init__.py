"""SplitScope's audit engine.

The engine is independent of FastAPI and of the frontend: it operates on a
pandas frame plus typed configuration and returns typed results. Everything the
web layer does is a thin wrapper around the functions exported here.
"""

from app.audit.canonical import MISSING_TOKEN, ValueCanonicalizer
from app.audit.dataset import Dataset, DemoInfo, SplitMasks
from app.audit.engine import GLOBAL_ASSUMPTIONS, GLOBAL_LIMITATIONS, run_audit
from app.audit.io import LoadedCsv, infer_column_types, read_csv_bytes
from app.audit.roles import validate_roles
from app.audit.service import audit_existing_split, resolve_or_raise
from app.audit.types import (
    AuditConfig,
    AuditResult,
    ColumnRoles,
    ComparisonResult,
    Count,
    Diagnostics,
    EvidenceExample,
    Finding,
    NotEvaluatedCheck,
    ResolvedRoles,
    RoleValidationResult,
    SplitAssignment,
    SplitConfig,
    SplitSummary,
)

__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "GLOBAL_ASSUMPTIONS",
    "GLOBAL_LIMITATIONS",
    "MISSING_TOKEN",
    "AuditConfig",
    "AuditResult",
    "ColumnRoles",
    "ComparisonResult",
    "Count",
    "Dataset",
    "DemoInfo",
    "Diagnostics",
    "EvidenceExample",
    "Finding",
    "LoadedCsv",
    "NotEvaluatedCheck",
    "ResolvedRoles",
    "RoleValidationResult",
    "SplitAssignment",
    "SplitConfig",
    "SplitMasks",
    "SplitSummary",
    "ValueCanonicalizer",
    "audit_existing_split",
    "infer_column_types",
    "read_csv_bytes",
    "resolve_or_raise",
    "run_audit",
    "validate_roles",
]
