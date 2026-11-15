"""Indexing service tests (Phase 2C).

Fakes for chunk/vector persistence; the real chunking and a fake provider. What
is under test is the orchestration invariants:

* a chunk is never rewritten in place under a different configuration;
* re-running skips completed work instead of duplicating it;
* a partial failure leaves a specific code and a truthful status;
* `ready` is only reached when everything succeeded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.errors import MnemosError
from app.domain.knowledge import (
    Chunk,
    ChunkDraft,
    DocumentVersion,
    EmbeddingStatus,
    ExtractionStatus,
    ProcessingStatus,
    Source,
    SourceKind,
)
from app.infrastructure.embeddings import (
    EmbeddingBatch,
    EmbeddingError,
    EmbeddingNotConfiguredError,
    EmbeddingVector,
)
from app.services.chunking import ChunkingConfig, PageRange
from app.services.indexing import IndexingService

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
WS = "33333333-3333-4333-8333-333333333333"
DIM = 8


def make_source(status: ProcessingStatus = ProcessingStatus.EXTRACTED) -> Source:
    return Source(
        id="src-1",
        workspace_id=WS,
        owner_id="u-1",
        kind=SourceKind.DOCUMENT,
        title="Doc",
        original_filename="d.txt",
        mime_type="text/plain",
        size_bytes=10,
        content_hash="a" * 64,
        storage_bucket="sources",
        storage_path="u-1/d.txt",
        processing_status=status,
        processing_error_code=None,
        processing_error_detail=None,
        processing_attempts=0,
        metadata={},
        submitted_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_version() -> DocumentVersion:
    return DocumentVersion(
        id="ver-1",
        workspace_id=WS,
        source_id="src-1",
        version_number=1,
        content_hash="a" * 64,
        size_bytes=10,
        mime_type="text/plain",
        storage_bucket="sources",
        storage_path="u-1/d.txt",
        extraction_status=ExtractionStatus.EXTRACTED,
        extraction_method="plain-text",
        extraction_error_code=None,
        is_current=True,
        submitted_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeChunkStore:
    def __init__(self) -> None:
        self.by_version: dict[str, list[Chunk]] = {}
        self.next_id = 0
        self.deleted: list[str] = []

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
        created = []
        for draft in chunks:
            self.next_id += 1
            created.append(
                Chunk(
                    id=f"chunk-{self.next_id}",
                    workspace_id=workspace_id,
                    source_id=source_id,
                    document_version_id=document_version_id,
                    chunk_index=draft.chunk_index,
                    content=draft.content,
                    content_hash=draft.content_hash,
                    char_count=len(draft.content),
                    source_location=draft.source_location.to_json(),
                    chunking_method=chunking_method,
                    chunking_version=chunking_version,
                    embedding_status=EmbeddingStatus.PENDING,
                    metadata={"chunking_config": chunking_config} if chunking_config else {},
                    created_at=NOW,
                )
            )
        self.by_version[document_version_id] = created
        return created

    def list_for_version(self, version_id: str) -> list[Chunk]:
        return self.by_version.get(version_id, [])

    def delete_for_version(self, version_id: str) -> int:
        self.deleted.append(version_id)
        removed = self.by_version.pop(version_id, [])
        return len(removed)


class FakeEmbeddingStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.batches: list[int] = []

    def list_embedded_chunk_ids(self, version_id: str) -> set[str]:
        return {
            chunk_id
            for chunk_id, row in self.rows.items()
            if row["document_version_id"] == version_id
        }

    def store_embeddings(
        self,
        *,
        workspace_id: str,
        document_version_id: str,
        model_id: str,
        dimension: int,
        vectors: Sequence[tuple[str, list[float]]],
    ) -> int:
        self.batches.append(len(vectors))
        for chunk_id, values in vectors:
            self.rows[chunk_id] = {
                "workspace_id": workspace_id,
                "document_version_id": document_version_id,
                "model_id": model_id,
                "dimension": dimension,
                "values": values,
            }
        return len(vectors)

    def delete_for_version(self, version_id: str) -> int:
        doomed = [
            chunk_id
            for chunk_id, row in self.rows.items()
            if row["document_version_id"] == version_id
        ]
        for chunk_id in doomed:
            del self.rows[chunk_id]
        return len(doomed)


class FakeExtractions:
    def __init__(
        self, text: str | None = "First sentence. Second sentence. Third sentence."
    ) -> None:
        self.text = text
        self.pages: list[PageRange] = []

    def read_extraction(
        self, version_id: str
    ) -> tuple[str, list[PageRange], dict[str, Any]] | None:
        if self.text is None:
            return None
        return self.text, self.pages, {}


class FakeSourceRepo:
    def __init__(self, source: Source) -> None:
        self.source = source
        self.statuses: list[str] = []

    def get(self, source_id: str) -> Source | None:
        return self.source if source_id == self.source.id else None

    def get_version(self, version_id: str) -> DocumentVersion | None:
        return make_version()

    def update_processing(
        self,
        source_id: str,
        *,
        status: ProcessingStatus,
        error_code: str | None = None,
        error_detail: str | None = None,
        increment_attempts: bool = False,
    ) -> Source | None:
        self.statuses.append(status.value)
        self.source = replace(
            self.source, processing_status=status, processing_error_code=error_code
        )
        return self.source


class FakeProvider:
    def __init__(self, *, fail: Exception | None = None, dim: int = DIM) -> None:
        self.fail = fail
        self._dim = dim
        self.calls = 0

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_id(self) -> str:
        return "test/model"

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        self.calls += 1
        if self.fail:
            raise self.fail
        return EmbeddingBatch(
            vectors=[
                EmbeddingVector(index=index, values=[0.1] * self._dim)
                for index in range(len(texts))
            ],
            model="test/model",
            prompt_tokens=5 * len(texts),
            latency_ms=12,
        )


def build(
    *,
    provider: FakeProvider | None = None,
    text: str | None = "First sentence. Second sentence. Third sentence.",
    chunks: FakeChunkStore | None = None,
    embeddings: FakeEmbeddingStore | None = None,
    repo: FakeSourceRepo | None = None,
) -> tuple[IndexingService, FakeChunkStore, FakeEmbeddingStore, FakeSourceRepo]:
    chunk_store = chunks or FakeChunkStore()
    vector_store = embeddings or FakeEmbeddingStore()
    source_repo = repo or FakeSourceRepo(make_source())
    service = IndexingService(
        sources=source_repo,
        chunks=chunk_store,
        embeddings=vector_store,
        extractions=FakeExtractions(text),
        provider=provider if provider is not None else FakeProvider(),
        config=ChunkingConfig(target_chars=50, overlap_chars=10),
    )
    return service, chunk_store, vector_store, source_repo


# --- chunking ------------------------------------------------------------


def test_chunks_are_created_with_the_recorded_configuration() -> None:
    service, chunks, _, _ = build()
    outcome = service.chunk_version(source=make_source(), version=make_version())

    assert outcome.created is True
    assert outcome.chunk_count == len(chunks.list_for_version("ver-1"))
    assert outcome.config["method"] == "paragraph-window"
    for chunk in chunks.list_for_version("ver-1"):
        assert chunk.chunking_method == "paragraph-window"
        assert chunk.chunking_version == 1


def test_chunking_is_skipped_when_identical_work_exists() -> None:
    service, chunks, _, _ = build()
    first = service.chunk_version(source=make_source(), version=make_version())
    second = service.chunk_version(source=make_source(), version=make_version())

    assert first.created is True
    assert second.created is False
    assert second.chunk_count == first.chunk_count
    assert len(chunks.list_for_version("ver-1")) == first.chunk_count


def test_a_different_configuration_refuses_to_mix_chunk_shapes() -> None:
    service, chunks, _, _ = build()
    service.chunk_version(source=make_source(), version=make_version())

    other = IndexingService(
        sources=FakeSourceRepo(make_source()),
        chunks=chunks,
        embeddings=FakeEmbeddingStore(),
        extractions=FakeExtractions(),
        provider=FakeProvider(),
        config=ChunkingConfig(target_chars=500, overlap_chars=0),
    )
    with pytest.raises(MnemosError) as error:
        other.chunk_version(source=make_source(), version=make_version())
    assert "different chunking configuration" in error.value.message


def test_missing_extraction_is_an_error() -> None:
    service, _, _, _ = build(text=None)
    with pytest.raises(MnemosError) as error:
        service.chunk_version(source=make_source(), version=make_version())
    assert "no extracted text" in error.value.message


# --- embedding -----------------------------------------------------------


async def test_every_chunk_gets_a_vector() -> None:
    service, chunks, embeddings, _ = build()
    service.chunk_version(source=make_source(), version=make_version())
    outcome = await service.embed_chunks(source=make_source(), version=make_version())

    created = chunks.list_for_version("ver-1")
    assert outcome.embedded == len(created)
    assert set(embeddings.rows) == {chunk.id for chunk in created}
    assert all(row["dimension"] == DIM for row in embeddings.rows.values())


async def test_embedding_is_skipped_for_chunks_that_already_have_vectors() -> None:
    service, chunks, embeddings, _ = build()
    service.chunk_version(source=make_source(), version=make_version())
    await service.embed_chunks(source=make_source(), version=make_version())

    second = await service.embed_chunks(source=make_source(), version=make_version())
    assert second.embedded == 0
    assert second.skipped == len(chunks.list_for_version("ver-1"))
    assert len(embeddings.rows) == len(chunks.list_for_version("ver-1"))


async def test_partial_progress_resumes_without_duplicating() -> None:
    service, chunks, embeddings, _ = build()
    service.chunk_version(source=make_source(), version=make_version())
    created = chunks.list_for_version("ver-1")

    # Pretend a previous run embedded only the first chunk.
    embeddings.store_embeddings(
        workspace_id=WS,
        document_version_id="ver-1",
        model_id="test/model",
        dimension=DIM,
        vectors=[(created[0].id, [0.1] * DIM)],
    )

    outcome = await service.embed_chunks(source=make_source(), version=make_version())
    assert outcome.embedded == len(created) - 1
    assert len(embeddings.rows) == len(created)


async def test_embedding_without_a_provider_is_not_configured() -> None:
    service, _, _, _ = build()
    service.chunk_version(source=make_source(), version=make_version())
    no_provider = IndexingService(
        sources=FakeSourceRepo(make_source()),
        chunks=FakeChunkStore(),
        embeddings=FakeEmbeddingStore(),
        extractions=FakeExtractions(),
        provider=None,
    )
    with pytest.raises(EmbeddingNotConfiguredError):
        await no_provider.embed_chunks(source=make_source(), version=make_version())


async def test_provider_failure_is_not_swallowed() -> None:
    service, _chunks, embeddings, _ = build(
        provider=FakeProvider(fail=EmbeddingError(message="boom"))
    )
    service.chunk_version(source=make_source(), version=make_version())
    with pytest.raises(EmbeddingError):
        await service.embed_chunks(source=make_source(), version=make_version())
    assert embeddings.rows == {}


# --- orchestration -------------------------------------------------------


async def test_successful_indexing_marks_the_source_ready() -> None:
    service, _, _, repo = build()
    outcome = await service.index_version(source=make_source(), version=make_version())

    assert outcome.source_status == "ready"
    assert repo.source.processing_status is ProcessingStatus.READY
    assert outcome.embedding is not None
    assert outcome.chunking is not None


async def test_embedding_failure_marks_failed_with_a_specific_code() -> None:
    service, _, _, repo = build(provider=FakeProvider(fail=EmbeddingError(message="provider down")))
    outcome = await service.index_version(source=make_source(), version=make_version())

    assert outcome.source_status == "failed"
    assert outcome.error_code == "embedding_failed"
    assert repo.source.processing_status is ProcessingStatus.FAILED
    assert repo.source.processing_error_code == "embedding_failed"


async def test_missing_provider_keeps_the_source_extracted_not_ready() -> None:
    source_repo = FakeSourceRepo(make_source())
    service = IndexingService(
        sources=source_repo,
        chunks=FakeChunkStore(),
        embeddings=FakeEmbeddingStore(),
        extractions=FakeExtractions(),
        provider=None,
        config=ChunkingConfig(target_chars=50, overlap_chars=0),
    )
    outcome = await service.index_version(source=make_source(), version=make_version())

    assert outcome.error_code == "embedding_not_configured"
    # Honest: chunks exist but the corpus is not searchable.
    assert outcome.source_status == "extracted"
    assert source_repo.statuses[-1] == "failed"


async def test_indexing_never_marks_ready_when_chunking_fails() -> None:
    service, _, _, repo = build(text=None)
    outcome = await service.index_version(source=make_source(), version=make_version())

    assert outcome.source_status == "failed"
    assert outcome.error_code == "chunking_failed"
    assert "ready" not in repo.statuses


async def test_reindex_discards_chunks_and_vectors_then_rebuilds() -> None:
    service, chunks, embeddings, _ = build()
    await service.index_version(source=make_source(), version=make_version())
    first_ids = {chunk.id for chunk in chunks.list_for_version("ver-1")}

    removed = service.reindex_version(source=make_source(), version=make_version())
    assert removed == len(first_ids)
    assert chunks.list_for_version("ver-1") == []
    assert embeddings.rows == {}

    await service.index_version(source=make_source(), version=make_version())
    second_ids = {chunk.id for chunk in chunks.list_for_version("ver-1")}
    assert second_ids.isdisjoint(first_ids)


async def test_reindex_does_not_touch_other_versions() -> None:
    chunks = FakeChunkStore()
    embeddings = FakeEmbeddingStore()
    service, _, _, _ = build(chunks=chunks, embeddings=embeddings)

    service.chunk_version(source=make_source(), version=make_version())
    other_version = replace(make_version(), id="ver-2", version_number=2)
    chunks.create_many(
        workspace_id=WS,
        source_id="src-1",
        document_version_id=other_version.id,
        chunks=[
            ChunkDraft(
                chunk_index=0,
                content="other",
                content_hash="b" * 64,
                source_location=__import__(
                    "app.domain.knowledge", fromlist=["SourceLocation"]
                ).SourceLocation(0, 5),
            )
        ],
        chunking_method="paragraph-window",
        chunking_version=1,
        chunking_config=ChunkingConfig().to_json(),
    )

    service.reindex_version(source=make_source(), version=make_version())
    assert len(chunks.list_for_version("ver-1")) == 0
    assert len(chunks.list_for_version("ver-2")) == 1
