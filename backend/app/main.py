"""MNEMOS FastAPI application.

Phase 1A: layered application foundation — versioned API routing,
configuration, request correlation, consistent error envelopes and
health/readiness endpoints. No product features yet.

Run: uvicorn app.main:app --reload
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.errors import (
    MnemosError,
    http_exception_handler,
    mnemos_error_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.services.health_service import APP_VERSION

settings = get_settings()
logger = configure_logging(settings.app_log_level)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle: log startup/shutdown, release resources."""
    logger.info(
        "Starting %s v%s env=%s supabase_configured=%s openrouter_configured=%s",
        settings.app_name,
        APP_VERSION,
        settings.app_env,
        settings.is_supabase_configured,
        settings.is_openrouter_configured,
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Application factory (testable, explicit configuration)."""
    application = FastAPI(
        title="MNEMOS API",
        version=APP_VERSION,
        description=(
            "Provenance-aware multi-agent personal knowledge system.\n\n"
            "Phase 1: application foundation. AI capabilities are not yet implemented."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    application.add_exception_handler(MnemosError, mnemos_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    application.add_exception_handler(Exception, unhandled_exception_handler)

    application.include_router(api_router, prefix=settings.api_v1_prefix)

    # Unversioned aliases for infrastructure probes.
    application.include_router(api_router, include_in_schema=False)

    return application


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    logging.getLogger("mnemos").info("Starting development server")
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
