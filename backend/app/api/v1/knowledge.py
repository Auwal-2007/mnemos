"""Knowledge read endpoints (Phase 2A).

Ingestion endpoints arrive in 2B; these cover listing, detail, versions,
chunks and provenance resolution.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.deps import IdentityDep, get_chunk_repository, get_source_repository
from app.repositories.knowledge_repositories import (
    SupabaseChunkRepository,
    SupabaseSourceRepository,
)
from app.schemas.knowledge import (
    ChunkListResponse,
    ChunkSummaryResponse,
    DocumentVersionResponse,
    ProvenanceResponse,
    SourceDetailResponse,
    SourceResponse,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

SourceRepoDep = Annotated[SupabaseSourceRepository, Depends(get_source_repository)]
ChunkRepoDep = Annotated[SupabaseChunkRepository, Depends(get_chunk_repository)]


def _service(sources: SourceRepoDep, chunks: ChunkRepoDep) -> KnowledgeService:
    return KnowledgeService(sources, chunks)


@router.get(
    "/workspaces/{workspace_id}/sources",
    summary="List sources in a workspace",
)
async def list_sources(
    workspace_id: Annotated[str, Path(description="Workspace id")],
    identity: IdentityDep,
    sources: SourceRepoDep,
    chunks: ChunkRepoDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SourceResponse]:
    """List sources visible to the caller. RLS scopes the result."""
    del identity  # presence is the authorization check; RLS scopes the rows
    rows = _service(sources, chunks).list_sources(workspace_id, limit=limit, offset=offset)
    return [SourceResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/sources/{source_id}", summary="Get a source with its version history")
async def get_source(
    source_id: str,
    identity: IdentityDep,
    sources: SourceRepoDep,
    chunks: ChunkRepoDep,
) -> SourceDetailResponse:
    service = _service(sources, chunks)
    source = service.get_source(source_id)
    versions = service.list_versions(source_id)
    current = next((version for version in versions if version.is_current), None)
    detail = SourceDetailResponse.model_validate(source, from_attributes=True)
    detail.versions = [
        DocumentVersionResponse.model_validate(version, from_attributes=True)
        for version in versions
    ]
    detail.current_version = (
        DocumentVersionResponse.model_validate(current, from_attributes=True) if current else None
    )
    return detail


@router.get("/sources/{source_id}/versions", summary="List a source's versions")
async def list_versions(
    source_id: str,
    identity: IdentityDep,
    sources: SourceRepoDep,
    chunks: ChunkRepoDep,
) -> list[DocumentVersionResponse]:
    del identity
    versions = _service(sources, chunks).list_versions(source_id)
    return [
        DocumentVersionResponse.model_validate(version, from_attributes=True)
        for version in versions
    ]


@router.get("/sources/{source_id}/chunks", summary="List a source's chunks")
async def list_chunks(
    source_id: str,
    identity: IdentityDep,
    sources: SourceRepoDep,
    chunks: ChunkRepoDep,
    version_id: Annotated[str | None, Query(description="Pin to one version")] = None,
) -> ChunkListResponse:
    del identity
    service = _service(sources, chunks)
    rows = service.list_chunks(source_id, version_id)
    items = [ChunkSummaryResponse.model_validate(row, from_attributes=True) for row in rows]
    return ChunkListResponse(items=items, total=len(items))


@router.get("/chunks/{chunk_id}/provenance", summary="Resolve a chunk's provenance")
async def resolve_provenance(
    chunk_id: str,
    identity: IdentityDep,
    sources: SourceRepoDep,
    chunks: ChunkRepoDep,
) -> ProvenanceResponse:
    del identity
    payload = _service(sources, chunks).resolve_provenance(chunk_id)
    return ProvenanceResponse.model_validate(payload, from_attributes=True)


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a source and all derived data",
)
async def delete_source(
    source_id: str,
    identity: IdentityDep,
    sources: SourceRepoDep,
    chunks: ChunkRepoDep,
) -> Response:
    _service(sources, chunks).delete_source(source_id, identity.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
