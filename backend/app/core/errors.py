"""Typed domain errors and the single API error envelope.

Every error response has the same shape:

    {"error": {"code": str, "message": str, "request_id": str, "details": ...}}

Error responses never leak stack traces, SQL, or internal paths.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("mnemos.errors")


class MnemosError(Exception):
    """Base class for domain errors."""

    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, details: Any = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class NotFoundError(MnemosError):
    """Raised when a requested resource does not exist."""

    status_code = 404
    code = "not_found"
    default_message = "The requested resource was not found."


class ValidationError(MnemosError):
    """Raised when input fails domain validation."""

    status_code = 422
    code = "validation_error"
    default_message = "The submitted data is invalid."


class UnauthorizedError(MnemosError):
    """Raised when authentication is missing or invalid."""

    status_code = 401
    code = "unauthorized"
    default_message = "Authentication is required."


class ForbiddenError(MnemosError):
    """Raised when the authenticated user lacks permission."""

    status_code = 403
    code = "forbidden"
    default_message = "You do not have permission to perform this action."


class ConfigurationError(MnemosError):
    """Raised when a feature requires configuration that is absent."""

    status_code = 503
    code = "service_not_configured"
    default_message = "This feature is not configured on the server."


class InsufficientEvidenceError(MnemosError):
    """Raised when evidence is insufficient to answer (FR-010, future)."""

    status_code = 422
    code = "insufficient_evidence"
    default_message = "There is not enough evidence to answer this question."


def error_payload(
    code: str,
    message: str,
    request_id: str,
    details: Any = None,
) -> dict[str, Any]:
    """Build the canonical error envelope."""
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details is not None:
        error["details"] = details
    return {"error": error}


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


async def mnemos_error_handler(request: Request, exc: MnemosError) -> JSONResponse:
    """Convert a domain error to a sanitized JSON response."""
    if exc.status_code >= 500:
        logger.exception("Unhandled domain error: %s", exc.code)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.code, exc.message, _request_id(request), exc.details),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Convert request validation failures into the canonical envelope."""
    details = [
        {"path": ".".join(str(part) for part in err.get("loc", ())), "message": err.get("msg", "")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "validation_error",
            "The request payload failed validation.",
            _request_id(request),
            details,
        ),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Convert framework HTTP errors into the canonical envelope."""
    codes = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found"}
    code = codes.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) and exc.detail else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(code, message, _request_id(request)),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors; never leak internals to clients."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_payload(
            "internal_error",
            "An unexpected error occurred. Please try again.",
            _request_id(request),
        ),
    )
