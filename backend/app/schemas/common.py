"""Shared API response contracts.

Conventions (documented in ARCHITECTURE.md):
- Success responses return the resource payload directly (HTTP 200/201).
- List responses use {"items": [...], "total": int}.
- Errors always use the canonical envelope in app.core.errors.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    """Health-check response (FR-015). Contains no infrastructure secrets."""

    status: str = Field(description="Service status: ok | degraded")
    service: str = Field(description="Service name")
    version: str = Field(description="Application version")
    environment: str = Field(description="Deployment environment")


class ReadinessCheck(BaseModel):
    """Individual dependency readiness result."""

    name: str
    configured: bool
    required: bool


class ReadinessResponse(BaseModel):
    """Readiness response: reports configuration presence only, never values."""

    status: str = Field(description="ready | not_ready")
    checks: list[ReadinessCheck]


class ListResponse(BaseModel, Generic[T]):
    """Standard paginated/collection envelope."""

    items: list[T]
    total: int = 0
