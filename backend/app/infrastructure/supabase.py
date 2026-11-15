"""Supabase client adapters.

Two clients with deliberately different privilege levels:

* **anon client** (`get_public_client`) — uses the publishable anon key.
  Used for nothing privileged; safe to construct anywhere server-side.
* **service client** (`get_service_client`) — uses the service-role key and
  therefore bypasses RLS. It must only be used by trusted server code.

Neither client is ever exposed through an API response or imported into
frontend code. Credentials are never logged.

Additionally, a per-request **user client** is created from the caller's
access token (`user_client_from_token`) so that database reads and writes
run under RLS as that user. This is the preferred path for user-scoped
operations: the database enforces authorization, not just our code.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from supabase import Client, create_client

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError

logger = logging.getLogger("mnemos.supabase")


class SupabaseNotConfiguredError(ConfigurationError):
    """Raised when a Supabase-backed feature is used without credentials."""

    default_message = (
        "Supabase is not configured on this server. Set SUPABASE_URL and the "
        "appropriate key to enable data features."
    )


def _require(settings: Settings) -> None:
    if not settings.is_supabase_configured:
        raise SupabaseNotConfiguredError()


@lru_cache
def get_public_client() -> Client:
    """Return a cached client authenticated with the anon key."""
    settings = get_settings()
    _require(settings)
    logger.info("Creating Supabase public (anon) client")
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@lru_cache
def get_service_client() -> Client:
    """Return a cached service-role client. Server-side use only.

    Bypasses RLS: every call site must enforce authorization itself.
    """
    settings = get_settings()
    if not settings.supabase_service_role_key:
        raise SupabaseNotConfiguredError(
            message="SUPABASE_SERVICE_ROLE_KEY is required for privileged operations."
        )
    _require(settings)
    logger.info("Creating Supabase service-role client (privileged)")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def user_client_from_token(access_token: str) -> Client:
    """Build a short-lived client that acts as the bearer of `access_token`.

    Database policies evaluate as that user, so authorization is enforced
    by RLS in addition to application checks.
    """
    settings = get_settings()
    _require(settings)
    if not access_token:
        raise SupabaseNotConfiguredError(message="An access token is required.")
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


def reset_clients() -> None:
    """Clear cached clients. Used by tests and after configuration changes."""
    get_public_client.cache_clear()
    get_service_client.cache_clear()
