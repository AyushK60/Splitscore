"""Vectorised canonical-token extraction.

:mod:`app.audit.canonical` defines *what* a canonical token is, one value at a
time. Building a 10,000 x 100 signature matrix value-by-value in Python is slow,
so this module produces the same tokens with pandas string operations wherever
that is exactly equivalent, and falls back to the value-by-value path only for
the opt-in numeric-string normalisation (where a per-value decimal parse is
unavoidable).

Equivalence between the two paths is asserted directly in the test suite.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.audit.canonical import MISSING_TOKEN, ValueCanonicalizer


def column_tokens(frame: pd.DataFrame, column: str, canonicalizer: ValueCanonicalizer) -> list[str]:
    """Canonical comparison token for every row of one column.

    Identical to ``[canonicalizer.token(v) for v in frame[column]]``; see the
    module docstring for why the fast path is safe.
    """
    series = frame[column]
    if canonicalizer.normalize_numeric_strings:
        return [canonicalizer.token(v) for v in series.tolist()]

    text = series.str.strip() if canonicalizer.strip_whitespace else series
    missing = text.eq("")
    missing_tokens = canonicalizer.missing_tokens
    if missing_tokens:
        missing = missing | text.isin(list(missing_tokens))
    tokens = text.where(~missing, MISSING_TOKEN)
    return tokens.tolist()


def column_missing_mask(
    frame: pd.DataFrame, column: str, canonicalizer: ValueCanonicalizer
) -> np.ndarray:
    """Boolean mask of missing cells under the audit's missing-value rule."""
    series = frame[column]
    if canonicalizer.normalize_numeric_strings:
        return np.fromiter(
            (canonicalizer.missing(v) for v in series.tolist()),
            dtype=bool,
            count=len(series),
        )
    text = series.str.strip() if canonicalizer.strip_whitespace else series
    missing = text.eq("")
    missing_tokens = canonicalizer.missing_tokens
    if missing_tokens:
        missing = missing | text.isin(list(missing_tokens))
    return missing.to_numpy(dtype=bool)


def feature_signatures(
    frame: pd.DataFrame,
    feature_columns: list[str],
    canonicalizer: ValueCanonicalizer,
) -> list[tuple[str, ...]]:
    """One canonical feature tuple per row, in the given column order.

    Column *order* is part of the report's settings, so the tuple order is the
    user's feature order rather than the file's column order. Equality of two
    rows therefore does not depend on column ordering.
    """
    if not feature_columns:
        return [() for _ in range(len(frame))]
    per_column = [column_tokens(frame, column, canonicalizer) for column in feature_columns]
    return list(zip(*per_column, strict=True))


def column_feature_values(
    frame: pd.DataFrame, feature_columns: list[str]
) -> dict[str, list[str]]:
    return {column: frame[column].tolist() for column in feature_columns}


__all__ = [
    "column_feature_values",
    "column_missing_mask",
    "column_tokens",
    "feature_signatures",
]
