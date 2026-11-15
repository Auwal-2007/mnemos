"""Knowledge domain models (Phase 2A).

These dataclasses describe the provenance-aware knowledge model. They are
deliberately independent of Pydantic and of the database driver, exactly like
the Phase 1 domain models.

Terminology (see docs/PROVENANCE_MODEL.md):

    Source           the submitted item (upload or note)
    DocumentVersion  one immutable submission of a source
    ExtractedContent text derived from a version — never the original
    Chunk            a deterministic slice of a version
    Provenance       the durable citation identity of a chunk

A `ProvenanceReference` is the reusable contract that every later stage
(retrieval, generation, verification, display) must carry so that no
generated text can ever lose the connection to its exact source and version.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class SourceKind(StrEnum):
    """How a source came into being."""

    DOCUMENT = "document"
    NOTE = "note"


class ProcessingStatus(StrEnum):
    """Position of a source in the ingestion pipeline."""

    PENDING = "pending"
    VALIDATING = "validating"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    CHUNKING = "chunking"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


#: Statuses from which no further progress is expected without a new attempt.
TERMINAL_STATUSES: frozenset[ProcessingStatus] = frozenset(
    {ProcessingStatus.READY, ProcessingStatus.FAILED}
)


class ExtractionStatus(StrEnum):
    """Position of one version's text-extraction step."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED = "failed"


class EmbeddingStatus(StrEnum):
    """Position of one chunk's embedding step."""

    PENDING = "pending"
    EMBEDDED = "embedded"
    FAILED = "failed"


class InformationStatus(StrEnum):
    """Epistemic status of a passage.

    This is *not* the same axis as `ProcessingStatus`. A document can be fully
    processed (`ready`) while the information it contains is `superseded`.
    """

    CURRENT = "current"
    SUPERSEDED = "superseded"
    DISPUTED = "disputed"
    ARCHIVED = "archived"
    PENDING_REVIEW = "pending_review"


@dataclass(frozen=True, slots=True)
class Source:
    """A submitted item belonging to one workspace."""

    id: str
    workspace_id: str
    owner_id: str
    kind: SourceKind
    title: str
    original_filename: str | None
    mime_type: str
    size_bytes: int
    content_hash: str
    storage_bucket: str
    storage_path: str
    processing_status: ProcessingStatus
    processing_error_code: str | None
    processing_error_detail: str | None
    processing_attempts: int
    metadata: dict[str, Any]
    submitted_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    """One immutable submission of a source."""

    id: str
    workspace_id: str
    source_id: str
    version_number: int
    content_hash: str
    size_bytes: int
    mime_type: str
    storage_bucket: str
    storage_path: str
    extraction_status: ExtractionStatus
    extraction_method: str | None
    extraction_error_code: str | None
    is_current: bool
    submitted_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Chunk:
    """A deterministic slice of a version."""

    id: str
    workspace_id: str
    source_id: str
    document_version_id: str
    chunk_index: int
    content: str
    content_hash: str
    char_count: int
    source_location: dict[str, Any]
    chunking_method: str
    chunking_version: int
    embedding_status: EmbeddingStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Where a chunk sits inside the original document.

    `start_offset`/`end_offset` are half-open character offsets into the
    extracted text. `page` is present when the original had pages.
    """

    start_offset: int
    end_offset: int
    page: int | None = None
    section: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
        }
        if self.page is not None:
            payload["page"] = self.page
        if self.section is not None:
            payload["section"] = self.section
        return payload

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> SourceLocation:
        page = payload.get("page")
        section = payload.get("section")
        return cls(
            start_offset=int(payload["start_offset"]),
            end_offset=int(payload["end_offset"]),
            page=int(page) if page is not None else None,
            section=str(section) if section is not None else None,
        )


@dataclass(frozen=True, slots=True)
class ProvenanceReference:
    """The reusable provenance contract.

    Every piece of evidence shown to a user, and every claim an agent makes,
    must be expressible as one of these. If a value cannot be produced here,
    the system must say the location is unavailable — never invent one.
    """

    provenance_id: str
    chunk_id: str
    source_id: str
    document_version_id: str
    workspace_id: str
    source_title: str
    source_kind: SourceKind
    version_number: int
    source_location: dict[str, Any]
    chunk_index: int
    information_status: InformationStatus
    revision_reference: str | None
    superseded_by: str | None
    document_created_at: datetime
    submitted_at: datetime
    resolution_metadata: dict[str, Any]

    @property
    def location(self) -> SourceLocation:
        """Typed view of `source_location`."""
        return SourceLocation.from_json(self.source_location)

    def has_location(self) -> bool:
        """True when a page or offset can be reported to the user."""
        location = self.source_location
        return bool(location.get("page")) or (
            location.get("start_offset") is not None and location.get("end_offset") is not None
        )


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    """A chunk that has been computed but not yet persisted.

    Produced by the chunking service, consumed by the repository. Keeping it
    as a domain type avoids the repository layer depending on a service.
    """

    chunk_index: int
    content: str
    content_hash: str
    source_location: SourceLocation
