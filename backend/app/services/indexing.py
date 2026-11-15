"""Chunking and indexing service (Phase 2C).

Two operations, each idempotent:

``chunk_version``   split a version's extracted text into chunks, recording the
                    chunking configuration. If the version already has chunks
                    produced by the *same* configuration, it does nothing.
``embed_chunks``    embed every chunk that has no vector yet, storing the model
                    id and dimension per row.

`index_source` runs both and only then marks the source `ready`. A partial
failure leaves the source failed with a specific code, and re-running resumes
from wherever it stopped because both steps skip completed work.

Invariants
----------
* chunks are never rewritten in place: a different configuration produces a
  new set only after the old set is explicitly discarded by a re-index;
* an embedding row is unique per chunk (primary key), so a retry cannot create a
  duplicate vector;
* the dimension is validated by the provider *and* by the database column, so a
  model change cannot silently mix vector sizes;
* `ready` is set only when every chunk has an `embedded` status.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.errors import MnemosError
from app.domain.knowledge import (
    Chunk,
    DocumentVersion,
    EmbeddingStatus,
    ExtractionStatus,
    ProcessingStatus,
    Source,
)
from app.infrastructure.embeddings import (
    EmbeddingBatch,
    EmbeddingError,
    EmbeddingNotConfiguredError,
    EmbeddingProvider,
)
from app.repositories.knowledge_repositories import sha256_hex
from app.services.chunking import ChunkingConfig, PageRange, chunk_text

logger = logging.getLogger("mnemos.indexing")


class ChunkStore(Protocol):
    """The chunk-side persistence the indexer needs."""

    def create_many(
        self,
        *,
        workspace_id: str,
        source_id: str,
        document_version_id: str,
        chunks: Sequence[Any],
        chunking_method: str,
        chunking_version: int,
        chunking_config: dict[str, Any] | None = None,
    ) -> list[Chunk]: ...

    def list_for_version(self, version_id: str) -> list[Chunk]: ...

    def delete_for_version(self, version_id: str) -> int: ...


class EmbeddingStore(Protocol):
    """Vector persistence, kept separate from chunk persistence."""

    def list_embedded_chunk_ids(self, version_id: str) -> set[str]: ...

    def store_embeddings(
        self,
        *,
        workspace_id: str,
        document_version_id: str,
        model_id: str,
        dimension: int,
        vectors: Sequence[tuple[str, list[float]]],
    ) -> int: ...

    def delete_for_version(self, version_id: str) -> int: ...


class ExtractionReader(Protocol):
    """Read a version's extracted text and page map."""

    def read_extraction(
        self, version_id: str
    ) -> tuple[str, list[PageRange], dict[str, Any]] | None: ...


class IndexedSourceRepository(Protocol):
    """The source/version operations the indexer needs."""

    def get(self, source_id: str) -> Source | None: ...

    def get_version(self, version_id: str) -> DocumentVersion | None: ...

    def update_processing(
        self,
        source_id: str,
        *,
        status: ProcessingStatus,
        error_code: str | None = None,
        error_detail: str | None = None,
        increment_attempts: bool = False,
    ) -> Source | None: ...


@dataclass(frozen=True, slots=True)
class ChunkingOutcome:
    """What chunking did (or skipped)."""

    chunk_count: int
    created: bool
    config: dict[str, Any]

    @property
    def skipped(self) -> bool:
        return not self.created


@dataclass(frozen=True, slots=True)
class EmbeddingOutcome:
    """What embedding did."""

    embedded: int
    skipped: int
    model_id: str
    dimension: int
    prompt_tokens: int | None = None
    latency_ms: int = 0

    @property
    def did_work(self) -> bool:
        return self.embedded > 0


@dataclass(frozen=True, slots=True)
class IndexOutcome:
    """The result of indexing one version."""

    source_status: str
    chunking: ChunkingOutcome | None
    embedding: EmbeddingOutcome | None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _tokens_estimate(text: str) -> int:
    """Rough token estimate for metadata only; never used for billing."""
    return max(1, len(text) // 4)


class IndexingService:
    """Deterministic chunking plus embedding, with resume-on-retry."""

    def __init__(
        self,
        *,
        sources: IndexedSourceRepository,
        chunks: ChunkStore,
        embeddings: EmbeddingStore,
        extractions: ExtractionReader,
        provider: EmbeddingProvider | None,
        config: ChunkingConfig | None = None,
    ) -> None:
        self._sources = sources
        self._chunks = chunks
        self._embeddings = embeddings
        self._extractions = extractions
        self._provider = provider
        self._config = config or ChunkingConfig()

    # --- public API ------------------------------------------------------
    def chunk_version(self, *, source: Source, version: DocumentVersion) -> ChunkingOutcome:
        """Create chunks for a version, unless identical work already exists."""
        existing = self._chunks.list_for_version(version.id)
        if existing and self._matches_config(existing):
            logger.info("Chunking skipped: %d chunks already match the config", len(existing))
            return ChunkingOutcome(
                chunk_count=len(existing), created=False, config=self._config.to_json()
            )

        if existing:
            # A different configuration is present. Re-indexing is an explicit
            # action; the caller must opt in by clearing first.
            raise MnemosError(
                message=(
                    "This version already has chunks from a different chunking "
                    "configuration. Re-index it explicitly rather than mixing "
                    "chunk shapes in one version."
                )
            )

        text, pages, _ = self._read_extraction(version.id)
        drafts = chunk_text(text, pages=pages, config=self._config)
        if not drafts:
            raise MnemosError(message="The extracted text produced no chunks.")

        created = self._chunks.create_many(
            workspace_id=source.workspace_id,
            source_id=source.id,
            document_version_id=version.id,
            chunks=drafts,
            chunking_method=self._config.method,
            chunking_version=self._config.version,
            chunking_config=self._config.to_json(),
        )
        logger.info("Chunked version %s into %d chunks", version.version_number, len(created))
        return ChunkingOutcome(
            chunk_count=len(created), created=True, config=self._config.to_json()
        )

    async def embed_chunks(self, *, source: Source, version: DocumentVersion) -> EmbeddingOutcome:
        """Embed every chunk of a version that has no vector yet."""
        if self._provider is None:
            raise EmbeddingNotConfiguredError()

        chunks = self._chunks.list_for_version(version.id)
        if not chunks:
            raise MnemosError(message="There are no chunks to embed for this version.")

        already = self._embeddings.list_embedded_chunk_ids(version.id)
        pending = [chunk for chunk in chunks if chunk.id not in already]
        if not pending:
            return EmbeddingOutcome(
                embedded=0,
                skipped=len(chunks),
                model_id=self._provider.model_id,
                dimension=self._provider.dimension,
            )

        batch: EmbeddingBatch = await self._provider.embed([chunk.content for chunk in pending])
        if len(batch.vectors) != len(pending):
            raise EmbeddingError(
                message="The embedding provider returned a different number of vectors than inputs."
            )

        pairs = [
            (chunk.id, vector.values) for chunk, vector in zip(pending, batch.vectors, strict=True)
        ]
        stored = self._embeddings.store_embeddings(
            workspace_id=source.workspace_id,
            document_version_id=version.id,
            model_id=batch.model,
            dimension=self._provider.dimension,
            vectors=pairs,
        )
        logger.info(
            "Embedded %d chunks (model=%s, dim=%d, tokens=%s)",
            stored,
            batch.model,
            self._provider.dimension,
            batch.prompt_tokens,
        )
        return EmbeddingOutcome(
            embedded=stored,
            skipped=len(already),
            model_id=batch.model,
            dimension=self._provider.dimension,
            prompt_tokens=batch.prompt_tokens,
            latency_ms=batch.latency_ms,
        )

    async def index_version(self, *, source: Source, version: DocumentVersion) -> IndexOutcome:
        """Chunk then embed, and mark the source ready only on full success."""
        try:
            chunking = self.chunk_version(source=source, version=version)
        except MnemosError as exc:
            self._fail(source.id, "chunking_failed", exc.message)
            return IndexOutcome(
                source_status=ProcessingStatus.FAILED.value,
                chunking=None,
                embedding=None,
                error_code="chunking_failed",
                error_message=exc.message,
            )

        self._sources.update_processing(source.id, status=ProcessingStatus.CHUNKING)

        try:
            embedding = await self.embed_chunks(source=source, version=version)
        except EmbeddingNotConfiguredError as exc:
            self._fail(source.id, "embedding_not_configured", exc.message)
            return IndexOutcome(
                source_status=ProcessingStatus.EXTRACTED.value,
                chunking=chunking,
                embedding=None,
                error_code="embedding_not_configured",
                error_message=exc.message,
            )
        except (EmbeddingError, MnemosError) as exc:
            self._fail(source.id, getattr(exc, "code", "embedding_failed"), exc.message)
            return IndexOutcome(
                source_status=ProcessingStatus.FAILED.value,
                chunking=chunking,
                embedding=None,
                error_code=getattr(exc, "code", "embedding_failed"),
                error_message=exc.message,
            )

        self._sources.update_processing(source.id, status=ProcessingStatus.READY)
        return IndexOutcome(
            source_status=ProcessingStatus.READY.value,
            chunking=chunking,
            embedding=embedding,
            metadata={"chunking": chunking.config},
        )

    def reindex_version(self, *, source: Source, version: DocumentVersion) -> int:
        """Discard a version's chunks and embeddings so they can be rebuilt.

        Destructive by design and therefore explicit: it is only called from an
        endpoint a user invokes. Returns the number of chunks removed.
        """
        self._embeddings.delete_for_version(version.id)
        removed = self._chunks.delete_for_version(version.id)
        logger.info("Re-index prepared: removed %d chunks for version %s", removed, version.id)
        return removed

    # --- internals -------------------------------------------------------
    def _matches_config(self, chunks: Sequence[Chunk]) -> bool:
        """True only when the stored chunks came from this exact configuration.

        Method and version alone are not enough: the version is a promise that
        parameters changed with it, and a caller can pass a different
        configuration without bumping it. Comparing the recorded parameters in
        `metadata` closes that gap, so two different chunk shapes can never be
        mixed in one version.
        """
        expected = {
            "method": self._config.method,
            "chunking_version": self._config.version,
            "target_chars": self._config.target_chars,
            "overlap_chars": self._config.overlap_chars,
        }
        for chunk in chunks:
            if chunk.chunking_method != self._config.method:
                return False
            recorded = chunk.metadata.get("chunking_config") if chunk.metadata else None
            if isinstance(recorded, dict):
                if {key: recorded.get(key) for key in expected} != expected:
                    return False
            elif self._config.version != chunk.chunking_version:
                # Legacy/absent config metadata: fall back to the version.
                return False
        return True

    def _read_extraction(self, version_id: str) -> tuple[str, list[PageRange], dict[str, Any]]:
        extracted = self._extractions.read_extraction(version_id)
        if extracted is None:
            raise MnemosError(
                message="This version has no extracted text. Extraction must succeed first."
            )
        return extracted

    def _fail(self, source_id: str, code: str, detail: str) -> None:
        self._sources.update_processing(
            source_id,
            status=ProcessingStatus.FAILED,
            error_code=code[:64],
            error_detail=detail[:500],
            increment_attempts=True,
        )


def chunk_hash(text: str) -> str:
    """Re-exported for callers that need the same hash the repository uses."""
    return sha256_hex(text)


__all__ = [
    "ChunkingOutcome",
    "EmbeddingOutcome",
    "EmbeddingStatus",
    "ExtractionStatus",
    "IndexOutcome",
    "IndexingService",
    "_tokens_estimate",
    "chunk_hash",
]
