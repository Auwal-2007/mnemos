"""Unit tests for configuration validation."""

from app.core.config import Settings


def test_settings_defaults() -> None:
    """Settings load with safe defaults when no env file is present."""
    settings = Settings(_env_file=None)
    assert settings.app_name == "mnemos"
    assert settings.app_env == "development"
    assert settings.app_port == 8000
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.openrouter_max_retries == 3


def test_cors_origins_list() -> None:
    """CORS origins are parsed into a clean list."""
    settings = Settings(_env_file=None, app_cors_origins="http://a, http://b ,http://c")
    assert settings.cors_origins_list() == ["http://a", "http://b", "http://c"]


def test_secret_fields_default_empty() -> None:
    """Secret fields default to empty — no hardcoded credentials."""
    settings = Settings(_env_file=None)
    assert settings.supabase_service_role_key == ""
    assert settings.openrouter_api_key == ""


def test_integration_flags() -> None:
    """Configuration flags reflect presence of required values."""
    empty = Settings(_env_file=None)
    assert empty.is_supabase_configured is False
    assert empty.is_openrouter_configured is False

    configured = Settings(
        _env_file=None,
        supabase_url="https://abcdefghijklm.supabase.co",
        supabase_anon_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon",
        openrouter_api_key="sk-or-v1-test-key",
    )
    assert configured.is_supabase_configured is True
    assert configured.is_openrouter_configured is True


def test_auth_flag_requires_url_and_verifier() -> None:
    """Auth is only considered configured with a URL and a verification key."""
    url_only = Settings(_env_file=None, supabase_url="https://abcdefghijklm.supabase.co")
    assert url_only.is_auth_configured is False
    assert (
        Settings(
            _env_file=None,
            supabase_url="https://abcdefghijklm.supabase.co",
            supabase_jwt_secret="super-secret-jwt-token-with-at-least-32-characters",
        ).is_auth_configured
        is True
    )


def test_placeholders_are_not_treated_as_configuration() -> None:
    """Template values from .env.example must never report as configured."""
    settings = Settings(
        _env_file=None,
        supabase_url="https://your-project-ref.supabase.co",
        supabase_anon_key="your-publishable-anon-key-here",
        openrouter_api_key="your-openrouter-api-key-here",
    )
    assert settings.is_supabase_configured is False
    assert settings.is_auth_configured is False
    assert settings.is_openrouter_configured is False


def test_blank_and_whitespace_values_are_not_configured() -> None:
    """Whitespace-only credentials are treated as absent."""
    settings = Settings(_env_file=None, supabase_url="   ", openrouter_api_key="  ")
    assert settings.is_supabase_configured is False
    assert settings.is_openrouter_configured is False
