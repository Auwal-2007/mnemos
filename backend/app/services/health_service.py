"""Health and readiness services.

Business logic stays out of route handlers; routes call services.
"""

from __future__ import annotations

from app.core.config import Settings
from app.schemas.common import HealthResponse, ReadinessCheck, ReadinessResponse

APP_VERSION = "0.1.0"


class HealthService:
    """Reports liveness and configuration readiness without leaking secrets."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def liveness(self) -> HealthResponse:
        """Return process liveness information."""
        return HealthResponse(
            status="ok",
            service=self._settings.app_name,
            version=APP_VERSION,
            environment=self._settings.app_env,
        )

    def readiness(self) -> ReadinessResponse:
        """Report which integrations are configured (presence only)."""
        checks = [
            ReadinessCheck(
                name="supabase", configured=self._settings.is_supabase_configured, required=False
            ),
            ReadinessCheck(
                name="supabase_auth", configured=self._settings.is_auth_configured, required=False
            ),
            ReadinessCheck(
                name="openrouter",
                configured=self._settings.is_openrouter_configured,
                required=False,
            ),
        ]
        # Phase 1: integrations are optional at boot, so status reflects
        # whether the core application is able to serve requests.
        return ReadinessResponse(status="ready", checks=checks)
