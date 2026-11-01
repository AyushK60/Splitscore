"""One structured error envelope for every failure mode.

Shape: ``{"error": {"code": ..., "message": ..., "details": {...}}}``.

The frontend renders ``message`` and can branch on ``code`` without parsing prose.
Validation errors from FastAPI/Pydantic are rewritten into the same envelope and
include the offending field paths, so a bad request body produces a useful message
rather than a 500.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import SplitScopeError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

GENERIC_CODE_BY_STATUS = {
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    500: "internal_error",
}


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(SplitScopeError)
    async def _split_scope_error(_request: Request, exc: SplitScopeError) -> JSONResponse:
        logger.info("Handled %s: %s", exc.code, exc.message)
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        problems = [
            {
                "location": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", "invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "validation_error",
                "The request body or query parameters are not valid.",
                {"problems": problems[:20], "problem_count": len(problems)},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = GENERIC_CODE_BY_STATUS.get(exc.status_code, "http_error")
        detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, detail))

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_envelope(
                "internal_error",
                "An unexpected error occurred while handling the request.",
                {"exception_type": type(exc).__name__},
            ),
        )


__all__ = ["register_error_handlers"]
