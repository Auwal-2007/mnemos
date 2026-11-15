"""Unit tests for the health service."""

from app.core.config import Settings
from app.services.health_service import HealthService


def test_readiness_marks_unconfigured_integrations() -> None:
    """Integrations without credentials are reported as unconfigured."""
    service = HealthService(Settings(_env_file=None))
    result = service.readiness()
    assert result.status == "ready"
    assert all(check.required is False for check in result.checks)
    assert all(check.configured is False for check in result.checks)


def test_readiness_reflects_configuration() -> None:
    """Configured integrations are reported as configured."""
    settings = Settings(
        _env_file=None,
        supabase_url="https://abcdefghijklm.supabase.co",
        supabase_anon_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon",
        openrouter_api_key="sk-or-v1-test-key",
    )
    checks = {check.name: check.configured for check in HealthService(settings).readiness().checks}
    assert checks["supabase"] is True
    assert checks["openrouter"] is True


def test_liveness_reports_environment() -> None:
    """Liveness includes the environment name for operators."""
    settings = Settings(_env_file=None, app_env="test")
    assert HealthService(settings).liveness().environment == "test"
