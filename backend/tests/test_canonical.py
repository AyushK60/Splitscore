"""Canonicalization and missing-value semantics.

These tests pin the contract that every other rule depends on: what counts as
missing, and what counts as equal.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.audit.canonical import (
    MISSING_TOKEN,
    ValueCanonicalizer,
    canonical_numeric,
    is_missing,
    parse_decimal,
)
from app.audit.tokens import column_tokens

from .conftest import make_dataset


def test_empty_string_is_missing_but_literal_na_is_a_value():
    canonicalizer = ValueCanonicalizer()
    assert canonicalizer.missing("") is True
    assert canonicalizer.missing(None) is True
    assert canonicalizer.missing("NA") is False
    assert canonicalizer.missing("NaN") is False
    assert canonicalizer.missing("null") is False
    assert canonicalizer.token("NA") == "NA"
    assert canonicalizer.token("") == MISSING_TOKEN


def test_configured_missing_tokens_are_opt_in():
    canonicalizer = ValueCanonicalizer(missing_tokens=["NA", "NULL"])
    assert canonicalizer.missing("NA") is True
    assert canonicalizer.missing("null") is False  # exact match only, no case folding
    assert canonicalizer.token("NULL") == MISSING_TOKEN


def test_whitespace_stripping_is_configurable_and_only_trims_the_edges():
    strict = ValueCanonicalizer(strip_whitespace=False)
    loose = ValueCanonicalizer(strip_whitespace=True)
    assert strict.token(" a ") == " a "
    assert loose.token(" a ") == "a"
    assert loose.token("   ") == MISSING_TOKEN
    assert strict.token("   ") == "   "


def test_case_and_unicode_are_never_folded():
    canonicalizer = ValueCanonicalizer()
    assert canonicalizer.values_equal("North", "north") is False
    assert canonicalizer.values_equal("café", "cafe\u0301") is False


def test_numeric_normalization_is_off_by_default_and_opt_in():
    default = ValueCanonicalizer()
    assert default.token("1.0") != default.token("1")
    assert default.token("01") != default.token("1")

    normalized = ValueCanonicalizer(normalize_numeric_strings=True)
    assert normalized.token("1.0") == normalized.token("1") == "1"
    assert normalized.token("01") == "1"
    assert normalized.token("1e0") == "1"
    assert normalized.token("-0.0") == "0"
    assert normalized.token("1.50") == "1.5"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", Decimal("1")),
        ("-2.5", Decimal("-2.5")),
        ("1e3", Decimal("1000")),
        ("nan", None),
        ("NaN", None),
        ("inf", None),
        ("Infinity", None),
        ("1,5", None),
        ("", None),
        ("0x10", None),
        ("1_000", None),
    ],
)
def test_parse_decimal_rejects_non_finite_and_junk(raw, expected):
    assert parse_decimal(raw) == expected


def test_canonical_numeric_normalises_zero_and_exponents():
    assert canonical_numeric(Decimal("1000.0")) == "1000"
    assert canonical_numeric(Decimal("-0")) == "0"
    assert canonical_numeric(Decimal("0.500")) == "0.5"


def test_values_equal_uses_numeric_equivalence_but_never_equates_missing():
    canonicalizer = ValueCanonicalizer()
    assert canonicalizer.values_equal("1", "1.0") is True
    assert canonicalizer.values_equal("1", "2") is False
    assert canonicalizer.values_equal("", "") is False
    assert canonicalizer.values_equal("", "0") is False
    assert canonicalizer.values_equal("NA", "NA") is True


def test_vectorized_tokens_match_the_value_by_value_path():
    """The fast pandas path and the scalar path must agree exactly."""
    values = ["1", " 2 ", "", "NA", "3.50", "3.5", "x", "  ", "-0", "0"]
    dataset = make_dataset([{"col": value, "k": str(index)} for index, value in enumerate(values)])

    for strip in (True, False):
        for normalize in (False, True):
            for missing_tokens in ((), ("NA",)):
                canonicalizer = ValueCanonicalizer(
                    strip_whitespace=strip,
                    normalize_numeric_strings=normalize,
                    missing_tokens=missing_tokens,
                )
                fast = column_tokens(dataset.frame, "col", canonicalizer)
                scalar = [canonicalizer.token(value) for value in dataset.values("col")]
                assert fast == scalar, (strip, normalize, missing_tokens)


def test_is_missing_ignores_non_string_values():
    assert is_missing(0) is False
    assert is_missing(False) is False
