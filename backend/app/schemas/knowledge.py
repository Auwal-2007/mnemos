"""Knowledge API schemas (Phase 2A)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceResponse(BaseModel):
    """A source as presented to the UI.

    `processing_status` is the honest pipeline position. `can_delete` and
    `can_ingest_version` are computed server-side so the UI never offers a
    control the server would reject.
    """

    id: str
    workspace_id: str
    owner_id: str
    kind: Literal["document", "note"]
    title: str
    original_filename: str | None
    mime_type: str
    size_bytes: int
    content_hash: str
    processing_status: str
    processing_error_code: str | None = None
    processing_error_detail: str | None = None
    processing_attempts: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    submitted_at: datetime
    created_at: datetime
    updated_at: datetime


class DocumentVersionResponse(BaseModel):
    """One immutable submission of a source."""

    id: str
    source_id: str
    version_number: int
    content_hash: str
    size_bytes: int
    mime_type: str
    extraction_status: str
    extraction_method: str | None = None
    is_current: bool
    submitted_at: datetime
    created_at: datetime


class SourceDetailResponse(SourceResponse):
    """Source plus its version history and current version."""

    versions: list[DocumentVersionResponse] = Field(default_factory=list)
    current_version: DocumentVersionResponse | None = None


class ChunkSummaryResponse(BaseModel):
    """Chunk metadata; the text itself is only exposed to its owner."""

    chunk_id: str
    document_version_id: str
    chunk_index: int
    char_count: int
    source_location: dict[str, Any]
    embedding_status: str
    preview: str


class ChunkListResponse(BaseModel):
    items: list[ChunkSummaryResponse]
    total: int


class ProvenanceResponse(BaseModel):
    """The reusable provenance contract, resolved for one chunk."""

    provenance_id: str
    chunk_id: str
    source_id: str
    document_version_id: str
    workspace_id: str
    source_title: str
    source_kind: str
    version_number: int
    source_location: dict[str, Any]
    chunk_index: int
    information_status: str
    revision_reference: str | None = None
    superseded_by: str | None = None
    document_created_at: datetime
    submitted_at: datetime
    resolution_metadata: dict[str, Any] = Field(default_factory=dict)


# --- Phase 2B: ingestion --------------------------------------------------


class NoteCreateRequest(BaseModel):
    """A typed note submitted as a versioned source."""

    workspace_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=200_000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


class ExtractionOutcomeResponse(BaseModel):
    """What happened to the text of the version just stored."""

    status: str
    method: str | None = None
    char_count: int = 0
    page_count: int = 0
    segment_count: int = 0
    error_code: str | None = None
    error_message: str | None = None


class IngestionResponse(BaseModel):
    """Accurate result of a submission.

    `duplicate_of_existing` is true when an idempotency key matched an earlier
    submission; the UI then says "already submitted" instead of implying a new
    document was created.
    """

    source: SourceResponse
    version_id: str | None = None
    version_number: int | None = None
    extraction: ExtractionOutcomeResponse
    duplicate_of_existing: bool = False


class DownloadUrlResponse(BaseModel):
    """Short-lived, user-scoped download link for an original."""

    url: str
    expires_in_seconds: int


# --- Phase 2C: indexing ---------------------------------------------------


class IndexSourceResponse(BaseModel):
    """The honest result of a chunk/embed run.

    `processing_status` is read back from the database, so it reflects what was
    actually persisted rather than what the code intended.
    """

    source_id: str
    processing_status: str
    chunk_count: int = 0
    chunks_created: bool = False
    embeddings_created: int = 0
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class EmbeddingStatusResponse(BaseModel):
    """Coverage of embeddings for a source's chunks."""

    source_id: str
    total_chunks: int
    embedded_chunks: int
    pending_chunks: int
    embedding_model: str | None = None
    configured: bool = False
