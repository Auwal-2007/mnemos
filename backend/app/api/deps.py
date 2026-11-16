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
from app.infrastructure.embeddings import embedding_provider_from_settings
from app.infrastructure.storage import SupabaseStorage
from app.infrastructure.supabase import (
    SupabaseNotConfiguredError,
    get_service_client,
    user_client_from_token,
)
from app.repositories.knowledge_repositories import (
    SupabaseChunkRepository,
    SupabaseEmbeddingRepository,
    SupabaseExtractionReader,
    SupabaseSourceRepository,
)
from app.repositories.supabase_repositories import (
    SupabasePreferencesRepository,
    SupabaseProfileRepository,
    SupabaseWorkspaceRepository,
)
from app.services.chunking import ChunkingConfig
from app.services.indexing import IndexingService
from app.services.ingestion.pipeline import IngestionPipeline
from app.services.workspace_service import WorkspaceService

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


def derived_write_client(context: AuthContext) -> Client:
    """The client used for trusted derived writes.

    Extracted text, chunks, provenance records and embeddings are *derived*
    data. Users hold only SELECT on those tables by design, so a user-scoped
    client cannot write them: doing so raises "permission denied for table
    chunks" against a real database (found while building Phase 3B).

    The service-role client is used for exactly those writes. It bypasses RLS,
    which is why every call site that receives it must first have authorized
    the caller — here, `WorkspaceService.require_contributor` inside the
    pipeline. When no service-role key is configured the user client is
    returned instead, so local development without privileged credentials
    fails with a clear permission error rather than silently doing nothing.
    """
    try:
        return get_service_client()
    except SupabaseNotConfiguredError:
        logger.warning(
            "SUPABASE_SERVICE_ROLE_KEY is not set: derived writes will run as the "
            "caller and be refused by RLS. Set it to enable ingestion."
        )
        return context.client


def get_ingestion_pipeline(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IngestionPipeline:
    """Build the ingestion pipeline for the caller.

    Authorization is unchanged and still RLS-enforced on the user client for
    every user-owned row (sources, versions, membership). Only derived-row
    writes use the privileged client, because those tables are intentionally
    not user-writable.
    """
    sources = SupabaseSourceRepository(context.client)
    derived = derived_write_client(context)
    chunks = SupabaseChunkRepository(derived)

    # Indexing is attached only when an embedding provider is configured, so
    # ingestion still works (stopping at `extracted`) in a deployment that has
    # no vector provider yet. The UI then shows the truth rather than an error.
    indexer: IndexingService | None = None
    if settings.is_embedding_configured:
        indexer = IndexingService(
            sources=sources,
            chunks=chunks,
            embeddings=SupabaseEmbeddingRepository(derived),
            extractions=SupabaseExtractionReader(context.client),
            provider=embedding_provider_from_settings(settings),
            config=ChunkingConfig(
                target_chars=settings.chunk_target_chars,
                overlap_chars=settings.chunk_overlap_chars,
            ),
        )

    return IngestionPipeline(
        sources=sources,
        chunks=chunks,
        storage=SupabaseStorage(context.client, settings),
        workspaces=WorkspaceService(SupabaseWorkspaceRepository(context.client)),
        indexer=indexer,
    )


# Typed aliases keep route signatures readable.
IdentityDep = Annotated[Identity, Depends(current_identity)]
AuthContextDep = Annotated[AuthContext, Depends(current_user_context)]
WorkspaceRepoDep = Annotated[SupabaseWorkspaceRepository, Depends(get_workspace_repository)]
ProfileRepoDep = Annotated[SupabaseProfileRepository, Depends(get_profile_repository)]
PreferencesRepoDep = Annotated[SupabasePreferencesRepository, Depends(get_preferences_repository)]
SourceRepoDep = Annotated[SupabaseSourceRepository, Depends(get_source_repository)]
ChunkRepoDep = Annotated[SupabaseChunkRepository, Depends(get_chunk_repository)]
IngestionPipelineDep = Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
