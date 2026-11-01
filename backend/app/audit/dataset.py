"""The in-memory dataset container and existing-split selection.

The container is deliberately thin. It holds the *raw text* frame exactly as it
was uploaded, plus the metadata needed to identify it. No rule ever mutates it:
every analysis derives a read-only view (boolean masks, column selections) and
split assignments live in a separate object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.audit.types import DatasetSummary
from app.core.errors import ValidationFailure


@dataclass
class DemoInfo:
    """Metadata for a bundled synthetic demonstration dataset."""

    demo_id: str
    title: str
    subtitle: str
    teaching_point: str
    generation_method: str
    seed: int | None
    expected_findings: list[str]
    synthetic: bool = True
    recommended_audit: dict[str, object] = field(default_factory=dict)
    recommended_split: dict[str, object] | None = None
    manifest: dict[str, object] = field(default_factory=dict)
    is_control: bool = False


@dataclass
class Dataset:
    """An immutable, typed view of one ingested dataset."""

    dataset_id: str
    name: str
    source: str
    is_synthetic: bool
    fingerprint_sha256: str
    frame: pd.DataFrame
    row_ids: list[str]
    columns: list[str]
    created_at: datetime
    encoding: str
    size_bytes: int
    warnings: list[str] = field(default_factory=list)
    demo: DemoInfo | None = None

    @property
    def row_count(self) -> int:
        return int(self.frame.shape[0])

    @property
    def column_count(self) -> int:
        return int(self.frame.shape[1])

    def series(self, column: str) -> pd.Series:
        if column not in self.frame.columns:
            raise ValidationFailure(
                f"Column {column!r} is not present in the dataset.",
                details={"available_columns": self.columns[:50]},
            )
        return self.frame[column]

    def values(self, column: str) -> list[str]:
        return self.frame[column].tolist()

    def summary(self) -> DatasetSummary:
        return DatasetSummary(
            dataset_id=self.dataset_id,
            name=self.name,
            source="demo" if self.source == "demo" else "upload",
            is_synthetic=self.is_synthetic,
            fingerprint_sha256=self.fingerprint_sha256,
            row_count=self.row_count,
            column_count=self.column_count,
            columns=list(self.columns),
            created_at_utc=self.created_at.astimezone(UTC).isoformat(timespec="seconds"),
            demo_id=self.demo.demo_id if self.demo else None,
            warnings=list(self.warnings),
        )


@dataclass(frozen=True)
class SplitMasks:
    """Boolean row masks for a train/test split."""

    train: np.ndarray
    test: np.ndarray

    @property
    def train_rows(self) -> int:
        return int(self.train.sum())

    @property
    def test_rows(self) -> int:
        return int(self.test.sum())

    @property
    def total_rows(self) -> int:
        return int(self.train.shape[0])

    @property
    def assigned_rows(self) -> int:
        return self.train_rows + self.test_rows

    @property
    def achieved_test_fraction(self) -> float:
        """Test share over *assigned* rows.

        Rows carrying neither the train nor the test label are excluded from the
        denominator, because folding them into either side would change the split
        being described. The count of such rows is reported separately.
        """
        assigned = self.assigned_rows
        return float(self.test_rows) / float(assigned) if assigned else 0.0

    def row_ids(self, dataset: Dataset, label: str) -> list[str]:
        mask = self.train if label == "train" else self.test
        return [rid for rid, keep in zip(dataset.row_ids, mask.tolist(), strict=True) if keep]

    def positions(self, label: str) -> list[int]:
        mask = self.train if label == "train" else self.test
        return [index for index, keep in enumerate(mask.tolist()) if keep]


@dataclass(frozen=True)
class ExistingSplitSelection:
    masks: SplitMasks
    other_labels: dict[str, int]
    matched_train_value: str
    matched_test_value: str
    unassigned_rows: int


def select_existing_split(
    dataset: Dataset,
    *,
    split_column: str,
    train_value: str,
    test_value: str,
) -> ExistingSplitSelection:
    """Build masks from an existing split column.

    Rows whose split label is neither the train nor the test value are reported
    as ``unassigned_rows`` rather than being folded into either side. Silently
    assigning them would change the split under audit.
    """
    labels = dataset.series(split_column).tolist()
    train_mask = np.fromiter((v == train_value for v in labels), dtype=bool, count=len(labels))
    test_mask = np.fromiter((v == test_value for v in labels), dtype=bool, count=len(labels))

    if not train_mask.any():
        raise ValidationFailure(
            f"No rows have the train label {train_value!r} in column {split_column!r}.",
            details={"split_column": split_column, "train_value": train_value},
        )
    if not test_mask.any():
        raise ValidationFailure(
            f"No rows have the test label {test_value!r} in column {split_column!r}.",
            details={"split_column": split_column, "test_value": test_value},
        )

    other: dict[str, int] = {}
    for value, is_train, is_test in zip(labels, train_mask.tolist(), test_mask.tolist(), strict=True):
        if is_train or is_test:
            continue
        other[value] = other.get(value, 0) + 1

    return ExistingSplitSelection(
        masks=SplitMasks(train=train_mask, test=test_mask),
        other_labels=dict(sorted(other.items(), key=lambda kv: (-kv[1], kv[0]))[:20]),
        matched_train_value=train_value,
        matched_test_value=test_value,
        unassigned_rows=int(sum(other.values())),
    )


__all__ = [
    "Dataset",
    "DemoInfo",
    "ExistingSplitSelection",
    "SplitMasks",
    "select_existing_split",
]
