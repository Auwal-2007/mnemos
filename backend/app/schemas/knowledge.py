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
