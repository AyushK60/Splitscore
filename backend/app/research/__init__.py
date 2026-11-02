"""S3 research foundation: study metadata, roles, profiling and provenance."""

from app.research.profiling import build_profile
from app.research.provenance import build_manifest, schema_fingerprint, validate_manifest
from app.research.schema import (
    MANIFEST_SCHEMA_VERSION,
    RESEARCH_ROLES,
    STUDY_FIELDS,
    STUDY_SCHEMA_VERSION,
    StudyCardDraft,
    build_role_map,
    completion,
)
from app.research.studies import (
    StudyRecord,
    StudyRegistry,
    apply_role_map,
    roles_from_column_roles,
    study_payload,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "RESEARCH_ROLES",
    "STUDY_FIELDS",
    "STUDY_SCHEMA_VERSION",
    "StudyCardDraft",
    "StudyRecord",
    "StudyRegistry",
    "apply_role_map",
    "build_manifest",
    "build_profile",
    "build_role_map",
    "completion",
    "roles_from_column_roles",
    "schema_fingerprint",
    "study_payload",
    "validate_manifest",
]
