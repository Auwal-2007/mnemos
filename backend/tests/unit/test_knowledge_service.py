"""Unit tests for the knowledge service (Phase 2A).

The repositories are replaced by in-memory fakes so the service's
authorization and error behaviour is tested without a database. Real
database behaviour is covered by scripts/verify-migrations.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.errors import ForbiddenError, NotFoundError
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
    SourceLocation,
)
from app.services.knowledge_service import KnowledgeService

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
WS = "33333333-3333-4333-8333-333333333333"


def make_source(source_id: str = "src-1", owner: str = USER_A) -> Source:
    return Source(
        id=source_id,
        workspace_id=WS,
        owner_id=owner,
        kind=SourceKind.DOCUMENT,
        title="Paper",
        original_filename="paper.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        content_hash="a" * 64,
        storage_bucket="sources",
        storage_path=f"{owner}/paper.pdf",
        processing_status=ProcessingStatus.READY,
        processing_error_code=None,
        processing_error_detail=None,
        processing_attempts=1,
        metadata={},
        submitted_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_version(version_id: str = "ver-1", is_current: bool = True) -> DocumentVersion:
    return DocumentVersion(
        id=version_id,
        workspace_id=WS,
        source_id="src-1",
        version_number=1 if is_current else 0,
        content_hash="a" * 64,
        size_bytes=10,
        mime_type="application/pdf",
        storage_bucket="sources",
        storage_path=f"{USER_A}/paper.pdf",
        extraction_status=ExtractionStatus.EXTRACTED,
        extraction_method="pdf",
        extraction_error_code=None,
        is_current=is_current,
        submitted_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_reference() -> ProvenanceReference:
    return ProvenanceReference(
        provenance_id="prov-1",
        chunk_id="chunk-1",
        source_id="src-1",
        document_version_id="ver-1",
        workspace_id=WS,
        source_title="Paper",
        source_kind=SourceKind.DOCUMENT,
        version_number=1,
        source_location={"start_offset": 0, "end_offset": 12, "page": 2},
        chunk_index=0,
        information_status=InformationStatus.CURRENT,
        revision_reference=None,
        superseded_by=None,
        document_created_at=NOW,
        submitted_at=NOW,
        resolution_metadata={"method": "direct"},
    )


class FakeSourceRepository:
    def __init__(self, sources: Sequence[Source] = (), versions: Sequence[DocumentVersion] = ()):
        self.sources = {source.id: source for source in sources}
        self.versions = {version.id: version for version in versions}
        self.deleted: list[str] = []

    def list_for_workspace(
        self, workspace_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Source]:
        return [s for s in self.sources.values() if s.workspace_id == workspace_id][
            offset : offset + limit
        ]

    def get(self, source_id: str) -> Source | None:
        source = self.sources.get(source_id)
        # Emulate RLS: another user's rows are invisible, not forbidden.
        return source if source and source.owner_id == USER_A else None

    def find_by_idempotency_key(self, workspace_id: str, idempotency_key: str) -> Source | None:
        return None

    def create(self, **kwargs: Any) -> Source:
        raise NotImplementedError

    def update_processing(self, source_id: str, **kwargs: Any) -> Source | None:
        raise NotImplementedError

    def delete(self, source_id: str) -> bool:
        if source_id in self.sources:
            del self.sources[source_id]
            self.deleted.append(source_id)
            return True
        return False

    def create_version(self, **kwargs: Any) -> DocumentVersion:
        raise NotImplementedError

    def list_versions(self, source_id: str) -> list[DocumentVersion]:
        return [v for v in self.versions.values() if v.source_id == source_id]

    def get_version(self, version_id: str) -> DocumentVersion | None:
        return self.versions.get(version_id)

    def current_version(self, source_id: str) -> DocumentVersion | None:
        for version in self.versions.values():
            if version.source_id == source_id and version.is_current:
                return version
        return None

    def retire_version(self, version_id: str) -> None:
        raise NotImplementedError

    def update_version_extraction(self, version_id: str, **kwargs: Any) -> DocumentVersion | None:
        raise NotImplementedError


class FakeChunkRepository:
    def __init__(self, chunks: Sequence[Chunk] = (), reference: ProvenanceReference | None = None):
        self.chunks = list(chunks)
        self.reference = reference

    def create_many(self, **kwargs: Any) -> list[Chunk]:
        raise NotImplementedError

    def list_for_version(self, version_id: str) -> list[Chunk]:
        return [c for c in self.chunks if c.document_version_id == version_id]

    def count_for_version(self, version_id: str) -> int:
        return len(self.list_for_version(version_id))

    def delete_for_version(self, version_id: str) -> int:
        raise NotImplementedError

    def create_provenance(self, **kwargs: Any) -> ProvenanceReference:
        raise NotImplementedError

    def list_provenance_for_version(self, version_id: str) -> list[ProvenanceReference]:
        return [self.reference] if self.reference else []

    def resolve_for_chunk(self, chunk_id: str) -> ProvenanceReference | None:
        if self.reference and self.reference.chunk_id == chunk_id:
            return self.reference
        return None


def make_chunk() -> Chunk:
    return Chunk(
        id="chunk-1",
        workspace_id=WS,
        source_id="src-1",
        document_version_id="ver-1",
        chunk_index=0,
        content="Hello world." * 20,
        content_hash="a" * 64,
        char_count=240,
        source_location={"start_offset": 0, "end_offset": 240, "page": 2},
        chunking_method="paragraph",
        chunking_version=1,
        embedding_status=EmbeddingStatus.PENDING,
        created_at=NOW,
    )


def service(
    sources: FakeSourceRepository | None = None, chunks: FakeChunkRepository | None = None
) -> KnowledgeService:
    return KnowledgeService(sources or FakeSourceRepository(), chunks or FakeChunkRepository())


def test_list_sources_returns_workspace_rows() -> None:
    repo = FakeSourceRepository([make_source()])
    assert [s.id for s in service(repo).list_sources(WS)] == ["src-1"]


def test_get_source_hides_other_users_rows() -> None:
    repo = FakeSourceRepository([make_source(owner=USER_B)])
    with pytest.raises(NotFoundError):
        service(repo).get_source("src-1")


def test_get_source_unknown_id_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        service().get_source("does-not-exist")


def test_list_versions_requires_a_visible_source() -> None:
    repo = FakeSourceRepository([make_source()], [make_version()])
    assert [v.id for v in service(repo).list_versions("src-1")] == ["ver-1"]

    hidden = FakeSourceRepository([make_source(owner=USER_B)], [make_version()])
    with pytest.raises(NotFoundError):
        service(hidden).list_versions("src-1")


def test_resolve_provenance_returns_full_contract() -> None:
    chunks = FakeChunkRepository(reference=make_reference())
    payload = service(chunks=chunks).resolve_provenance("chunk-1")
    assert payload["source_id"] == "src-1"
    assert payload["document_version_id"] == "ver-1"
    assert payload["version_number"] == 1
    assert payload["source_location"] == {"start_offset": 0, "end_offset": 12, "page": 2}
    assert payload["information_status"] == "current"


def test_resolve_provenance_without_record_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        service(chunks=FakeChunkRepository()).resolve_provenance("chunk-1")


def test_list_chunks_uses_current_version_by_default() -> None:
    chunks = FakeChunkRepository([make_chunk()])
    rows = service(FakeSourceRepository([make_source()], [make_version()]), chunks).list_chunks(
        "src-1"
    )
    assert len(rows) == 1
    assert rows[0]["chunk_index"] == 0
    # Preview is truncated so the API never ships the whole document.
    assert len(str(rows[0]["preview"])) == 200


def test_list_chunks_without_current_version_is_empty() -> None:
    svc = service(FakeSourceRepository([make_source()]), FakeChunkRepository([make_chunk()]))
    assert svc.list_chunks("src-1") == []


def test_delete_source_requires_ownership() -> None:
    repo = FakeSourceRepository([make_source()])
    with pytest.raises(ForbiddenError):
        service(repo).delete_source("src-1", USER_B)
    assert repo.deleted == []


def test_delete_source_by_owner_cascades_repository_call() -> None:
    repo = FakeSourceRepository([make_source()])
    service(repo).delete_source("src-1", USER_A)
    assert repo.deleted == ["src-1"]


def test_delete_unknown_source_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        service().delete_source("nope", USER_A)


def test_source_location_round_trips() -> None:
    location = SourceLocation(start_offset=10, end_offset=40, page=3, section="Intro")
    assert SourceLocation.from_json(location.to_json()) == location


def test_source_location_omits_absent_fields() -> None:
    assert SourceLocation(0, 5).to_json() == {"start_offset": 0, "end_offset": 5}


def test_provenance_reference_reports_whether_location_is_available() -> None:
    assert make_reference().has_location() is True

    no_location = replace(make_reference(), source_location={})
    assert no_location.has_location() is False


def test_chunk_draft_matches_location_contract() -> None:
    draft = ChunkDraft(
        chunk_index=0,
        content="abc",
        content_hash="a" * 64,
        source_location=SourceLocation(0, 3),
    )
    assert draft.source_location.to_json() == {"start_offset": 0, "end_offset": 3}
