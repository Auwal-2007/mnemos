"""MNEMOS FastAPI application entry point.

Phase 0: health-check skeleton only (FR-015). No product features.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import MnemosError, mnemos_error_handler
from app.core.logging import configure_logging

settings = get_settings()
logger = configure_logging(settings.app_log_level)

app = FastAPI(
    title="MNEMOS API",
    version="0.0.1",
    description="Provenance-aware multi-agent personal knowledge system (Phase 0 skeleton).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.add_exception_handler(MnemosError, mnemos_error_handler)  # type: ignore[arg-type]


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Return service health status (FR-015)."""
    logger.info("Health check requested")
    return {"status": "ok", "service": settings.app_name, "version": "0.0.1"}


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    """Return API root information."""
    return {"service": settings.app_name, "status": "phase-0-skeleton"}
