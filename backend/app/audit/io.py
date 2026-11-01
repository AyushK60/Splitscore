"""CSV ingestion: validation, stable row IDs and advisory column typing.

Design choices worth defending in a review
------------------------------------------
**Nothing is silently repaired.** Duplicate headers, malformed rows, an empty
file, too many rows/columns or too few rows all raise a typed error naming the
offending items. SplitScope never drops "bad lines" and never truncates.

**Every cell stays a string.** ``na_filter=False`` and ``keep_default_na=False``
are used so that the loader cannot decide on its own that ``"NA"`` is missing.
See :mod:`app.audit.canonical` for the missing-value contract.

**Row IDs are positional, not content-derived.** ``row-000123`` is the 124th
physical data row of the file. A content hash would be worse: the interesting
case for this tool is *exactly duplicated rows*, and a content-derived ID would
give both copies the same ID, making evidence impossible to point at. Positional
IDs are stable for a given file (and therefore reproducible across re-uploads of
identical bytes, which the SHA-256 fingerprint confirms) but are not stable
across row reordering; that limitation is documented in the report.
"""

from __future__ import annotations

import csv
import io as _io
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from app.audit.types import ColumnTypeInfo
from app.core.errors import (
    LimitExceededError,
    MalformedCsvError,
    UnsupportedInputError,
    ValidationFailure,
)
from app.core.hashing import sha256_bytes

ROW_ID_PREFIX = "row-"
ROW_ID_WIDTH = 6

_DATE_LIKE_PATTERNS = (
    re.compile(r"^\d{4}-\d{2}-\d{2}"),  # 2024-03-01, 2024-03-01T10:00:00Z
    re.compile(r"^\d{4}/\d{1,2}/\d{1,2}"),
    re.compile(r"^\d{1,2}/\d{1,2}/\d{4}"),
    re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}"),  # 01-Mar-2024
    re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}"),
    re.compile(r"^\d{10}$|^\d{13}$"),  # epoch seconds / milliseconds
)

_NUMERIC_NAME_HINTS = ("id", "code", "zip", "postal", "phone")
_NAME_DATE_HINTS = ("date", "time", "_ts", "timestamp", "datetime", "created", "updated")


@dataclass
class LoadedCsv:
    """A validated, immutably-typed view of an uploaded CSV."""

    frame: pd.DataFrame
    row_ids: list[str]
    columns: list[str]
    fingerprint_sha256: str
    encoding: str
    warnings: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.frame)

    @property
    def column_count(self) -> int:
        return len(self.columns)


def make_row_ids(count: int) -> list[str]:
    """Stable internal row IDs, independent of any user-supplied ID column."""
    return [f"{ROW_ID_PREFIX}{i + 1:0{ROW_ID_WIDTH}d}" for i in range(count)]


def _decode(data: bytes) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    if b"\x00" in data:
        raise MalformedCsvError(
            "The file contains NUL bytes, which is not valid CSV text.",
            details={"hint": "This usually means a binary file (for example .xlsx or .zip) was renamed to .csv."},
        )
    try:
        return data.decode("utf-8-sig"), "utf-8-sig", warnings
    except UnicodeDecodeError:
        warnings.append(
            "The file is not valid UTF-8; it was decoded as Windows-1252. "
            "Accented or non-Latin characters may be misread."
        )
        return data.decode("cp1252", errors="replace"), "cp1252", warnings


def _parse_header(text: str) -> list[str]:
    reader = csv.reader(_io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise MalformedCsvError("The file is empty.") from None
    except csv.Error as exc:
        raise MalformedCsvError(f"The CSV header could not be parsed: {exc}") from None
    return list(header)


def _validate_header(header: list[str], max_columns: int) -> list[str]:
    if not header:
        raise MalformedCsvError("The CSV has no header row.")

    blank_positions = [str(i + 1) for i, name in enumerate(header) if name.strip() == ""]
    if blank_positions:
        raise ValidationFailure(
            "Some column names are blank, which makes the header ambiguous.",
            details={"blank_positions": blank_positions},
        )

    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for name in header:
        seen[name] = seen.get(name, 0) + 1
    duplicates = sorted(name for name, count in seen.items() if count > 1)
    if duplicates:
        raise ValidationFailure(
            "Duplicate column names are ambiguous and cannot be resolved automatically.",
            details={
                "duplicate_columns": duplicates[:20],
                "duplicate_count": len(duplicates),
                "suggestion": "Rename the duplicated columns in the source file and upload again.",
            },
        )

    if len(header) > max_columns:
        raise LimitExceededError(
            f"The file has {len(header)} columns, above the configured limit of {max_columns}.",
            details={"columns_found": len(header), "columns_allowed": max_columns},
        )
    return header


def read_csv_bytes(
    data: bytes,
    *,
    max_bytes: int,
    max_rows: int,
    max_columns: int,
    min_rows: int,
    min_columns: int,
    filename: str | None = None,
) -> LoadedCsv:
    """Validate and load CSV bytes under explicit limits.

    Raises a typed :class:`~app.core.errors.SplitScopeError` subclass instead of
    repairing the input.
    """
    if len(data) == 0:
        raise MalformedCsvError("The uploaded file is empty (0 bytes).")
    if len(data) > max_bytes:
        raise LimitExceededError(
            f"The file is {len(data) / (1024 * 1024):.2f} MB, above the configured "
            f"limit of {max_bytes / (1024 * 1024):.2f} MB.",
            details={
                "bytes_found": len(data),
                "bytes_allowed": max_bytes,
                "filename": filename or "(unnamed)",
            },
        )

    text, encoding, warnings = _decode(data)
    if text.strip() == "":
        raise MalformedCsvError("The uploaded file contains only whitespace.")

    header = _validate_header(_parse_header(text), max_columns)

    try:
        frame = pd.read_csv(
            _io.StringIO(text),
            dtype=str,
            na_filter=False,
            keep_default_na=False,
            skipinitialspace=False,
            on_bad_lines="error",
            engine="c",
        )
    except pd.errors.EmptyDataError:
        raise MalformedCsvError(
            "The CSV has a header but no data rows.",
            details={"columns": header[:20], "column_count": len(header)},
        ) from None
    except pd.errors.ParserError as exc:
        raise MalformedCsvError(
            f"The CSV is malformed and could not be parsed: {exc}",
            details={"hint": "Check for unescaped quotes, stray delimiters or a row with the wrong number of fields."},
        ) from None
    except UnicodeError as exc:  # pragma: no cover - defensive
        raise MalformedCsvError(f"The CSV could not be decoded: {exc}") from None

    # Re-assert the header we validated: pandas would have mangled duplicates.
    if list(frame.columns) != header:
        raise MalformedCsvError(
            "The parsed header does not match the file header.",
            details={"expected": header[:20], "parsed": [str(c) for c in frame.columns][:20]},
        )

    if frame.shape[0] == 0:
        # pandas raises EmptyDataError only in some configurations; the empty
        # frame is checked explicitly so the message never depends on that.
        raise MalformedCsvError(
            "The CSV has a header but no data rows.",
            details={"columns": header[:20], "column_count": len(header)},
        )
    if frame.shape[0] > max_rows:
        raise LimitExceededError(
            f"The file has {frame.shape[0]} rows, above the configured limit of {max_rows}.",
            details={"rows_found": int(frame.shape[0]), "rows_allowed": max_rows},
        )
    if frame.shape[1] < min_columns:
        raise UnsupportedInputError(
            f"The file has {frame.shape[1]} columns; at least {min_columns} are required.",
            details={"columns_found": int(frame.shape[1]), "columns_required": min_columns},
        )
    if frame.shape[0] < min_rows:
        raise ValidationFailure(
            f"The dataset has {frame.shape[0]} rows; at least {min_rows} are required "
            "for a train/test leakage audit.",
            details={"rows_found": int(frame.shape[0]), "rows_required": min_rows},
        )

    non_string = [
        str(name)
        for name, dtype in frame.dtypes.items()
        if not isinstance(dtype, object) and dtype.name != "str" and dtype.kind not in {"O", "U"}
    ]
    if non_string:  # pragma: no cover - defensive guard against pandas dtype changes
        raise MalformedCsvError(
            "Internal error: some columns were not loaded as text.",
            details={"columns": non_string[:20]},
        )

    frame = frame.reset_index(drop=True)
    return LoadedCsv(
        frame=frame,
        row_ids=make_row_ids(len(frame)),
        columns=[str(c) for c in frame.columns],
        fingerprint_sha256=sha256_bytes(data),
        encoding=encoding,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# Advisory typing
# --------------------------------------------------------------------------- #


def _is_date_like(sample: list[str]) -> bool:
    non_empty = [s for s in sample if s.strip() != ""]
    if not non_empty:
        return False
    return all(any(p.match(s.strip()) for p in _DATE_LIKE_PATTERNS) for s in non_empty)


def _default_missing(value: object) -> bool:
    """Missingness under the no-configuration default (empty string only).

    Before an audit configuration exists the UI has no canonicalizer, so column
    statistics use this documented default. Once an audit runs, the same
    statistics are recomputed with the audit's own missing-value predicate so
    that diagnostics and findings never disagree.
    """
    return value is None or value == ""


def column_type_info(
    series: pd.Series,
    *,
    name: str,
    max_examples: int = 3,
    numeric_ratio_threshold: float = 0.8,
    missing_predicate: Callable[[object], bool] | None = None,
) -> ColumnTypeInfo:
    """Advisory type information for one column.

    Datetime inference is *gated* on cheap string-shape or column-name hints so
    that the loader never attempts a full-column timestamp parse on every
    numeric column of a wide dataset.
    """
    is_missing_value = missing_predicate or _default_missing
    total = int(series.shape[0])
    values = series.tolist()
    missing_mask = [is_missing_value(v) for v in values]
    missing_count = sum(1 for m in missing_mask if m)
    non_missing = [v for v, m in zip(values, missing_mask, strict=True) if not m]
    distinct = len(set(non_missing))

    numeric_ratio = 0.0
    if non_missing:
        parsed = pd.to_numeric(series, errors="coerce")
        numeric_ratio = float(parsed.notna().sum()) / float(len(non_missing))
    looks_numeric = bool(non_missing) and numeric_ratio >= numeric_ratio_threshold

    datetime_ratio = 0.0
    looks_datetime = False
    name_lower = name.lower()
    name_hint = any(h in name_lower for h in _NAME_DATE_HINTS)
    if non_missing and not looks_numeric:
        sample = non_missing[: min(5, len(non_missing))]
        if name_hint or _is_date_like(sample):
            parsed_dt = to_datetime_series(series)
            datetime_ratio = float(parsed_dt.notna().sum()) / float(len(non_missing))
            # Half is enough for the advisory flag: the chronology rule verifies
            # every value itself and reports unparsable ones explicitly.
            looks_datetime = datetime_ratio >= 0.5

    looks_identifier = (
        len(non_missing) >= 5
        and distinct == len(non_missing)
        and not looks_numeric
        and not looks_datetime
    )
    if looks_numeric and distinct == len(non_missing) and any(
        hint in name_lower for hint in _NUMERIC_NAME_HINTS
    ):
        # Advisory only: rows that are unique *and* named like an identifier are
        # probably keys. The near-duplicate rule makes its own decision from
        # numeric_parse_ratio, so this flag never silently changes analysis.
        looks_identifier = True
        looks_numeric = False

    return ColumnTypeInfo(
        name=name,
        numeric_parse_ratio=round(numeric_ratio, 6),
        datetime_parse_ratio=round(datetime_ratio, 6),
        distinct_values=distinct,
        missing_count=missing_count,
        missing_ratio=round(missing_count / total, 6) if total else 0.0,
        looks_numeric=looks_numeric,
        looks_datetime=looks_datetime,
        looks_identifier=looks_identifier,
        example_values=list(non_missing[:max_examples]),
    )


def infer_column_types(
    frame: pd.DataFrame,
    *,
    missing_predicate: Callable[[object], bool] | None = None,
) -> dict[str, ColumnTypeInfo]:    return {
        str(name): column_type_info(
            frame[name], name=str(name), missing_predicate=missing_predicate
        )
        for name in frame.columns
    }


def to_datetime_series(series: pd.Series) -> pd.Series:
    """Parse a text column to timestamps, coercing failures to NaT.

    Naive timestamps are interpreted as UTC; mixed offsets are normalised to
    UTC. Both conventions are stated in the chronology rule's assumptions.
    """
    try:
        parsed = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    except (ValueError, TypeError):
        parsed = pd.to_datetime(series, errors="coerce", utc=True)
    return parsed


#: `str`-typed column dtype name that the loader expects from pandas.
TEXT_DTYPE_NAMES = frozenset({"str", "string", "object"})


__all__ = [
    "LoadedCsv",
    "column_type_info",
    "infer_column_types",
    "make_row_ids",
    "read_csv_bytes",
    "to_datetime_series",
]
