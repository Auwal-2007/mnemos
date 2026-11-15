"""Indexing endpoints (Phase 2C).

Chunking and embedding are separate from ingestion so a deployment without an
embedding provider can still accept and extract documents, and so a failed
embedding can be retried without re-uploading anything.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import AuthContextDep, ChunkRepoDep, SourceRepoDep
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.infrastructure.embeddings import embedding_provider_from_settings
from app.repositories.knowledge_repositories import (
    SupabaseEmbeddingRepository,
    SupabaseExtractionReader,
)
from app.schemas.knowledge import IndexSourceResponse
from app.services.indexing import IndexingService

logger = logging.getLogger("mnemos.api.indexing")

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post(
    "/sources/{source_id}/index",
    status_code=status.HTTP_200_OK,
    summary="Chunk and embed a source's current version",
)
async def index_source(
    source_id: str,
    context: AuthContextDep,
    sources: SourceRepoDep,
    chunks: ChunkRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> IndexSourceResponse:
    """Run chunking and embedding for the current version.

    Idempotent: chunks already produced by the same configuration are reused,
    and already-embedded chunks are skipped. Re-running after a failure resumes
    rather than duplicating.
    """
    source = sources.get(source_id)
    if source is None:
        raise NotFoundError(message="Source not found.")

    version = sources.current_version(source_id)
    if version is None:
        raise NotFoundError(message="This source has no current version to index.")

    service = IndexingService(
        sources=sources,
        chunks=chunks,
        embeddings=SupabaseEmbeddingRepository(context.client),
        extractions=SupabaseExtractionReader(context.client),
        provider=(
            embedding_provider_from_settings(settings) if settings.is_embedding_configured else None
        ),
    )
    outcome = await service.index_version(source=source, version=version)
    refreshed = sources.get(source_id) or source
    return IndexSourceResponse(
        source_id=refreshed.id,
        processing_status=refreshed.processing_status.value,
        chunk_count=outcome.chunking.chunk_count if outcome.chunking else 0,
        chunks_created=bool(outcome.chunking and outcome.chunking.created),
        embeddings_created=outcome.embedding.embedded if outcome.embedding else 0,
        embedding_model=outcome.embedding.model_id if outcome.embedding else None,
        embedding_dimension=outcome.embedding.dimension if outcome.embedding else None,
        error_code=outcome.error_code,
        error_message=outcome.error_message,
    )


@router.post(
    "/sources/{source_id}/reindex",
    status_code=status.HTTP_200_OK,
    summary="Discard a source's chunks and embeddings and rebuild them",
)
async def reindex_source(
    source_id: str,
    context: AuthContextDep,
    sources: SourceRepoDep,
    chunks: ChunkRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> IndexSourceResponse:
    """Delete then rebuild. Explicit because it destroys derived data.

    The original file and the extracted text are untouched: only derived chunks
    and vectors are replaced.
    """
    source = sources.get(source_id)
    if source is None:
        raise NotFoundError(message="Source not found.")
    version = sources.current_version(source_id)
    if version is None:
        raise NotFoundError(message="This source has no current version to index.")

    service = IndexingService(
        sources=sources,
        chunks=chunks,
        embeddings=SupabaseEmbeddingRepository(context.client),
        extractions=SupabaseExtractionReader(context.client),
        provider=(
            embedding_provider_from_settings(settings) if settings.is_embedding_configured else None
        ),
    )
    removed = service.reindex_version(source=source, version=version)
    logger.info("Re-index requested (chunks removed=%d)", removed)

    outcome = await service.index_version(source=source, version=version)
    refreshed = sources.get(source_id) or source
    return IndexSourceResponse(
        source_id=refreshed.id,
        processing_status=refreshed.processing_status.value,
        chunk_count=outcome.chunking.chunk_count if outcome.chunking else 0,
        chunks_created=bool(outcome.chunking and outcome.chunking.created),
        embeddings_created=outcome.embedding.embedded if outcome.embedding else 0,
        embedding_model=outcome.embedding.model_id if outcome.embedding else None,
        embedding_dimension=outcome.embedding.dimension if outcome.embedding else None,
        error_code=outcome.error_code,
        error_message=outcome.error_message,
    )
