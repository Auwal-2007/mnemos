"""Shared FastAPI dependencies.

Authentication dependency chain:

    Authorization header → verify_token() → Identity
    Identity + raw token  → user-scoped Supabase client → repositories
    Repositories          → services → route handlers

A missing/invalid token yields 401 via the canonical error envelope.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from supabase import Client

from app.core.config import Settings, get_settings
from app.core.errors import UnauthorizedError
from app.domain.identity import Identity
from app.infrastructure.auth import verify_token
from app.infrastructure.supabase import user_client_from_token
from app.repositories.knowledge_repositories import (
    SupabaseChunkRepository,
    SupabaseSourceRepository,
)
from app.repositories.supabase_repositories import (
    SupabasePreferencesRepository,
    SupabaseProfileRepository,
    SupabaseWorkspaceRepository,
)

logger = logging.getLogger("mnemos.deps")


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Verified caller identity plus a client bound to their token."""

    identity: Identity
    client: Client


def bearer_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Extract a bearer token, rejecting anything malformed."""
    if not authorization:
        raise UnauthorizedError(
            message="Authentication is required. Provide an Authorization: Bearer <token> header."
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError(message="The Authorization header must use the Bearer scheme.")
    return token.strip()


def get_auth_context(
    token: Annotated[str, Depends(bearer_token)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    """Verify the token and build a client scoped to the caller."""
    identity = verify_token(token, settings)
    client = user_client_from_token(token)
    return AuthContext(identity=identity, client=client)


def current_identity(context: Annotated[AuthContext, Depends(get_auth_context)]) -> Identity:
    """The verified caller identity."""
    return context.identity


def current_user_context(context: Annotated[AuthContext, Depends(get_auth_context)]) -> AuthContext:
    """The verified caller identity and their database client."""
    return context


# --- Repository providers -------------------------------------------------


def get_workspace_repository(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> SupabaseWorkspaceRepository:
    return SupabaseWorkspaceRepository(context.client)


def get_profile_repository(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> SupabaseProfileRepository:
    return SupabaseProfileRepository(context.client)


def get_preferences_repository(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> SupabasePreferencesRepository:
    return SupabasePreferencesRepository(context.client)


def get_source_repository(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> SupabaseSourceRepository:
    return SupabaseSourceRepository(context.client)


def get_chunk_repository(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> SupabaseChunkRepository:
    return SupabaseChunkRepository(context.client)


# Typed aliases keep route signatures readable.
IdentityDep = Annotated[Identity, Depends(current_identity)]
AuthContextDep = Annotated[AuthContext, Depends(current_user_context)]
WorkspaceRepoDep = Annotated[SupabaseWorkspaceRepository, Depends(get_workspace_repository)]
ProfileRepoDep = Annotated[SupabaseProfileRepository, Depends(get_profile_repository)]
PreferencesRepoDep = Annotated[SupabasePreferencesRepository, Depends(get_preferences_repository)]
SourceRepoDep = Annotated[SupabaseSourceRepository, Depends(get_source_repository)]
ChunkRepoDep = Annotated[SupabaseChunkRepository, Depends(get_chunk_repository)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
