"""Application configuration loaded from environment variables.

All configuration comes from the environment (see .env.example).
No secrets or model identifiers are hardcoded in business logic.

Phase 1A adds environment validation and Supabase/OpenRouter readiness
flags. Credential values are optional at startup so that the application
can boot for local development before a Supabase project exists; features
that require credentials fail explicitly at use time, never silently.
"""

from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
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

    # --- Embeddings (separate provider concern, see infrastructure/embeddings) ---
    # Deliberately NOT derived from the chat settings: an embedding request must
    # never be sent to a chat-completions endpoint, and a deployment may use a
    # different provider for vectors than for generation.
    embedding_base_url: str = Field(default="https://openrouter.ai/api/v1/embeddings")
    embedding_api_key: str = Field(default="")
    embedding_model: str = Field(default="")
    embedding_dimension: int = Field(default=1536)
    embedding_batch_size: int = Field(default=32)
    embedding_timeout_seconds: float = Field(default=30.0)
    embedding_max_retries: int = Field(default=3)

    # --- Chunking (recorded on every chunk) ---------------------------------
    chunk_target_chars: int = Field(default=900)
    chunk_overlap_chars: int = Field(default=150)

    @model_validator(mode="after")
    def _check_chunking(self) -> Self:
        """Reject chunking settings that could hang or misbehave.

        A window that does not advance loops forever, so this fails at startup
        rather than during a request.
        """
        if self.chunk_target_chars < 100:
            raise ValueError("CHUNK_TARGET_CHARS must be at least 100")
        if not 0 <= self.chunk_overlap_chars < self.chunk_target_chars:
            raise ValueError("CHUNK_OVERLAP_CHARS must be >= 0 and smaller than CHUNK_TARGET_CHARS")
        return self

    def model_for_role(self, role: str) -> str:
        """Resolve the configured model id for a role.

        Roles are the named capabilities the system has, not the names of any
        particular model. A role with no specific setting falls back to the
        default model; if neither is set the result is empty and the caller must
        refuse rather than invent one (NFR-008).
        """
        role_models = {
            "default": self.openrouter_default_model,
            "retrieval": self.openrouter_retrieval_model,
            "orchestrator": self.openrouter_orchestrator_model,
            "memory": self.openrouter_memory_model,
            "verification": self.openrouter_verification_model,
        }
        specific = role_models.get(role, "").strip()
        if specific:
            return specific
        return self.openrouter_default_model.strip()

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
    def is_embedding_configured(self) -> bool:
        """True when a real embedding provider can be used."""
        return (
            _is_real(self.embedding_api_key)
            and bool(self.embedding_model.strip())
            and self.embedding_dimension > 0
        )

    @property
    def _is_supabase_url(self) -> bool:
        """A real project URL is a non-placeholder https URL on supabase.co."""
        value = self.supabase_url.strip().lower()
        return _is_real(value) and value.startswith("https://") and "supabase.co" in value


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
