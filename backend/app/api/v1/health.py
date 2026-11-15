"""Health and readiness endpoints (FR-015)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.common import HealthResponse, ReadinessResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["health"])


def _service(settings: Settings = Depends(get_settings)) -> HealthService:
    return HealthService(settings)


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(service: HealthService = Depends(_service)) -> HealthResponse:
    """Return service liveness status."""
    return service.liveness()


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def ready(service: HealthService = Depends(_service)) -> ReadinessResponse:
    """Report integration configuration readiness (presence, never values)."""
    return service.readiness()
