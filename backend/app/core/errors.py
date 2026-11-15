"""Typed domain errors mapped to HTTP responses at the API boundary.

Error responses never leak stack traces, SQL, or internal paths.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class MnemosError(Exception):
    """Base class for domain errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str = "An unexpected error occurred.") -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(MnemosError):
    """Raised when a requested resource does not exist."""

    status_code = 404
    code = "not_found"


class ValidationError(MnemosError):
    """Raised when input fails validation."""

    status_code = 422
    code = "validation_error"


class UnauthorizedError(MnemosError):
    """Raised when authentication is missing or invalid."""

    status_code = 401
    code = "unauthorized"


class ForbiddenError(MnemosError):
    """Raised when the user lacks permission for an operation."""

    status_code = 403
    code = "forbidden"


class InsufficientEvidenceError(MnemosError):
    """Raised when evidence is insufficient to answer (FR-010)."""

    status_code = 422
    code = "insufficient_evidence"


async def mnemos_error_handler(request: Request, exc: MnemosError) -> JSONResponse:
    """Convert a domain error to a sanitized JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "data": None,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request.headers.get("x-request-id", ""),
            },
        },
    )
