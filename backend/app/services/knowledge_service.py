"""Knowledge service (Phase 2A): source listing, detail, versions and deletion.

Ingestion itself (2B) will add creation. This service owns the authorization
rules that sit above RLS so that the API cannot be driven into an operation
the caller is not entitled to, and so that error messages stay honest.
"""

from __future__ import annotations

import logging

from app.core.errors import ForbiddenError, NotFoundError
from app.domain.knowledge import DocumentVersion, Source
from app.repositories.base import ChunkRepository, SourceRepository

logger = logging.getLogger("mnemos.knowledge")


class KnowledgeService:
    """Read-side knowledge operations."""

    def __init__(self, sources: SourceRepository, chunks: ChunkRepository) -> None:
        self._sources = sources
        self._chunks = chunks

    def list_sources(self, workspace_id: str, *, limit: int = 50, offset: int = 0) -> list[Source]:
        """Sources in a workspace the caller can see (RLS scopes the result)."""
        return self._sources.list_for_workspace(workspace_id, limit=limit, offset=offset)

    def get_source(self, source_id: str) -> Source:
        """Fetch one source or raise a sanitized not-found error."""
        source = self._sources.get(source_id)
        if source is None:
            # RLS makes another user's source indistinguishable from a missing
            # one, which is the intended behaviour: no existence disclosure.
            raise NotFoundError(message="Source not found.")
        return source

    def list_versions(self, source_id: str) -> list[DocumentVersion]:
        """All versions of a source, newest first."""
        self.get_source(source_id)
        return self._sources.list_versions(source_id)

    def get_version(self, version_id: str) -> DocumentVersion:
        version = self._sources.get_version(version_id)
        if version is None:
            raise NotFoundError(message="Document version not found.")
        return version

    def resolve_provenance(self, chunk_id: str) -> dict[str, object]:
        """Resolve a chunk to its provenance contract.

        Raises NotFound when the chunk is not visible to the caller, so a
        citation that cannot be resolved is never rendered as supported.
        """
        reference = self._chunks.resolve_for_chunk(chunk_id)
        if reference is None:
            raise NotFoundError(message="No provenance record exists for that chunk.")
        return {
            "provenance_id": reference.provenance_id,
            "chunk_id": reference.chunk_id,
            "source_id": reference.source_id,
            "document_version_id": reference.document_version_id,
            "workspace_id": reference.workspace_id,
            "source_title": reference.source_title,
            "source_kind": reference.source_kind.value,
            "version_number": reference.version_number,
            "source_location": reference.source_location,
            "chunk_index": reference.chunk_index,
            "information_status": reference.information_status.value,
            "revision_reference": reference.revision_reference,
            "superseded_by": reference.superseded_by,
            "document_created_at": reference.document_created_at,
            "submitted_at": reference.submitted_at,
            "resolution_metadata": reference.resolution_metadata,
        }

    def list_chunks(self, source_id: str, version_id: str | None = None) -> list[dict[str, object]]:
        """Chunks of a source, optionally pinned to one version."""
        self.get_source(source_id)
        version = version_id or None
        if version is None:
            current = self._sources.current_version(source_id)
            if current is None:
                return []
            version = current.id
        chunks = self._chunks.list_for_version(version)
        return [
            {
                "chunk_id": chunk.id,
                "document_version_id": chunk.document_version_id,
                "chunk_index": chunk.chunk_index,
                "char_count": chunk.char_count,
                "source_location": chunk.source_location,
                "embedding_status": chunk.embedding_status.value,
                "preview": chunk.content[:200],
            }
            for chunk in chunks
        ]

    def delete_source(self, source_id: str, user_id: str) -> None:
        """Delete a source and every derived row.

        The storage object is removed by the ingestion service before this
        call; the database cascade removes versions, extracted text, chunks
        and provenance. Documented in docs/DATABASE_SCHEMA.md.
        """
        source = self.get_source(source_id)
        if source.owner_id != user_id:
            raise ForbiddenError(message="Only the user who submitted this source may delete it.")
        if not self._sources.delete(source_id):
            raise NotFoundError(message="Source not found.")
        logger.info(
            "Source deleted (kind=%s, status=%s)",
            source.kind.value,
            source.processing_status.value,
        )
