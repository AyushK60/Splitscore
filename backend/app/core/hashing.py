"""Deterministic hashing helpers.

Used for two distinct purposes, and the distinction matters:

* :func:`sha256_bytes` / :func:`sha256_text` produce the *input fingerprint*.
  This is a reproducibility identifier, **not** an anonymisation mechanism. The
  input file is still fully recoverable from the original data; the hash only
  lets two people confirm they audited identical bytes.
* :func:`signature_hash` produces the collision-checked bucket key used by
  duplicate grouping. It is never used on its own to *decide* equality.
"""

from __future__ import annotations

import hashlib


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def encode_signature(values: tuple[str, ...]) -> str:
    """Length-prefixed encoding of a value tuple.

    Length prefixing makes the encoding injective for tuples of strings, so two
    different tuples cannot encode to the same string even if they contain
    values that look like separators.
    """
    parts = [f"{len(v)}:{v}" for v in values]
    return "\x1f".join(parts)


def signature_hash(values: tuple[str, ...]) -> str:
    """SHA-256 of the injective encoding of ``values`` (12 hex chars)."""
    return sha256_text(encode_signature(values))[:12]
