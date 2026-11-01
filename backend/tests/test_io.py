"""CSV ingestion: validation, limits and stable row identifiers."""

from __future__ import annotations

import pytest

from app.audit.io import make_row_ids, read_csv_bytes
from app.core.errors import (
    LimitExceededError,
    MalformedCsvError,
    UnsupportedInputError,
    ValidationFailure,
)

from .conftest import rows_to_csv

BASE_KWARGS = {
    "max_bytes": 10 * 1024 * 1024,
    "max_rows": 10_000,
    "max_columns": 100,
    "min_rows": 20,
    "min_columns": 2,
}


def load(payload: bytes, **overrides):
    return read_csv_bytes(payload, **{**BASE_KWARGS, **overrides})


def test_row_ids_are_positional_and_zero_padded():
    assert make_row_ids(3) == ["row-000001", "row-000002", "row-000003"]
    assert make_row_ids(1)[0] == "row-000001"


def test_duplicate_column_names_are_rejected_with_the_names_listed():
    payload = b"a,b,a\n1,2,3\n"
    with pytest.raises(ValidationFailure) as error:
        load(payload, min_rows=1, min_columns=1)
    assert error.value.code == "validation_error"
    assert error.value.details["duplicate_columns"] == ["a"]


def test_blank_column_name_is_rejected():
    with pytest.raises(ValidationFailure):
        load(b"a,,b\n1,2,3\n", min_rows=1, min_columns=1)


def test_empty_file_is_rejected():
    with pytest.raises(MalformedCsvError):
        load(b"", min_rows=1, min_columns=1)


def test_header_without_rows_is_rejected():
    with pytest.raises(MalformedCsvError) as error:
        load(b"a,b\n", min_rows=0, min_columns=1)
    assert "no data rows" in error.value.message


def test_ragged_row_is_reported_as_malformed():
    with pytest.raises(MalformedCsvError) as error:
        load(b"a,b\n1,2\n3,4,5,6\n", min_rows=1, min_columns=1)
    assert error.value.code == "malformed_csv"


def test_nul_bytes_are_rejected_as_a_binary_file():
    with pytest.raises(MalformedCsvError) as error:
        load(b"a,b\n1,\x00\n", min_rows=1, min_columns=1)
    assert "NUL" in error.value.message


def test_byte_limit_is_enforced_without_truncating():
    payload = rows_to_csv([{"a": index, "b": index} for index in range(200)])
    with pytest.raises(LimitExceededError) as error:
        load(payload, max_bytes=100, min_rows=1, min_columns=1)
    assert error.value.details["bytes_found"] == len(payload)


def test_row_limit_is_enforced_with_the_exact_counts():
    payload = rows_to_csv([{"a": index, "b": index} for index in range(50)])
    with pytest.raises(LimitExceededError) as error:
        load(payload, max_rows=10, min_rows=1, min_columns=1)
    assert error.value.details == {"rows_found": 50, "rows_allowed": 10}


def test_column_limit_is_enforced():
    payload = rows_to_csv([{"a": 1, "b": 2, "c": 3, "d": 4}], columns=list("abcd"))
    with pytest.raises(LimitExceededError):
        load(payload, max_columns=3, min_rows=1, min_columns=1)


def test_too_few_rows_and_columns_are_rejected():
    small = rows_to_csv([{"a": 1, "b": 2}])
    with pytest.raises(ValidationFailure):
        load(small, min_rows=5)
    with pytest.raises(UnsupportedInputError):
        load(small, min_rows=1, min_columns=3)


def test_values_are_preserved_exactly_and_never_coerced():
    payload = b"a,b,c,d\n NA ,1.0,01,\n"
    loaded = load(payload, min_rows=1, min_columns=1)
    row = loaded.frame.iloc[0].tolist()
    assert row == [" NA ", "1.0", "01", ""]


def test_latin1_fallback_records_a_warning():
    payload = "city\nZürich\nZürich\n".encode("latin-1")
    loaded = load(payload, min_rows=1, min_columns=1)
    assert loaded.encoding == "cp1252"
    assert any("Windows-1252" in warning for warning in loaded.warnings)


def test_fingerprint_matches_sha256_of_the_uploaded_bytes():
    import hashlib

    payload = rows_to_csv([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
    loaded = load(payload, min_rows=1, min_columns=1)
    assert loaded.fingerprint_sha256 == hashlib.sha256(payload).hexdigest()


def test_quoted_fields_containing_commas_and_newlines_round_trip():
    payload = b'a,b\n"x,1","line1\nline2"\n'
    loaded = load(payload, min_rows=1, min_columns=1)
    assert loaded.frame.iloc[0].tolist() == ["x,1", "line1\nline2"]
