"""F07 - train/test similarity exploration (bounded, deterministic).

The exploration half of the near-duplicate method: the same documented distance
- normalised Chebyshev (L-infinity) after pooled median imputation and robust
scaling - computed as an *exploration service* rather than a rule. It returns
the K nearest cross-split pairs and a nearest-neighbour distance summary for
the test population, so a researcher can inspect the closest train/test
neighbours of any split, not only the audit's thresholded candidates.

Scientific rules this service obeys (mirroring SS-NEAR-001):

* only feature-style numeric columns take part; non-numeric columns are listed
  as excluded, never silently skipped;
* the scaling population is the pooled train+test rows of the analysed split;
  the scaler is diagnostic and never exported;
* rows missing more than the configured fraction of included columns are
  excluded and counted;
* when the split exceeds the row bound, a seeded proportional sample is taken
  and every count is labelled with its scope;
* candidate pairs are never labelled leakage. Similarity is a screening signal.

Deterministic for identical inputs: the sample is seeded, the sweep is
exhaustive over the analysed rows, and ties are broken by row position.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from app.audit.dataset import Dataset
from app.audit.tokens import column_missing_mask
from app.core.errors import ValidationFailure

MAX_PAIRS = 100
DEFAULT_PAIRS = 25
MAX_SIMILARITY_ROWS = 4000
TOP_DIFFERING_COLUMNS = 4
PAIR_CHUNK_SIZE = 128


class SimilarityRequest(BaseModel):
    """Request for the train/test similarity explorer."""

    model_config = ConfigDict(extra="forbid")

    max_pairs: int = Field(default=DEFAULT_PAIRS, ge=1, le=MAX_PAIRS)
    columns: list[str] = Field(default_factory=list, max_length=60)


class SimilarityPair(BaseModel):
    train_row_id: str
    test_row_id: str
    distance: float
    top_diffs: list[dict[str, str]]
    train_values: dict[str, str]
    test_values: dict[str, str]


class SimilarityResponse(BaseModel):
    pairs: list[SimilarityPair]
    pairs_total_available: int
    pairs_truncated: bool
    method: str
    scaling: dict[str, str]
    split: dict[str, str]
    populations: dict[str, int]
    nearest_neighbour_summary: dict[str, float | int]
    nn_histogram: list[int]
    nn_histogram_edges: list[float]
    sampling: str
    limitations: list[str]


@dataclass
class _SplitSpec:
    column: str
    train_value: str
    test_value: str

    def describe(self) -> dict[str, str]:
        return {
            "kind": "existing",
            "column": self.column,
            "train_value": self.train_value,
            "test_value": self.test_value,
        }


def _resolve_split(dataset: Dataset, record) -> _SplitSpec:
    # The study record stores role assignments as column -> role list.
    column = (
        next(
            (
                candidate
                for candidate, roles in (record.role_assignments or {}).items()
                if "split" in roles
            ),
            None,
        )
        if record is not None
        else None
    )
    if not column or record is None or not record.split_train_value or not record.split_test_value:
        raise ValidationFailure(
            "The similarity explorer needs a train/test split. Confirm the split column and "
            "its train/test values in the Data stage, then return here.",
            details={
                "split_column": column or "(none)",
                "hint": "The explorer reads the split confirmed in the Data stage.",
            },
        )
    return _SplitSpec(
        column=column, train_value=record.split_train_value, test_value=record.split_test_value
    )


def _proportional_sample(
    seed: int, train_positions: list[int], test_positions: list[int], cap: int
) -> tuple[list[int], list[int]]:
    """Seeded, proportional sample that keeps both sides non-empty."""
    total = len(train_positions) + len(test_positions)
    effective = max(2, min(cap, total))
    rng = np.random.default_rng(seed)
    n_train = int(round(effective * len(train_positions) / total))
    n_train = max(1, min(n_train, len(train_positions)))
    n_test = max(1, min(effective - n_train, len(test_positions)))
    n_train = max(1, min(effective - n_test, len(train_positions)))
    train_sample = sorted(
        rng.choice(np.asarray(train_positions, dtype=np.int64), size=n_train, replace=False).tolist()
    )
    test_sample = sorted(
        rng.choice(np.asarray(test_positions, dtype=np.int64), size=n_test, replace=False).tolist()
    )
    return train_sample, test_sample


LIMITATIONS = [
    "Similarity is not leakage. A close cross-split pair may be two genuine "
    "records that happen to be alike; the explorer exists to make the closest "
    "pairs inspectable, not to conclude anything about them.",
    "Only numeric columns participate in the distance. Categorical and text "
    "columns are listed as excluded and appear in the pair inspector as raw "
    "values for the human eye.",
    "Distances are in scaled units. The scaling (pooled median/IQR) is a "
    "diagnostic device; the same column in raw units can rank differently.",
    "Counts over a sampled analysis describe the sample, not the dataset; the "
    "sampling note is carried verbatim in the response.",
]


def compute_similarity(
    dataset: Dataset,
    record,  # StudyRecord | None
    request: SimilarityRequest,
    *,
    row_bound: int = MAX_SIMILARITY_ROWS,
    sample_seed: int = 11,
) -> SimilarityResponse:
    split = _resolve_split(dataset, record)

    from app.audit.dataset import select_existing_split

    selection = select_existing_split(
        dataset,
        split_column=split.column,
        train_value=split.train_value,
        test_value=split.test_value,
    )
    masks = selection.masks
    train_positions = [i for i, keep in enumerate(masks.train.tolist()) if keep]
    test_positions = [i for i, keep in enumerate(masks.test.tolist()) if keep]
    if not train_positions or not test_positions:
        raise ValidationFailure(
            "One side of the confirmed split is empty, so there are no cross-split pairs.",
            details={"train_rows": str(len(train_positions)), "test_rows": str(len(test_positions))},
        )

    columns = list(request.columns) if request.columns else list(dataset.columns)
    canonicalizer = _canonicalizer_for(dataset)
    numeric_columns: list[str] = []
    excluded: list[dict[str, str]] = []
    for column in columns:
        missing = column_missing_mask(dataset.frame, column, canonicalizer)
        non_missing = int((~missing).sum())
        if non_missing == 0:
            excluded.append({"column": column, "reason": "all values are missing"})
            continue
        parsed = pd.to_numeric(dataset.frame[column], errors="coerce")
        ratio = float(parsed.notna().sum()) / float(non_missing)
        if ratio >= 0.8:
            numeric_columns.append(column)
        else:
            excluded.append(
                {"column": column, "reason": f"{ratio:.0%} of non-missing values parse as numbers"}
            )
    if not numeric_columns:
        raise ValidationFailure(
            "No column is numeric for at least 80% of its non-missing values, so no distance "
            "can be computed. The similarity explorer measures numeric columns only.",
            details={"columns_considered": str(len(columns))},
        )

    combined = len(train_positions) + len(test_positions)
    sampling = "Full split analysed."
    if combined > row_bound:
        train_positions, test_positions = _proportional_sample(
            sample_seed, train_positions, test_positions, row_bound
        )
        sampling = (
            f"Seeded proportional sample: {len(train_positions)} train and {len(test_positions)} "
            f"test rows drawn from {combined} combined rows with seed {sample_seed}. All counts "
            "describe this sample."
        )

    n_train = len(train_positions)
    selected = train_positions + test_positions
    sub = dataset.frame.iloc[selected][numeric_columns]
    raw = np.column_stack(
        [
            pd.to_numeric(sub[column], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
            for column in numeric_columns
        ]
    )
    missing_fraction = np.isnan(raw).sum(axis=1) / raw.shape[1]
    retained = missing_fraction <= 0.5
    dropped = int((~retained).sum())
    train_raw = raw[:n_train][retained[:n_train]]
    test_raw = raw[n_train:][retained[n_train:]]
    train_kept = [p for p, keep in zip(train_positions, retained[:n_train].tolist(), strict=True) if keep]
    test_kept = [p for p, keep in zip(test_positions, retained[n_train:].tolist(), strict=True) if keep]
    if train_raw.shape[0] == 0 or test_raw.shape[0] == 0:
        raise ValidationFailure(
            "After excluding rows with too many missing numeric values, one side has no rows "
            "left to compare.",
            details={"dropped_rows": str(dropped)},
        )

    pooled = np.vstack([train_raw, test_raw])
    with np.errstate(all="ignore"):
        medians = np.nanmedian(pooled, axis=0)
        q25 = np.nanpercentile(pooled, 25, axis=0)
        q75 = np.nanpercentile(pooled, 75, axis=0)
    iqr = q75 - q25
    usable = ~np.isnan(medians) & (iqr > 0)
    if not usable.any():
        raise ValidationFailure(
            "Every numeric column is constant or has an undefined interquartile range, so no "
            "informative distance can be computed.",
            details={"columns": str(len(numeric_columns))},
        )
    used_columns = [numeric_columns[i] for i in np.nonzero(usable)[0].tolist()]
    for index, column in enumerate(numeric_columns):
        if not usable[index]:
            excluded.append({"column": column, "reason": "constant or not robustly scalable"})

    def _fill_and_scale(block: np.ndarray) -> np.ndarray:
        out = block[:, usable].copy()
        med = medians[usable]
        scale = iqr[usable]
        nan = np.isnan(out)
        out[nan] = np.take(med, np.nonzero(nan)[1])
        return (out - med) / scale

    train_scaled = _fill_and_scale(train_raw)
    test_scaled = _fill_and_scale(test_raw)

    # Sweep the cross-split pairs in chunks, keeping the K nearest in a bounded
    # list ordered worst-first: entries are (-distance, train, test), so after
    # an ascending sort heap[0] is the largest distance and is evicted first.
    # Ties break by (train index, test index): the first encountered under a
    # deterministic order, never by chance.
    k = request.max_pairs
    heap: list[tuple[float, int, int]] = []  # (-distance, train_index, test_index)
    total_pairs = 0
    nn_distances = np.full(test_scaled.shape[0], np.inf)
    for start in range(0, test_scaled.shape[0], PAIR_CHUNK_SIZE):
        chunk = test_scaled[start : start + PAIR_CHUNK_SIZE]
        # (chunk, train, columns) absolute differences -> Chebyshev per pair.
        diff = np.max(np.abs(chunk[:, None, :] - train_scaled[None, :, :]), axis=2)
        for row_in_chunk in range(diff.shape[0]):
            distances = diff[row_in_chunk]
            total_pairs += int(diff.shape[1])
            nn_distances[start + row_in_chunk] = float(distances.min())
            for train_index in range(diff.shape[1]):
                distance = float(distances[train_index])
                if len(heap) < k:
                    heap.append((-distance, train_index, start + row_in_chunk))
                    if len(heap) == k:
                        heap.sort()
                elif distance < -heap[0][0]:
                    heap[0] = (-distance, train_index, start + row_in_chunk)
                    heap.sort()

    heap.sort()
    # Ascending distance is what the inspector shows first.
    ordered = sorted((-neg, train_index, test_index) for neg, train_index, test_index in heap)

    pairs: list[SimilarityPair] = []
    for distance, train_index, test_index in ordered:
        distance = float(distance)
        scaled_diff = np.abs(train_scaled[train_index] - test_scaled[test_index])
        top = np.argsort(-scaled_diff)[:TOP_DIFFERING_COLUMNS]
        train_position = train_kept[train_index]
        test_position = test_kept[test_index]
        top_diffs = [
            {
                "column": used_columns[column_index],
                "scaled_diff": f"{float(scaled_diff[column_index]):.4f}",
                "train_value": _cell(dataset, train_position, used_columns[column_index]),
                "test_value": _cell(dataset, test_position, used_columns[column_index]),
            }
            for column_index in top.tolist()
            if scaled_diff[column_index] > 0
        ]
        display_columns = used_columns[:8]
        pairs.append(
            SimilarityPair(
                train_row_id=dataset.row_ids[train_position],
                test_row_id=dataset.row_ids[test_position],
                distance=round(distance, 6),
                top_diffs=top_diffs,
                train_values={
                    column: _cell(dataset, train_position, column) for column in display_columns
                },
                test_values={
                    column: _cell(dataset, test_position, column) for column in display_columns
                },
            )
        )

    finite_nn = nn_distances[np.isfinite(nn_distances)]
    histogram, edges = np.histogram(finite_nn, bins=20)
    summary = {
        "test_rows_analysed": int(finite_nn.shape[0]),
        "nn_min": round(float(finite_nn.min()), 6),
        "nn_median": round(float(np.median(finite_nn)), 6),
        "nn_p90": round(float(np.percentile(finite_nn, 90)), 6),
        "nn_max": round(float(finite_nn.max()), 6),
    }

    return SimilarityResponse(
        pairs=pairs,
        pairs_total_available=total_pairs,
        pairs_truncated=total_pairs > len(pairs),
        method=(
            "Normalised Chebyshev (L-infinity): the maximum absolute scaled difference over the "
            "included numeric columns. Same method as SS-NEAR-001, computed as an exploration."
        ),
        scaling={
            "method": "robust (median / IQR) over the pooled train+test rows of the analysed split",
            "columns_used": str(len(used_columns)),
            "imputation": "column median over the pooled rows; gaps imputed before scaling",
            "purpose": "diagnostic only - never exported as a fitted pipeline",
        },
        split=split.describe(),
        populations={
            "train_rows": masks.train_rows,
            "test_rows": masks.test_rows,
            "analysed_train": int(train_raw.shape[0]),
            "analysed_test": int(test_raw.shape[0]),
            "rows_dropped_missing": dropped,
            "unassigned_rows": dataset.row_count - masks.assigned_rows,
        },
        nearest_neighbour_summary=summary,
        nn_histogram=[int(value) for value in histogram.tolist()],
        nn_histogram_edges=[round(float(value), 6) for value in edges.tolist()],
        sampling=sampling,
        limitations=LIMITATIONS,
    )


def _cell(dataset: Dataset, position: int, column: str) -> str:
    value = dataset.frame[column].iloc[position]
    if value is None or (isinstance(value, float) and value != value):
        return "(missing)"
    text = str(value)
    return text if len(text) <= 40 else text[:39] + "…"


def _canonicalizer_for(dataset: Dataset):
    from app.audit.canonical import ValueCanonicalizer

    return ValueCanonicalizer()


__all__ = [
    "DEFAULT_PAIRS",
    "MAX_PAIRS",
    "MAX_SIMILARITY_ROWS",
    "SimilarityPair",
    "SimilarityRequest",
    "SimilarityResponse",
    "compute_similarity",
]
