"""Explicit value canonicalization and missing-value semantics.

Why this module exists
----------------------
"Are these two rows duplicates?" is only a well-posed question once you have
written down (a) what counts as a missing value and (b) how values are mapped to
a comparison key. Both are easy to get silently wrong, so both are defined here,
in one place, and echoed into every report.

Missing values
--------------
CSV files are read with ``na_filter=False`` and ``keep_default_na=False``, so
**no cell is ever coerced by pandas**. A cell is missing only when, after
optional whitespace stripping, it is:

1. absent entirely (``None``), or
2. the empty string, or
3. an exact member of the user-configured ``missing_tokens`` list (empty by
   default).

Consequences, deliberately chosen:

* the literal string ``"NA"`` is a **value**, not a missing value;
* the literal string ``"NaN"`` is a **value**, not a missing value;
* ``" "`` (a single space) is missing only if whitespace stripping is enabled.

This is stricter than pandas' default and avoids the classic bug where a
legitimate category named ``NA`` silently disappears into the missing bucket.

Canonicalization
----------------
``canonical_value`` maps a raw cell to a comparison token:

1. missing -> :data:`MISSING_TOKEN` (only ever compared against itself, and
   only as an element of a tagged tuple, so it can never collide with real data)
2. else strip leading/trailing whitespace when ``strip_whitespace`` (default on)
3. else, when ``normalize_numeric_strings`` is on (default **off**) and the
   value parses as a finite decimal, replace it with its canonical decimal form
   so ``1``, ``1.0`` and ``01`` compare equal
4. else the stripped string itself

Step 3 is off by default because it is not always right: zero-padded codes such
as ``"01"`` and ``"007"`` are *different* identifiers that would be merged with
``"1"`` and ``"7"``. It is offered as an explicit, reported choice rather than a
hidden default.

No case folding, no Unicode normalisation and no punctuation stripping are
applied. Each of those creates false duplicates that the report cannot explain
away, which is worse than a missed duplicate the user can enable a flag for.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal, InvalidOperation

#: Token used for a missing value inside a canonical signature. Chosen so that
#: it cannot be produced by a CSV cell that survives stripping (it starts with a
#: NUL byte, which CSV text cannot contain here because NUL bytes are rejected
#: at load time).
MISSING_TOKEN = "\x00__missing__\x00"


def is_missing(value: object, missing_tokens: frozenset[str] = frozenset()) -> bool:
    """Return True when ``value`` counts as missing under the documented rules."""
    if value is None:
        return True
    if not isinstance(value, str):
        # Non-string cells only arise from programmatic frame construction.
        # They are never missing by string rules.
        return False
    return value == "" or value in missing_tokens


def parse_decimal(raw: str) -> Decimal | None:
    """Parse a finite decimal, or return None.

    Rejects NaN and Infinity, which :class:`decimal.Decimal` would otherwise
    accept, rejects digit-grouping underscores (``"1_000"`` is not the number
    1000 in a data file), and rejects anything with surrounding junk such as
    ``"1,5"``.
    """
    if raw == "" or "_" in raw:
        return None
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed


def canonical_numeric(parsed: Decimal) -> str:
    """Canonical string form of a finite decimal.

    Normalises ``1``, ``1.0``, ``1.00`` and ``1e0`` to ``"1"``, and normalises
    both positive and negative zero to ``"0"``.
    """
    if parsed == 0:
        return "0"
    return format(parsed.normalize(), "f")


class ValueCanonicalizer:
    """Applies one fixed canonicalization configuration to many values."""

    __slots__ = ("_missing_tokens", "_normalize_numeric", "_strip")

    def __init__(
        self,
        *,
        strip_whitespace: bool = True,
        normalize_numeric_strings: bool = False,
        missing_tokens: Iterable[str] = (),
    ) -> None:
        self._strip = strip_whitespace
        self._normalize_numeric = normalize_numeric_strings
        self._missing_tokens = frozenset(missing_tokens)

    @property
    def missing_tokens(self) -> frozenset[str]:
        return self._missing_tokens

    @property
    def strip_whitespace(self) -> bool:
        return self._strip

    @property
    def normalize_numeric_strings(self) -> bool:
        return self._normalize_numeric

    def missing(self, value: object) -> bool:
        return is_missing(value, self._missing_tokens)

    def token(self, value: object) -> str:
        """Comparison token for a single cell."""
        if self.missing(value):
            return MISSING_TOKEN
        assert isinstance(value, str)  # guaranteed by is_missing() for non-None
        text = value.strip() if self._strip else value
        if text == "":
            # Only reachable when stripping is enabled and the cell was
            # whitespace-only; that is missing under rule 2 of the docstring.
            return MISSING_TOKEN
        if self._normalize_numeric:
            parsed = parse_decimal(text)
            if parsed is not None:
                return canonical_numeric(parsed)
        return text

    def tokens(self, values: Sequence[object]) -> tuple[str, ...]:
        return tuple(self.token(v) for v in values)

    def values_equal(self, left: object, right: object) -> bool:
        """Typed-aware equality used by the target-copy rule.

        Two non-missing cells are equal when their canonical tokens match, or,
        failing that, when both parse as finite decimals of equal value. This is
        what lets a numeric target ``1.0`` match the feature value ``"1"`` while
        still refusing to treat ``"NA"`` as a missing value.
        """
        if self.missing(left) or self.missing(right):
            return False
        assert isinstance(left, str) and isinstance(right, str)
        left_text = left.strip() if self._strip else left
        right_text = right.strip() if self._strip else right
        if left_text == right_text:
            return True
        left_num = parse_decimal(left_text)
        if left_num is None:
            return False
        right_num = parse_decimal(right_text)
        return right_num is not None and left_num == right_num


__all__ = [
    "MISSING_TOKEN",
    "ValueCanonicalizer",
    "canonical_numeric",
    "is_missing",
    "parse_decimal",
]
