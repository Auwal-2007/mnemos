"""Application configuration loaded from environment variables.

All configuration comes from the environment (see .env.example).
No secrets or model identifiers are hardcoded in business logic.

Phase 1A adds environment validation and Supabase/OpenRouter readiness
flags. Credential values are optional at startup so that the application
can boot for local development before a Supabase project exists; features
that require credentials fail explicitly at use time, never silently.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_MARKERS = ("your-", "your_", "changeme", "placeholder", "example.com", "<", "TODO")


def _is_real(value: str) -> bool:
    """False for empty values and obvious template placeholders."""
    cleaned = value.strip()
    if not cleaned:
        return False
    lowered = cleaned.lower()
    return not any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    """Validated application settings."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -------------------------------------------------
    app_env: str = Field(default="development")
    app_name: str = Field(default="mnemos")
    app_debug: bool = Field(default=True)
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_log_level: str = Field(default="INFO")
    app_cors_origins: str = Field(default="http://localhost:5173")
    api_v1_prefix: str = Field(default="/api/v1")

    # --- Supabase (managed PostgreSQL platform) -----------------------
    supabase_url: str = Field(default="")
    supabase_anon_key: str = Field(default="")
    supabase_service_role_key: str = Field(default="")
    supabase_db_url: str = Field(default="")
    supabase_jwt_secret: str = Field(default="")
    supabase_storage_bucket_sources: str = Field(default="sources")

    # --- OpenRouter (model-access layer) ------------------------------
    openrouter_api_key: str = Field(default="")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    openrouter_default_model: str = Field(default="")
    openrouter_orchestrator_model: str = Field(default="")
    openrouter_retrieval_model: str = Field(default="")
    openrouter_memory_model: str = Field(default="")
    openrouter_verification_model: str = Field(default="")
    openrouter_timeout_seconds: float = Field(default=30.0)
    openrouter_max_retries: int = Field(default=3)

    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a list."""
        return [origin.strip() for origin in self.app_cors_origins.split(",") if origin.strip()]

    @property
    def is_supabase_configured(self) -> bool:
        """True when real Supabase credentials are present.

        Template placeholders (e.g. `your-project-ref`) must never be
        reported as configured: readiness output has to be truthful.
        """
        return self._is_supabase_url and _is_real(self.supabase_anon_key)

    @property
    def is_auth_configured(self) -> bool:
        """True when token verification can be performed server-side."""
        if not self._is_supabase_url:
            return False
        return _is_real(self.supabase_jwt_secret) or _is_real(self.supabase_anon_key)

    @property
    def is_openrouter_configured(self) -> bool:
        """True when OpenRouter credentials are present."""
        return _is_real(self.openrouter_api_key)

    @property
    def _is_supabase_url(self) -> bool:
        """A real project URL is a non-placeholder https URL on supabase.co."""
        value = self.supabase_url.strip().lower()
        return _is_real(value) and value.startswith("https://") and "supabase.co" in value


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
