"""Numerical core of the Visual Explorer.

Every function here works on the *full* population the caller selected — never
on a render sample — and returns typed results that separate a value from its
denominator. The conventions are the profiler's (``app.research.profiling``):

* an **empty cell** is missing; no other string is silently treated as missing;
* numeric columns are parsed with ``pd.to_numeric``; cells that neither parse
  nor are empty are counted as ``unparsed`` and excluded from numeric
  statistics, never coerced to zero;
* a statistic that cannot be defined (correlation of a constant column, fewer
  valid pairs than the minimum) is returned as ``None`` **with a warning code**
  instead of a fabricated number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.audit.dataset import Dataset
from app.core.errors import ValidationFailure

MISSING_CELL = ""
#: A correlation is only reported when at least this many complete pairs exist.
#: (Two points always produce |r| = 1, which would read as a finding; three is
#: the smallest sample where the coefficient carries information.)
CORR_MIN_PAIRS = 3
#: Tolerance below which a column counts as constant for correlation purposes.
CONSTANT_TOLERANCE = 0.0
#: Hard cap on distinct levels listed individually in a frequency chart.
MAX_CATEGORY_LEVELS = 30
#: Hard cap on histogram bins.
MAX_BINS = 60
MIN_BINS = 5
DEFAULT_BINS = 20
#: Outlier examples returned per box plot (counts are always complete).
MAX_OUTLIER_EXAMPLES = 20


@dataclass(frozen=True)
class NumericColumn:
    """A parsed numeric column with honest exclusion counts."""

    values: np.ndarray  # float, NaN where missing or unparsable
    missing: int  # empty cells
    unparsed: int  # non-empty cells that do not parse as numbers

    @property
    def valid(self) -> np.ndarray:
        return self.values[np.isfinite(self.values)]

    @property
    def valid_count(self) -> int:
        return int(np.isfinite(self.values).sum())


def parse_numeric(dataset: Dataset, column: str) -> NumericColumn:
    """Parse one column as numbers under the shared missingness policy."""
    raw = dataset.series(column)
    values = raw.astype(object).where(pd.notna(raw), MISSING_CELL)
    text = [v if isinstance(v, str) else MISSING_CELL for v in values.tolist()]
    missing = sum(1 for v in text if v == MISSING_CELL)
    parsed = pd.to_numeric(pd.Series(text).replace(MISSING_CELL, None), errors="coerce")
    arr = parsed.to_numpy(dtype=float)
    unparsed = sum(
        1
        for v, p in zip(text, arr, strict=True)
        if v != MISSING_CELL and not np.isfinite(p)
    )
    return NumericColumn(values=arr, missing=missing, unparsed=unparsed)


def text_values(dataset: Dataset, column: str) -> tuple[list[str], int]:
    """A column as display text plus its missing-cell count."""
    raw = dataset.series(column)
    out: list[str] = []
    missing = 0
    for value in raw.tolist():
        if value is None or (isinstance(value, float) and np.isnan(value)) or value == MISSING_CELL:
            out.append(MISSING_CELL)
            missing += 1
        else:
            out.append(str(value))
    return out, missing


# --------------------------------------------------------------------------- #
# Correlation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CorrResult:
    """One pairwise coefficient with its evidence, or None plus a reason."""

    coefficient: float | None
    n_valid: int
    warning: str | None = None
    missing_policy: str = "pairwise_complete"


def _guard_constant(x: np.ndarray, y: np.ndarray) -> str | None:
    if float(np.max(x) - np.min(x)) <= CONSTANT_TOLERANCE:
        return "constant_x"
    if float(np.max(y) - np.min(y)) <= CONSTANT_TOLERANCE:
        return "constant_y"
    return None


def pearson(x: np.ndarray, y: np.ndarray) -> CorrResult:
    """Pairwise-complete Pearson correlation, undefined where not defined."""
    mask = np.isfinite(x) & np.isfinite(y)
    n = int(mask.sum())
    if n < CORR_MIN_PAIRS:
        return CorrResult(None, n, "insufficient_pairs")
    xs, ys = x[mask].astype(float), y[mask].astype(float)
    constant = _guard_constant(xs, ys)
    if constant:
        return CorrResult(None, n, constant)
    r = float(np.corrcoef(xs, ys)[0, 1])
    return CorrResult(coefficient=max(-1.0, min(1.0, r)), n_valid=n)


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Ranks 1..n with average ranks for ties (the standard Spearman basis)."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    sorted_values = values[order]
    i = 0
    while i < values.size:
        j = i
        while j + 1 < values.size and sorted_values[j + 1] == sorted_values[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> CorrResult:
    """Spearman rank correlation: Pearson on average ranks, pairwise complete."""
    mask = np.isfinite(x) & np.isfinite(y)
    n = int(mask.sum())
    if n < CORR_MIN_PAIRS:
        return CorrResult(None, n, "insufficient_pairs")
    xs, ys = x[mask].astype(float), y[mask].astype(float)
    constant = _guard_constant(xs, ys)
    if constant:
        return CorrResult(None, n, constant)
    rx, ry = _average_ranks(xs), _average_ranks(ys)
    r = float(np.corrcoef(rx, ry)[0, 1])
    return CorrResult(coefficient=max(-1.0, min(1.0, r)), n_valid=n)


CORRELATION_METHODS = {"pearson": pearson, "spearman": spearman}


# --------------------------------------------------------------------------- #
# Distributions
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Histogram:
    """A histogram of the valid (non-missing, parsable) values."""

    edges: list[float]
    counts: list[int]
    valid: int
    missing: int
    unparsed: int
    population: int


def histogram(column: NumericColumn, bins: int = DEFAULT_BINS) -> Histogram:
    """Counts over ``[min, max]`` with equal-width bins.

    Bin count is clamped to ``[MIN_BINS, MAX_BINS]``. The bin count is a
    display choice, never part of the statistic: totals always sum to the
    valid count, which is reported alongside the population.
    """
    bins = max(MIN_BINS, min(int(bins), MAX_BINS))
    valid = column.valid
    if valid.size == 0:
        return Histogram(edges=[], counts=[], valid=0, missing=column.missing,
                         unparsed=column.unparsed, population=column.values.size)
    lo, hi = float(valid.min()), float(valid.max())
    if hi - lo <= 0.0:
        # A single distinct value: one bin holds everything between its edges.
        edges = [lo, hi]
        counts = [int(valid.size)]
        return Histogram(edges=edges, counts=counts, valid=int(valid.size),
                         missing=column.missing, unparsed=column.unparsed,
                         population=column.values.size)
    counts, edges = np.histogram(valid, bins=bins, range=(lo, hi))
    return Histogram(
        edges=[float(e) for e in edges],
        counts=[int(c) for c in counts],
        valid=int(valid.size),
        missing=column.missing,
        unparsed=column.unparsed,
        population=column.values.size,
    )


@dataclass(frozen=True)
class BoxStats:
    """Tukey box-plot statistics (linear-interpolated quartiles)."""

    n: int
    q1: float
    median: float
    q3: float
    whisker_low: float
    whisker_high: float
    iqr: float
    outlier_count: int
    outlier_examples: list[float] = field(default_factory=list)


def box_stats(column: NumericColumn) -> BoxStats | None:
    """Quartiles and 1.5*IQR whiskers; None when nothing is plottable."""
    valid = np.sort(column.valid)
    if valid.size == 0:
        return None
    q1, median, q3 = (float(q) for q in np.percentile(valid, [25, 50, 75], method="linear"))
    iqr = q3 - q1
    low_fence, high_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = valid[(valid >= low_fence) & (valid <= high_fence)]
    outliers = valid[(valid < low_fence) | (valid > high_fence)]
    # Whiskers reach to the most extreme *inside* values; with no inside values
    # (a degenerate all-outlier spread) they fall back to the quartiles.
    whisker_low = float(inside.min()) if inside.size else q1
    whisker_high = float(inside.max()) if inside.size else q3
    return BoxStats(
        n=int(valid.size),
        q1=q1,
        median=median,
        q3=q3,
        whisker_low=whisker_low,
        whisker_high=whisker_high,
        iqr=float(iqr),
        outlier_count=int(outliers.size),
        outlier_examples=[float(v) for v in outliers[:MAX_OUTLIER_EXAMPLES]],
    )


@dataclass(frozen=True)
class Frequencies:
    """Counts of a categorical column's distinct values."""

    levels: list[tuple[str, int]]  # (label, count), descending, capped
    other_count: int
    distinct: int
    missing: int
    population: int


def frequencies(values: list[str]) -> Frequencies:
    """Exact per-level counts, capped at MAX_CATEGORY_LEVELS + an other bucket."""
    counts: dict[str, int] = {}
    missing = 0
    for value in values:
        if value == MISSING_CELL:
            missing += 1
        else:
            counts[value] = counts.get(value, 0) + 1
    distinct = len(counts)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if distinct <= MAX_CATEGORY_LEVELS:
        return Frequencies(levels=ranked, other_count=0, distinct=distinct,
                           missing=missing, population=len(values))
    levels = ranked[:MAX_CATEGORY_LEVELS]
    other = sum(count for _, count in ranked[MAX_CATEGORY_LEVELS:])
    return Frequencies(levels=levels, other_count=other, distinct=distinct,
                       missing=missing, population=len(values))


def require_column(dataset: Dataset, column: str | None) -> str | None:
    """Validate an optional column reference against the dataset."""
    if column is None:
        return None
    if not isinstance(column, str) or not column:
        raise ValidationFailure("Column references must be non-empty strings.")
    if column not in dataset.columns:
        raise ValidationFailure(
            f"Column {column!r} is not present in the dataset.",
            details={"available_columns": dataset.columns[:50]},
        )
    return column
