"""Application configuration loaded from environment variables.

All configuration comes from the environment (see .env.example).
No secrets or model identifiers are hardcoded in business logic.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development")
    app_name: str = Field(default="mnemos")
    app_debug: bool = Field(default=True)
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_log_level: str = Field(default="INFO")
    app_cors_origins: str = Field(default="http://localhost:5173")

    # Supabase (managed PostgreSQL platform). Empty in Phase 0 until the
    # user provisions a project; validated strictly in later phases.
    supabase_url: str = Field(default="")
    supabase_anon_key: str = Field(default="")
    supabase_service_role_key: str = Field(default="")
    supabase_db_url: str = Field(default="")

    # OpenRouter (model-access layer). Boundary only in Phase 0.
    openrouter_api_key: str = Field(default="")
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


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
