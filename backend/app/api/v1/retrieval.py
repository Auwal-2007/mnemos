"""Retrieval endpoints (Phase 3A).

`POST /knowledge/workspaces/{workspace_id}/search` is the read-only retrieval
API. It returns evidence, never generated text — that is Phase 3B's endpoint.

Why POST for a read: the query is arbitrary natural language of up to 2000
characters, which does not belong in a URL (logs, length limits, encoding).
The operation is still side-effect free and idempotent.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.api.deps import AuthContextDep, WorkspaceRepoDep
from app.core.config import Settings, get_settings
from app.domain.retrieval import RetrievalResult, RetrievedPassage
from app.infrastructure.embeddings import EmbeddingProvider, embedding_provider_from_settings
from app.repositories.knowledge_repositories import SupabaseRetrievalRepository
from app.schemas.retrieval import (
    RetrievalScoreResponse,
    RetrievedPassageResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.retrieval import RetrievalOptions, RetrievalService

logger = logging.getLogger("mnemos.api.retrieval")

router = APIRouter(prefix="/knowledge", tags=["retrieval"])


def _provider(settings: Settings) -> EmbeddingProvider | None:
    """The configured embedding provider, or None when none is configured.

    Retrieval deliberately tolerates the absence of a provider: lexical search
    still works, and the response says semantic search was skipped.
    """
    if not settings.is_embedding_configured:
        return None
    return embedding_provider_from_settings(settings)


@router.post(
    "/workspaces/{workspace_id}/search",
    summary="Search a workspace for passages relevant to a query",
)
async def search_workspace(
    workspace_id: Annotated[str, Path(description="Workspace id")],
    body: SearchRequest,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchResponse:
    """Hybrid (lexical + semantic) retrieval, fused with reciprocal rank fusion.

    Returns an empty `passages` list when nothing matches. That is a successful
    search, not an error: whether an answer can be given is decided by the
    generation stage, which must abstain when evidence is insufficient.
    """
    service = RetrievalService(
        workspaces=workspaces,
        search=SupabaseRetrievalRepository(context.client),
        provider=_provider(settings),
    )
    result = await service.search(
        workspace_id=workspace_id,
        user_id=context.identity.user_id,
        query=body.query,
        options=RetrievalOptions(
            limit=body.limit,
            candidate_count=body.candidate_count,
            include_superseded=body.include_superseded,
        ),
    )
    return _response(result)


def _response(result: RetrievalResult) -> SearchResponse:
    return SearchResponse(
        query=result.query,
        passages=[_passage(passage) for passage in result.passages],
        total=result.total,
        limit=result.limit,
        candidate_count=result.candidate_count,
        include_superseded=result.include_superseded,
        hybrid=result.hybrid,
        degraded_reason=result.degraded_reason,
        metadata=result.metadata,
    )


def _passage(passage: RetrievedPassage) -> RetrievedPassageResponse:
    return RetrievedPassageResponse(
        chunk_id=passage.chunk_id,
        provenance_id=passage.provenance_id,
        source_id=passage.source_id,
        document_version_id=passage.document_version_id,
        source_title=passage.source_title,
        source_kind=passage.source_kind.value,
        version_number=passage.version_number,
        version_is_current=passage.version_is_current,
        information_status=passage.information_status.value,
        chunk_index=passage.chunk_index,
        content=passage.content,
        char_count=passage.char_count,
        source_location=passage.source_location,
        page=passage.page,
        start_offset=passage.start_offset,
        end_offset=passage.end_offset,
        matched_by=passage.matched_by.value,
        scores=RetrievalScoreResponse(
            lexical_rank=passage.lexical_rank,
            semantic_rank=passage.semantic_rank,
            lexical_score=passage.lexical_score,
            semantic_similarity=passage.semantic_similarity,
            fused_score=passage.fused_score,
        ),
    )
