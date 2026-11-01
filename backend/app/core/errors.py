"""Structured application errors.

Every error that can reach the HTTP layer carries a machine-readable ``code``,
a human-readable ``message`` and an optional ``details`` mapping. The FastAPI
layer converts these into a single documented JSON error envelope, so the
frontend never has to parse prose to understand what happened.
"""

from __future__ import annotations

from typing import Any


class SplitScopeError(Exception):
    """Base class for expected, user-actionable failures."""

    code = "internal_error"
    http_status = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class ValidationFailure(SplitScopeError):
    """The request body, roles or configuration is not usable."""

    code = "validation_error"
    http_status = 422


class UnsupportedInputError(SplitScopeError):
    """The input is understood but not supported by this version."""

    code = "unsupported_input"
    http_status = 415


class LimitExceededError(SplitScopeError):
    """An explicit, documented limit was exceeded. Never silently truncated."""

    code = "limit_exceeded"
    http_status = 413


class MalformedCsvError(SplitScopeError):
    code = "malformed_csv"
    http_status = 400


class NotFoundError(SplitScopeError):
    code = "not_found"
    http_status = 404


class ExpiredError(SplitScopeError):
    """The referenced dataset or run expired or was evicted from the store."""

    code = "expired_or_evicted"
    http_status = 410


class InfeasibleOperationError(SplitScopeError):
    """A requested split or check cannot be performed for this dataset."""

    code = "infeasible_operation"
    http_status = 409
