"""Load the committed demonstration datasets and their manifest.

The runtime never re-generates a demo. It reads the CSV that is committed to the
repository and the manifest that describes it, so the bytes a reviewer audits are
the bytes that were reviewed. ``scripts/generate_datasets.py`` is what regenerates
both; a test asserts that regeneration reproduces the committed files exactly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

from app.audit.dataset import Dataset, DemoInfo
from app.audit.io import read_csv_bytes
from app.audit.types import AuditConfig, ColumnRoles, NearDuplicateSettings
from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationFailure
from app.core.logging_config import get_logger
from app.synthetic.generators import DEMO_ORDER, DEMOS, DemoSpec

logger = get_logger(__name__)

MANIFEST_FILENAME = "manifest.json"


def datasets_dir() -> Path:
    """Directory holding the committed synthetic CSVs.

    ``SPLITSCOPE_DATASETS_DIR`` overrides the default so the API can run from a
    different working directory without guessing.
    """
    import os

    override = os.environ.get("SPLITSCOPE_DATASETS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path(__file__).resolve().parents[3] / "datasets").resolve()


@dataclass
class LoadedDemo:
    spec: DemoSpec
    manifest_entry: dict[str, Any]
    path: Path

    @property
    def demo_id(self) -> str:
        return self.spec.demo_id

    def info(self) -> DemoInfo:
        return DemoInfo(
            demo_id=self.spec.demo_id,
            title=self.spec.title,
            subtitle=self.spec.subtitle,
            teaching_point=self.spec.teaching_point,
            generation_method=self.spec.generation_method,
            seed=self.spec.seed,
            expected_findings=list(self.spec.expected_findings),
            synthetic=True,
            recommended_audit=dict(self.spec.recommended_audit),
            recommended_split=dict(self.spec.recommended_split) if self.spec.recommended_split else None,
            manifest=self.manifest_entry,
            is_control=self.spec.is_control,
        )

    def load(self, *, settings: Settings) -> Dataset:
        if not self.path.exists():
            raise NotFoundError(
                f"The demo file {self.path.name!r} is missing from the datasets directory.",
                details={
                    "path": str(self.path),
                    "fix": "Run: python scripts/generate_datasets.py",
                },
            )
        data = self.path.read_bytes()
        loaded = read_csv_bytes(
            data,
            max_bytes=settings.upload.max_bytes,
            max_rows=settings.upload.max_rows,
            max_columns=settings.upload.max_columns,
            min_rows=max(1, min(settings.upload.min_rows, 1)),
            min_columns=settings.upload.min_columns,
            filename=self.path.name,
        )
        expected = self.manifest_entry.get("sha256")
        warnings = list(loaded.warnings)
        if expected and expected != loaded.fingerprint_sha256:
            warnings.append(
                "The committed demo file no longer matches its manifest fingerprint. Regenerate it "
                "with scripts/generate_datasets.py before relying on the documented expectations."
            )
        return Dataset(
            dataset_id="pending",
            name=self.spec.filename,
            source="demo",
            is_synthetic=True,
            fingerprint_sha256=loaded.fingerprint_sha256,
            frame=loaded.frame,
            row_ids=loaded.row_ids,
            columns=loaded.columns,
            created_at=_now(),
            encoding=loaded.encoding,
            size_bytes=len(data),
            warnings=warnings,
            demo=self.info(),
        )


def _now():
    from datetime import datetime

    return datetime.now(UTC)


def load_manifest() -> dict[str, Any]:
    path = datasets_dir() / MANIFEST_FILENAME
    if not path.exists():
        raise NotFoundError(
            "The demonstration manifest is missing.",
            details={"path": str(path), "fix": "Run: python scripts/generate_datasets.py"},
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationFailure(
            f"The demonstration manifest is not valid JSON: {exc}",
            details={"path": str(path)},
        ) from None


def list_demos() -> list[DemoSpec]:
    """Demo specs in the documented display order."""
    return [DEMOS[demo_id] for demo_id in DEMO_ORDER]


def entries_by_id() -> dict[str, dict[str, Any]]:
    manifest = load_manifest()
    return {entry["demo_id"]: entry for entry in manifest.get("datasets", [])}


def get_demo(demo_id: str) -> LoadedDemo:
    if demo_id not in DEMOS:
        raise NotFoundError(
            f"No demonstration dataset is registered under the id {demo_id!r}.",
            details={"available": list(DEMO_ORDER)},
        )
    spec = DEMOS[demo_id]
    entries = entries_by_id()
    if demo_id not in entries:
        raise NotFoundError(
            f"The manifest has no entry for the demo {demo_id!r}.",
            details={"path": str(datasets_dir() / MANIFEST_FILENAME)},
        )
    return LoadedDemo(
        spec=spec,
        manifest_entry=entries[demo_id],
        path=datasets_dir() / spec.filename,
    )


def demo_payload(demo_id: str) -> dict[str, Any]:
    """Everything the overview screen needs to describe one demo, without loading it."""
    loaded = get_demo(demo_id)
    spec = loaded.spec
    entry = loaded.manifest_entry
    return {
        "demo_id": spec.demo_id,
        "title": spec.title,
        "subtitle": spec.subtitle,
        "filename": spec.filename,
        "synthetic": True,
        "is_control": spec.is_control,
        "seed": spec.seed,
        "row_count": entry.get("row_count"),
        "column_count": entry.get("column_count"),
        "columns": entry.get("columns", []),
        "sha256": entry.get("sha256"),
        "teaching_point": spec.teaching_point,
        "generation_method": spec.generation_method,
        "expected_findings": spec.expected_findings,
        "recommended_audit": spec.recommended_audit,
        "recommended_split": spec.recommended_split,
        "planted_cases": entry.get("planted_cases", []),
        "summary_metrics": entry.get("summary_metrics", {}),
        "notes": spec.notes,
        "file_present": loaded.path.exists(),
    }


def recommended_roles(demo_id: str) -> ColumnRoles:
    spec = DEMOS[demo_id]
    config = spec.recommended_audit
    return ColumnRoles(
        features=list(config["features"]),
        target=config.get("target"),
        entity=config.get("entity"),
        timestamp=config.get("timestamp"),
        split=config.get("split"),
        split_train_value=config.get("split_train_value"),
        split_test_value=config.get("split_test_value"),
        metadata_excluded=list(config.get("metadata_excluded") or []),
    )


def recommended_audit_config(demo_id: str, *, settings: Settings) -> AuditConfig:
    spec = DEMOS[demo_id]
    enabled = bool(spec.recommended_audit.get("near_duplicates", False))
    return AuditConfig(
        near_duplicates=NearDuplicateSettings(
            enabled=enabled,
            max_combined_rows=settings.near_duplicate.max_combined_rows,
        )
    )


__all__ = [
    "MANIFEST_FILENAME",
    "LoadedDemo",
    "datasets_dir",
    "demo_payload",
    "entries_by_id",
    "get_demo",
    "list_demos",
    "load_manifest",
    "recommended_audit_config",
    "recommended_roles",
]
