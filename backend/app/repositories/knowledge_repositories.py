"""Supabase implementations for the knowledge repositories (Phase 2A).

Every call goes through the caller's token-bound client, so RLS decides what
is visible. Nothing here accepts SQL text; the only vocabulary is the named
methods below.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from postgrest.exceptions import APIError
from supabase import Client

from app.core.errors import ForbiddenError, MnemosError, NotFoundError
from app.domain.knowledge import (
    Chunk,
    ChunkDraft,
    DocumentVersion,
    EmbeddingStatus,
    ExtractionStatus,
    InformationStatus,
    ProcessingStatus,
    ProvenanceReference,
    Source,
    SourceKind,
)
from app.repositories.supabase_repositories import (
    RepositoryError,
    _BaseSupabaseRepository,
    _parse_datetime,
)
from app.services.ingestion.extraction import ExtractionResult

logger = logging.getLogger("mnemos.repositories.knowledge")


def _source(row: dict[str, Any]) -> Source:
    return Source(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        owner_id=str(row["owner_id"]),
        kind=SourceKind(row["kind"]),
        title=str(row["title"]),
        original_filename=cast("str | None", row.get("original_filename")),
        mime_type=str(row["mime_type"]),
        size_bytes=int(row["size_bytes"]),
        content_hash=str(row["content_hash"]),
        storage_bucket=str(row["storage_bucket"]),
        storage_path=str(row["storage_path"]),
        processing_status=ProcessingStatus(row["processing_status"]),
        processing_error_code=cast("str | None", row.get("processing_error_code")),
        processing_error_detail=cast("str | None", row.get("processing_error_detail")),
        processing_attempts=int(row.get("processing_attempts") or 0),
        metadata=cast("dict[str, Any]", row.get("metadata") or {}),
        submitted_at=_parse_datetime(row.get("submitted_at")),
        created_at=_parse_datetime(row.get("created_at")),
        updated_at=_parse_datetime(row.get("updated_at")),
    )


def _version(row: dict[str, Any]) -> DocumentVersion:
    return DocumentVersion(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        source_id=str(row["source_id"]),
        version_number=int(row["version_number"]),
        content_hash=str(row["content_hash"]),
        size_bytes=int(row["size_bytes"]),
        mime_type=str(row["mime_type"]),
        storage_bucket=str(row["storage_bucket"]),
        storage_path=str(row["storage_path"]),
        extraction_status=ExtractionStatus(row["extraction_status"]),
        extraction_method=cast("str | None", row.get("extraction_method")),
        extraction_error_code=cast("str | None", row.get("extraction_error_code")),
        is_current=bool(row["is_current"]),
        submitted_at=_parse_datetime(row.get("submitted_at")),
        created_at=_parse_datetime(row.get("created_at")),
        updated_at=_parse_datetime(row.get("updated_at")),
    )


def _chunk(row: dict[str, Any]) -> Chunk:
    return Chunk(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        source_id=str(row["source_id"]),
        document_version_id=str(row["document_version_id"]),
        chunk_index=int(row["chunk_index"]),
        content=str(row["content"]),
        content_hash=str(row["content_hash"]),
        char_count=int(row["char_count"]),
        source_location=cast("dict[str, Any]", row["source_location"]),
        chunking_method=str(row["chunking_method"]),
        chunking_version=int(row["chunking_version"]),
        embedding_status=EmbeddingStatus(row["embedding_status"]),
        metadata=cast("dict[str, Any]", row.get("metadata") or {}),
        created_at=_parse_datetime(row.get("created_at")),
    )


def _provenance(row: dict[str, Any]) -> ProvenanceReference:
    return ProvenanceReference(
        provenance_id=str(row["provenance_id"]),
        chunk_id=str(row["chunk_id"]),
        source_id=str(row["source_id"]),
        document_version_id=str(row["document_version_id"]),
        workspace_id=str(row["workspace_id"]),
        source_title=str(row["source_title"]),
        source_kind=SourceKind(row["source_kind"]),
        version_number=int(row["version_number"]),
        source_location=cast("dict[str, Any]", row["source_location"]),
        chunk_index=int(row["chunk_index"]),
        information_status=InformationStatus(row["information_status"]),
        revision_reference=cast("str | None", row.get("revision_reference")),
        superseded_by=cast("str | None", row.get("superseded_by")),
        document_created_at=_parse_datetime(row.get("document_created_at")),
        submitted_at=_parse_datetime(row.get("submitted_at")),
        resolution_metadata=cast("dict[str, Any]", row.get("resolution_metadata") or {}),
    )


def sha256_hex(text: str) -> str:
    """Lowercase sha256 hex of UTF-8 text. Matches the database check."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SupabaseSourceRepository(_BaseSupabaseRepository):
    """Sources and document versions."""

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    # --- sources ---------------------------------------------------------
    def list_for_workspace(
        self, workspace_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Source]:
        try:
            response = (
                self._client.table("sources")
                .select("*")
                .eq("workspace_id", workspace_id)
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        return [_source(cast("dict[str, Any]", row)) for row in response.data or []]

    def get(self, source_id: str) -> Source | None:
        try:
            response = (
                self._client.table("sources")
                .select("*")
                .eq("id", source_id)
                .maybe_single()
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        data = response.data if response else None
        return _source(cast("dict[str, Any]", data)) if data else None

    def find_by_idempotency_key(self, workspace_id: str, idempotency_key: str) -> Source | None:
        try:
            response = (
                self._client.table("sources")
                .select("*")
                .eq("workspace_id", workspace_id)
                .eq("idempotency_key", idempotency_key)
                .limit(1)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        return _source(cast("dict[str, Any]", rows[0])) if rows else None

    def create(
        self,
        *,
        workspace_id: str,
        owner_id: str,
        kind: SourceKind,
        title: str,
        original_filename: str | None,
        mime_type: str,
        size_bytes: int,
        content_hash: str,
        storage_path: str,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Source:
        payload: dict[str, Any] = {
            "workspace_id": workspace_id,
            "owner_id": owner_id,
            "kind": kind.value,
            "title": title,
            "original_filename": original_filename,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "content_hash": content_hash,
            "storage_path": storage_path,
            "metadata": metadata or {},
            "idempotency_key": idempotency_key,
            "processing_status": ProcessingStatus.PENDING.value,
            "submitted_at": datetime.now(UTC).isoformat(),
        }
        try:
            response = self._client.table("sources").insert(payload).execute()
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        if not rows:
            # An insert blocked by RLS returns no rows; never pretend success.
            raise ForbiddenError(message="You are not allowed to add sources to this workspace.")
        return _source(cast("dict[str, Any]", rows[0]))

    def update_processing(
        self,
        source_id: str,
        *,
        status: ProcessingStatus,
        error_code: str | None = None,
        error_detail: str | None = None,
        increment_attempts: bool = False,
    ) -> Source | None:
        payload: dict[str, Any] = {
            "processing_status": status.value,
            "processing_error_code": error_code,
            "processing_error_detail": error_detail,
        }
        if increment_attempts:
            current = self.get(source_id)
            if current is None:
                return None
            payload["processing_attempts"] = current.processing_attempts + 1
        try:
            response = self._client.table("sources").update(payload).eq("id", source_id).execute()
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        return _source(cast("dict[str, Any]", rows[0])) if rows else None

    def delete(self, source_id: str) -> bool:
        try:
            response = self._client.table("sources").delete().eq("id", source_id).execute()
        except APIError as exc:
            raise self._translate(exc) from exc
        return bool(response.data)

    # --- versions --------------------------------------------------------
    def create_version(
        self,
        *,
        workspace_id: str,
        source_id: str,
        content_hash: str,
        size_bytes: int,
        mime_type: str,
        storage_path: str,
        submitted_by: str,
        idempotency_key: str | None = None,
    ) -> DocumentVersion:
        payload: dict[str, Any] = {
            "workspace_id": workspace_id,
            "source_id": source_id,
            "content_hash": content_hash,
            "size_bytes": size_bytes,
            "mime_type": mime_type,
            "storage_path": storage_path,
            "submitted_by": submitted_by,
            "idempotency_key": idempotency_key,
            "submitted_at": datetime.now(UTC).isoformat(),
        }
        try:
            response = self._client.table("document_versions").insert(payload).execute()
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        if not rows:
            raise ForbiddenError(message="You are not allowed to add a version to this source.")
        return _version(cast("dict[str, Any]", rows[0]))

    def list_versions(self, source_id: str) -> list[DocumentVersion]:
        try:
            response = (
                self._client.table("document_versions")
                .select("*")
                .eq("source_id", source_id)
                .order("version_number", desc=True)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        return [_version(cast("dict[str, Any]", row)) for row in response.data or []]

    def get_version(self, version_id: str) -> DocumentVersion | None:
        try:
            response = (
                self._client.table("document_versions")
                .select("*")
                .eq("id", version_id)
                .maybe_single()
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        data = response.data if response else None
        return _version(cast("dict[str, Any]", data)) if data else None

    def current_version(self, source_id: str) -> DocumentVersion | None:
        try:
            response = (
                self._client.table("document_versions")
                .select("*")
                .eq("source_id", source_id)
                .eq("is_current", True)
                .limit(1)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        return _version(cast("dict[str, Any]", rows[0])) if rows else None

    def retire_version(self, version_id: str) -> None:
        try:
            response = (
                self._client.table("document_versions")
                .update({"is_current": False})
                .eq("id", version_id)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        if not response.data:
            raise NotFoundError(message="Document version not found.")

    def store_extraction(
        self,
        *,
        workspace_id: str,
        document_version_id: str,
        result: ExtractionResult,
    ) -> None:
        """Persist extracted text and its segment map for one version.

        Re-extraction replaces the previous extraction of *that version* only.
        A new version gets its own row, so history is never rewritten.
        """
        payload = {
            "workspace_id": workspace_id,
            "document_version_id": document_version_id,
            "content": result.text,
            "content_hash": result.content_hash,
            "char_count": result.char_count,
            "extraction_method": result.method,
            "page_count": result.page_count,
            "metadata": result.metadata,
        }
        try:
            self._client.table("extracted_contents").delete().eq(
                "document_version_id", document_version_id
            ).execute()
            self._client.table("extracted_contents").insert(payload).execute()
            if result.segments:
                self._client.table("extracted_pages").insert(
                    [
                        {
                            "workspace_id": workspace_id,
                            "document_version_id": document_version_id,
                            "page_number": segment.number,
                            "start_offset": segment.start_offset,
                            "end_offset": segment.end_offset,
                        }
                        for segment in result.segments
                    ]
                ).execute()
        except APIError as exc:
            raise self._translate(exc) from exc

    def update_version_extraction(
        self,
        version_id: str,
        *,
        status: ExtractionStatus,
        method: str | None = None,
        error_code: str | None = None,
    ) -> DocumentVersion | None:
        payload: dict[str, Any] = {
            "extraction_status": status.value,
            "extraction_method": method,
            "extraction_error_code": error_code,
        }
        if status is ExtractionStatus.EXTRACTED:
            payload["extracted_at"] = datetime.now(UTC).isoformat()
        try:
            response = (
                self._client.table("document_versions")
                .update(payload)
                .eq("id", version_id)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        return _version(cast("dict[str, Any]", rows[0])) if rows else None


class SupabaseChunkRepository(_BaseSupabaseRepository):
    """Chunks and provenance records."""

    def __init__(self, client: Client) -> None:
        super().__init__(client)

    def create_many(
        self,
        *,
        workspace_id: str,
        source_id: str,
        document_version_id: str,
        chunks: Sequence[ChunkDraft],
        chunking_method: str,
        chunking_version: int,
        chunking_config: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        if not chunks:
            return []
        payload = [
            {
                "workspace_id": workspace_id,
                "source_id": source_id,
                "document_version_id": document_version_id,
                "chunk_index": draft.chunk_index,
                "content": draft.content,
                "content_hash": draft.content_hash,
                "char_count": len(draft.content),
                "source_location": draft.source_location.to_json(),
                "chunking_method": chunking_method,
                "chunking_version": chunking_version,
                "metadata": {"chunking_config": chunking_config} if chunking_config else {},
            }
            for draft in chunks
        ]
        try:
            response = self._client.table("chunks").insert(payload).execute()
        except APIError as exc:
            raise self._translate(exc) from exc
        return [_chunk(cast("dict[str, Any]", row)) for row in response.data or []]

    def list_for_version(self, version_id: str) -> list[Chunk]:
        try:
            response = (
                self._client.table("chunks")
                .select("*")
                .eq("document_version_id", version_id)
                .order("chunk_index", desc=False)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        return [_chunk(cast("dict[str, Any]", row)) for row in response.data or []]

    def count_for_version(self, version_id: str) -> int:
        try:
            response = (
                self._client.table("chunks")
                .select("id", count=cast("Any", "exact"))
                .eq("document_version_id", version_id)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        return int(response.count or 0)

    def delete_for_version(self, version_id: str) -> int:
        try:
            response = (
                self._client.table("chunks")
                .delete()
                .eq("document_version_id", version_id)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        return len(response.data or [])

    def create_provenance(
        self,
        *,
        workspace_id: str,
        source_id: str,
        document_version_id: str,
        chunk_id: str,
        source_location: dict[str, Any],
        submitted_at: datetime,
        information_status: InformationStatus = InformationStatus.CURRENT,
    ) -> ProvenanceReference:
        payload = {
            "workspace_id": workspace_id,
            "source_id": source_id,
            "document_version_id": document_version_id,
            "chunk_id": chunk_id,
            "source_location": source_location,
            "information_status": information_status.value,
            "submitted_at": submitted_at.isoformat(),
        }
        try:
            # The table has no direct columns for the joined display fields;
            # insert then resolve through the SQL function.
            self._client.table("provenance_records").insert(payload).execute()
        except APIError as exc:
            raise self._translate(exc) from exc
        resolved = self.resolve_for_chunk(chunk_id)
        if resolved is None:
            raise RepositoryError(message="Provenance record could not be resolved after insert.")
        return resolved

    def list_provenance_for_version(self, version_id: str) -> list[ProvenanceReference]:
        try:
            response = (
                self._client.table("chunks")
                .select("id")
                .eq("document_version_id", version_id)
                .order("chunk_index", desc=False)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        chunk_ids = [str(row["id"]) for row in response.data or []]
        resolved: list[ProvenanceReference] = []
        for chunk_id in chunk_ids:
            reference = self.resolve_for_chunk(chunk_id)
            if reference is not None:
                resolved.append(reference)
        return resolved

    def resolve_for_chunk(self, chunk_id: str) -> ProvenanceReference | None:
        try:
            response = self._client.rpc(
                "resolve_chunk_provenance", {"p_chunk_id": chunk_id}
            ).execute()
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        if not rows:
            return None
        return _provenance(cast("dict[str, Any]", rows[0]))


class SupabaseEmbeddingRepository:
    """Vector persistence for `chunk_embeddings` (Phase 2C)."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def list_embedded_chunk_ids(self, version_id: str) -> set[str]:
        try:
            response = (
                self._client.table("chunk_embeddings")
                .select("chunk_id")
                .eq("document_version_id", version_id)
                .execute()
            )
        except APIError as exc:
            raise _translate_error(exc) from exc
        return {str(row["chunk_id"]) for row in response.data or []}

    def store_embeddings(
        self,
        *,
        workspace_id: str,
        document_version_id: str,
        model_id: str,
        dimension: int,
        vectors: Sequence[tuple[str, list[float]]],
    ) -> int:
        if not vectors:
            return 0
        payload = [
            {
                "chunk_id": chunk_id,
                "workspace_id": workspace_id,
                "document_version_id": document_version_id,
                "embedding_model": model_id,
                "embedding_dim": dimension,
                # pgvector accepts a JSON array literal for a vector column.
                "embedding": values,
            }
            for chunk_id, values in vectors
        ]
        try:
            response = (
                self._client.table("chunk_embeddings")
                .upsert(payload, on_conflict="chunk_id")
                .execute()
            )
        except APIError as exc:
            raise _translate_error(exc) from exc
        return len(response.data or [])

    def delete_for_version(self, version_id: str) -> int:
        try:
            response = (
                self._client.table("chunk_embeddings")
                .delete()
                .eq("document_version_id", version_id)
                .execute()
            )
        except APIError as exc:
            raise _translate_error(exc) from exc
        return len(response.data or [])

    def match(
        self,
        *,
        workspace_id: str,
        query_embedding: list[float],
        match_count: int = 10,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Cosine similarity search, scoped by RLS at the caller's identity."""
        try:
            response = self._client.rpc(
                "match_chunks",
                {
                    "p_workspace_id": workspace_id,
                    "p_query_embedding": query_embedding,
                    "p_match_count": match_count,
                    "p_min_similarity": min_similarity,
                },
            ).execute()
        except APIError as exc:
            raise _translate_error(exc) from exc
        return [dict(row) for row in response.data or []]


class SupabaseExtractionReader:
    """Reads extracted text plus its page map for chunking."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def read_extraction(self, version_id: str) -> tuple[str, list[Any], dict[str, Any]] | None:
        from app.services.chunking import PageRange

        try:
            content_response = (
                self._client.table("extracted_contents")
                .select("content,metadata")
                .eq("document_version_id", version_id)
                .maybe_single()
                .execute()
            )
            if not content_response or not content_response.data:
                return None
            row = cast("dict[str, Any]", content_response.data)

            pages_response = (
                self._client.table("extracted_pages")
                .select("page_number,start_offset,end_offset")
                .eq("document_version_id", version_id)
                .order("page_number", desc=False)
                .execute()
            )
        except APIError as exc:
            raise _translate_error(exc) from exc

        pages = [
            PageRange(
                number=int(page["page_number"]),
                start_offset=int(page["start_offset"]),
                end_offset=int(page["end_offset"]),
            )
            for page in pages_response.data or []
        ]
        return str(row["content"]), pages, cast("dict[str, Any]", row.get("metadata") or {})


def _translate_error(exc: APIError) -> MnemosError:
    from app.repositories.supabase_repositories import _BaseSupabaseRepository

    return _BaseSupabaseRepository._translate(exc)
