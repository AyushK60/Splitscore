"""Supporting distribution diagnostics.

These numbers describe the split. They are **not** leakage findings, and the
module keeps them in a separate type (:class:`~app.audit.types.Diagnostics`) so
no caller can accidentally merge them into the findings list. Distribution shift
and class imbalance are properties a modeller needs to know about; neither is a
leakage mechanism on its own.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.audit.canonical import ValueCanonicalizer
from app.audit.tokens import column_missing_mask, column_tokens
from app.audit.types import (
    CategoryShare,
    ColumnMissingness,
    Diagnostics,
    DistributionSummary,
    SplitCounts,
)
from app.core.config import DiagnosticsLimits

OTHER_BUCKET_LABEL = "(all remaining categories)"

MISSINGNESS_NOTE = (
    "Missingness differences between the splits are reported because they change how a split "
    "behaves in practice. A difference in missingness is not by itself a leakage mechanism."
)

DISCLAIMER = (
    "These diagnostics support interpretation; they are not leakage findings. Distribution shift "
    "and class imbalance are properties of a split, not evidence that information crossed the "
    "train/test boundary. Read them alongside the findings above, and do not treat a small "
    "distribution gap as proof that a split is sound."
)

CONTINUOUS_NOTE = (
    "The target is treated as continuous: descriptive statistics and a shared-bin histogram are "
    "shown instead of per-value class proportions, because treating every distinct value as its own "
    "class would be meaningless."
)


def split_counts(train_rows: int, test_rows: int, total_rows: int) -> SplitCounts:
    return SplitCounts(train_rows=train_rows, test_rows=test_rows, total_rows=total_rows)


def missingness_table(
    frame: pd.DataFrame,
    *,
    columns: list[str],
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    canonicalizer: ValueCanonicalizer,
    limits: DiagnosticsLimits,
) -> list[ColumnMissingness]:
    """Missing counts per column per split, ordered by the widest gap first."""
    train_rows = int(train_mask.sum())
    test_rows = int(test_mask.sum())
    rows: list[ColumnMissingness] = []
    for column in columns:
        missing = column_missing_mask(frame, column, canonicalizer)
        train_missing = int(missing[train_mask].sum())
        test_missing = int(missing[test_mask].sum())
        train_ratio = train_missing / train_rows if train_rows else 0.0
        test_ratio = test_missing / test_rows if test_rows else 0.0
        rows.append(
            ColumnMissingness(
                column=column,
                train_missing=train_missing,
                train_missing_ratio=round(train_ratio, 6),
                test_missing=test_missing,
                test_missing_ratio=round(test_ratio, 6),
                missing_ratio_gap=round(abs(test_ratio - train_ratio), 6),
            )
        )
    rows.sort(key=lambda row: (-row.missing_ratio_gap, -max(row.train_missing, row.test_missing), row.column))
    return rows[: limits.max_missingness_columns]


def target_distribution(
    frame: pd.DataFrame,
    *,
    target_column: str,
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    canonicalizer: ValueCanonicalizer,
    limits: DiagnosticsLimits,
) -> DistributionSummary:
    """Categorical or continuous summary of the target, chosen by distinct count."""
    tokens = column_tokens(frame, target_column, canonicalizer)
    missing = column_missing_mask(frame, target_column, canonicalizer)
    numeric = pd.to_numeric(frame[target_column], errors="coerce").to_numpy(dtype=float, na_value=np.nan)

    train_missing = int(missing[train_mask].sum())
    test_missing = int(missing[test_mask].sum())

    train_non_missing = train_mask & ~missing
    test_non_missing = test_mask & ~missing
    distinct = len({tokens[i] for i in np.nonzero(~missing)[0].tolist()})

    if distinct <= limits.categorical_max_unique:
        return _categorical(
            tokens=tokens,
            train_non_missing=train_non_missing,
            test_non_missing=test_non_missing,
            train_missing=train_missing,
            test_missing=test_missing,
            column=target_column,
            limits=limits,
        )

    numeric_ratio = float(np.isfinite(numeric).sum()) / max(int((~missing).sum()), 1)
    if numeric_ratio >= 0.8:
        return _continuous(
            numeric=numeric,
            missing=missing,
            train_mask=train_mask,
            test_mask=test_mask,
            column=target_column,
            limits=limits,
            train_missing=train_missing,
            test_missing=test_missing,
        )

    return DistributionSummary(
        column=target_column,
        kind="not_available",
        train_missing=train_missing,
        test_missing=test_missing,
        note=(
            f"The target has {distinct} distinct non-missing values, more than the configured "
            f"categorical cut-off of {limits.categorical_max_unique}, and only "
            f"{numeric_ratio:.0%} of them parse as numbers. Per-value proportions would be "
            "meaningless at this cardinality and no numeric summary applies, so no target "
            "distribution is produced."
        ),
    )


def _categorical(
    *,
    tokens: list[str],
    train_non_missing: np.ndarray,
    test_non_missing: np.ndarray,
    train_missing: int,
    test_missing: int,
    column: str,
    limits: DiagnosticsLimits,
) -> DistributionSummary:
    train_rows = int(train_non_missing.sum())
    test_rows = int(test_non_missing.sum())

    train_counts: dict[str, int] = {}
    for i in np.nonzero(train_non_missing)[0].tolist():
        train_counts[tokens[i]] = train_counts.get(tokens[i], 0) + 1
    test_counts: dict[str, int] = {}
    for i in np.nonzero(test_non_missing)[0].tolist():
        test_counts[tokens[i]] = test_counts.get(tokens[i], 0) + 1

    categories = sorted(
        set(train_counts) | set(test_counts),
        key=lambda name: (-(train_counts.get(name, 0) + test_counts.get(name, 0)), name),
    )

    shares: list[CategoryShare] = []
    max_gap = 0.0
    for name in categories:
        train_count = train_counts.get(name, 0)
        test_count = test_counts.get(name, 0)
        train_ratio = train_count / train_rows if train_rows else 0.0
        test_ratio = test_count / test_rows if test_rows else 0.0
        gap = abs(test_ratio - train_ratio)
        max_gap = max(max_gap, gap)
        shares.append(
            CategoryShare(
                category=name,
                train_count=train_count,
                train_ratio=round(train_ratio, 6),
                test_count=test_count,
                test_ratio=round(test_ratio, 6),
                ratio_gap=round(gap, 6),
            )
        )

    if len(shares) > limits.max_categories_shown:
        shown = shares[: limits.max_categories_shown]
        rest = shares[limits.max_categories_shown :]
        rest_train = sum(s.train_count for s in rest)
        rest_test = sum(s.test_count for s in rest)
        shown.append(
            CategoryShare(
                category=OTHER_BUCKET_LABEL,
                train_count=rest_train,
                train_ratio=round(rest_train / train_rows, 6) if train_rows else 0.0,
                test_count=rest_test,
                test_ratio=round(rest_test / test_rows, 6) if test_rows else 0.0,
                ratio_gap=round(
                    abs(
                        (rest_test / test_rows if test_rows else 0.0)
                        - (rest_train / train_rows if train_rows else 0.0)
                    ),
                    6,
                ),
                is_other_bucket=True,
            )
        )
        shares = shown

    return DistributionSummary(
        column=column,
        kind="categorical",
        categories=shares,
        train_missing=train_missing,
        test_missing=test_missing,
        max_abs_ratio_gap=round(max_gap, 6),
        note=(
            f"Proportions are computed over non-missing target values only "
            f"({train_rows} train, {test_rows} test). The largest absolute proportion difference "
            f"across the true categories is {max_gap:.1%}. A difference this size is a class-share "
            "difference, which is not by itself leakage."
        ),
    )


def _continuous(
    *,
    numeric: np.ndarray,
    missing: np.ndarray,
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    column: str,
    limits: DiagnosticsLimits,
    train_missing: int,
    test_missing: int,
) -> DistributionSummary:
    train_values = numeric[train_mask & ~missing & np.isfinite(numeric)]
    test_values = numeric[test_mask & ~missing & np.isfinite(numeric)]

    combined = np.concatenate([train_values, test_values]) if train_values.size or test_values.size else np.array([])
    if combined.size == 0:
        return DistributionSummary(
            column=column,
            kind="not_available",
            train_missing=train_missing,
            test_missing=test_missing,
            note="No numeric target values were available, so no distribution is produced.",
        )

    low = float(np.min(combined))
    high = float(np.max(combined))
    bins = max(1, limits.histogram_bins)
    if high == low:
        edges = np.array([low, high if high != low else low + 1.0])
        bins = 1
    else:
        edges = np.linspace(low, high, bins + 1)

    train_hist, _ = np.histogram(train_values, bins=edges) if train_values.size else (np.zeros(bins, dtype=int), edges)
    test_hist, _ = np.histogram(test_values, bins=edges) if test_values.size else (np.zeros(bins, dtype=int), edges)

    return DistributionSummary(
        column=column,
        kind="continuous",
        train_missing=train_missing,
        test_missing=test_missing,
        train_stats=_describe(train_values),
        test_stats=_describe(test_values),
        histogram_edges=[round(float(edge), 6) for edge in edges.tolist()],
        train_histogram=[int(value) for value in train_hist.tolist()],
        test_histogram=[int(value) for value in test_hist.tolist()],
        note=(
            CONTINUOUS_NOTE
            + " The histogram uses shared bin edges computed over both splits, so the two series "
            "are directly comparable."
        ),
    )


def _describe(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {"n": 0.0}
    return {
        "n": float(values.size),
        "mean": round(float(np.mean(values)), 6),
        "std": round(float(np.std(values, ddof=1)) if values.size > 1 else 0.0, 6),
        "min": round(float(np.min(values)), 6),
        "p25": round(float(np.percentile(values, 25)), 6),
        "median": round(float(np.median(values)), 6),
        "p75": round(float(np.percentile(values, 75)), 6),
        "max": round(float(np.max(values)), 6),
    }


def build_diagnostics(
    frame: pd.DataFrame,
    *,
    resolved_columns: list[str],
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    canonicalizer: ValueCanonicalizer,
    limits: DiagnosticsLimits,
    target_column: str | None,
) -> Diagnostics:
    """Assemble the diagnostics block for one split."""
    target: DistributionSummary | None = None
    if target_column is not None:
        target = target_distribution(
            frame,
            target_column=target_column,
            train_mask=train_mask,
            test_mask=test_mask,
            canonicalizer=canonicalizer,
            limits=limits,
        )

    return Diagnostics(
        counts=split_counts(int(train_mask.sum()), int(test_mask.sum()), len(frame)),
        missingness=missingness_table(
            frame,
            columns=resolved_columns,
            train_mask=train_mask,
            test_mask=test_mask,
            canonicalizer=canonicalizer,
            limits=limits,
        ),
        missingness_note=MISSINGNESS_NOTE,
        target=target,
        disclaimer=DISCLAIMER,
    )


__all__ = [
    "DISCLAIMER",
    "MISSINGNESS_NOTE",
    "OTHER_BUCKET_LABEL",
    "build_diagnostics",
    "missingness_table",
    "split_counts",
    "target_distribution",
]
