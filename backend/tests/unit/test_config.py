"""Unit tests for application configuration validation."""

from app.core.config import Settings


def test_settings_defaults() -> None:
    """Settings load with safe defaults when no env is set."""
    settings = Settings(_env_file=None)
    assert settings.app_name == "mnemos"
    assert settings.app_env == "development"
    assert settings.app_port == 8000
    assert settings.openrouter_max_retries == 3


def test_cors_origins_list() -> None:
    """CORS origins are parsed into a clean list."""
    settings = Settings(_env_file=None, app_cors_origins="http://a, http://b ,http://c")
    assert settings.cors_origins_list() == ["http://a", "http://b", "http://c"]


def test_no_hardcoded_secrets() -> None:
    """Secret fields default to empty (never hardcoded credentials)."""
    settings = Settings(_env_file=None)
    assert settings.supabase_service_role_key == ""
    assert settings.openrouter_api_key == ""
