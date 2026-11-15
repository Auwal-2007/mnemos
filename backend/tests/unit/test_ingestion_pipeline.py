"""Ingestion pipeline tests (Phase 2B).

The repository and storage layers are in-memory fakes, so the pipeline's real
behaviour — ordering, status transitions, cleanup on failure, idempotency — is
what is under test. Database constraints are covered by
`scripts/verify-migrations.py`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.errors import ForbiddenError, NotFoundError
from app.domain.knowledge import (
    DocumentVersion,
    ExtractionStatus,
    ProcessingStatus,
    Source,
    SourceKind,
)
from app.domain.models import Workspace
from app.services.ingestion.pipeline import IngestionPipeline, IngestionRejected

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
USER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
WS = "33333333-3333-4333-8333-333333333333"


class FakeStorage:
    """In-memory object store that records every call."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploads: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.fail_upload = False

    def upload(self, path: str, content: bytes, mime_type: str) -> None:
        if self.fail_upload:
            from app.infrastructure.storage import StorageError

            raise StorageError(message="Upload failed.")
        self.objects[path] = content
        self.uploads.append((path, mime_type))

    def download(self, path: str) -> bytes:
        return self.objects[path]

    def delete(self, path: str) -> None:
        self.deleted.append(path)
        self.objects.pop(path, None)

    def signed_url(self, path: str, expires_in: int) -> str:
        return f"https://storage.test/{path}?expires={expires_in}"


class FakeSourceRepository:
    """Minimal in-memory implementation of the source/version repository."""

    def __init__(self) -> None:
        self.sources: dict[str, Source] = {}
        self.versions: dict[str, DocumentVersion] = {}
        self.status_history: list[tuple[str, str]] = []
        self.extraction_store: list[dict[str, Any]] = []
        self.fail_create_version = False
        self._counter = 0

    def _id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter:04d}"

    def list_for_workspace(
        self, workspace_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Source]:
        return [s for s in self.sources.values() if s.workspace_id == workspace_id]

    def get(self, source_id: str) -> Source | None:
        return self.sources.get(source_id)

    def find_by_idempotency_key(self, workspace_id: str, key: str) -> Source | None:
        del workspace_id, key
        return None

    def create(self, **kwargs: Any) -> Source:
        source = Source(
            id=self._id("src"),
            workspace_id=kwargs["workspace_id"],
            owner_id=kwargs["owner_id"],
            kind=kwargs["kind"],
            title=kwargs["title"],
            original_filename=kwargs["original_filename"],
            mime_type=kwargs["mime_type"],
            size_bytes=kwargs["size_bytes"],
            content_hash=kwargs["content_hash"],
            storage_bucket="sources",
            storage_path=kwargs["storage_path"],
            processing_status=ProcessingStatus.PENDING,
            processing_error_code=None,
            processing_error_detail=None,
            processing_attempts=0,
            metadata=kwargs.get("metadata") or {},
            submitted_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        self.sources[source.id] = source
        return source

    def update_processing(
        self,
        source_id: str,
        *,
        status: ProcessingStatus,
        error_code: str | None = None,
        error_detail: str | None = None,
        increment_attempts: bool = False,
    ) -> Source | None:
        source = self.sources.get(source_id)
        if source is None:
            return None
        updated = replace(
            source,
            processing_status=status,
            processing_error_code=error_code,
            processing_error_detail=error_detail,
            processing_attempts=source.processing_attempts + (1 if increment_attempts else 0),
        )
        self.sources[source_id] = updated
        self.status_history.append((source_id, status.value))
        return updated

    def delete(self, source_id: str) -> bool:
        if source_id not in self.sources:
            return False
        del self.sources[source_id]
        for version_id in [vid for vid, v in self.versions.items() if v.source_id == source_id]:
            del self.versions[version_id]
        return True

    def create_version(self, **kwargs: Any) -> DocumentVersion:
        if self.fail_create_version:
            raise RuntimeError("database unavailable")
        existing = [v for v in self.versions.values() if v.source_id == kwargs["source_id"]]
        version = DocumentVersion(
            id=self._id("ver"),
            workspace_id=kwargs["workspace_id"],
            source_id=kwargs["source_id"],
            version_number=len(existing) + 1,
            content_hash=kwargs["content_hash"],
            size_bytes=kwargs["size_bytes"],
            mime_type=kwargs["mime_type"],
            storage_bucket="sources",
            storage_path=kwargs["storage_path"],
            extraction_status=ExtractionStatus.PENDING,
            extraction_method=None,
            extraction_error_code=None,
            is_current=True,
            submitted_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        self.versions[version.id] = version
        return version

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
        version = self.versions.get(version_id)
        assert version is not None
        self.versions[version_id] = replace(version, is_current=False)

    def update_version_extraction(
        self,
        version_id: str,
        *,
        status: ExtractionStatus,
        method: str | None = None,
        error_code: str | None = None,
    ) -> DocumentVersion | None:
        version = self.versions.get(version_id)
        if version is None:
            return None
        updated = replace(
            version,
            extraction_status=status,
            extraction_method=method,
            extraction_error_code=error_code,
        )
        self.versions[version_id] = updated
        return updated

    def store_extraction(self, **kwargs: Any) -> None:
        self.extraction_store.append(kwargs)


class FakeChunkRepository:
    def create_many(self, **kwargs: Any) -> list[Any]:
        return []

    def list_for_version(self, version_id: str) -> list[Any]:
        return []

    def count_for_version(self, version_id: str) -> int:
        return 0

    def delete_for_version(self, version_id: str) -> int:
        return 0

    def create_provenance(self, **kwargs: Any) -> Any:
        raise NotImplementedError

    def list_provenance_for_version(self, version_id: str) -> list[Any]:
        return []

    def resolve_for_chunk(self, chunk_id: str) -> Any:
        return None


class FakeWorkspaceService:
    """Authorization stub: only USER may contribute to WS."""

    def __init__(self, allowed: dict[str, set[str]] | None = None) -> None:
        self.allowed = allowed if allowed is not None else {WS: {USER}}

    def get_workspace(self, workspace_id: str, user_id: str) -> Workspace:
        if workspace_id not in self.allowed or user_id not in self.allowed[workspace_id]:
            raise ForbiddenError(message="You do not have access to this workspace.")
        return Workspace(
            id=workspace_id,
            owner_id=user_id,
            name="Personal",
            slug="personal",
            description=None,
            created_at=NOW,
            updated_at=NOW,
        )


def build_pipeline(
    sources: FakeSourceRepository | None = None,
    storage: FakeStorage | None = None,
    workspaces: FakeWorkspaceService | None = None,
) -> tuple[IngestionPipeline, FakeSourceRepository, FakeStorage]:
    source_repo = sources or FakeSourceRepository()
    storage = storage or FakeStorage()
    pipeline = IngestionPipeline(
        sources=source_repo,
        chunks=FakeChunkRepository(),
        storage=storage,
        workspaces=workspaces or FakeWorkspaceService(),  # type: ignore[arg-type]
    )
    return pipeline, source_repo, storage


# --- documents -----------------------------------------------------------


def test_text_document_is_stored_extracted_and_marked_extracted() -> None:
    pipeline, _sources, storage = build_pipeline()
    result = pipeline.ingest_document(
        user_id=USER,
        workspace_id=WS,
        raw=b"Hello world.",
        filename="hello.txt",
        declared_mime="text/plain",
        title=None,
    )
    assert result.source.kind is SourceKind.DOCUMENT
    assert result.source.processing_status is ProcessingStatus.EXTRACTED
    assert result.extraction.status == "extracted"
    assert result.extraction.method == "plain-text"
    assert result.extraction.char_count == 12
    assert result.duplicate_of_existing is False
    assert result.version_number == 1

    # Original bytes preserved and never re-encoded.
    assert list(storage.objects.values()) == [b"Hello world."]
    path = next(iter(storage.objects))
    assert path.startswith(f"{USER}/")


def test_status_progression_is_ordered_and_accurate() -> None:
    pipeline, sources, _ = build_pipeline()
    result = pipeline.ingest_document(
        user_id=USER,
        workspace_id=WS,
        raw=b"text",
        filename="a.txt",
        declared_mime="text/plain",
        title=None,
    )
    observed = [
        status for source_id, status in sources.status_history if source_id == result.source.id
    ]
    assert observed == ["validating", "extracting", "extracted"]


def test_markdown_document_extracts_with_method() -> None:
    pipeline, _, _ = build_pipeline()
    result = pipeline.ingest_document(
        user_id=USER,
        workspace_id=WS,
        raw=b"# Title\n\nBody.",
        filename="notes.md",
        declared_mime="text/markdown",
        title=None,
    )
    assert result.extraction.method == "markdown"
    assert result.source.mime_type == "text/markdown"


def test_empty_file_is_rejected_before_storage() -> None:
    pipeline, sources, storage = build_pipeline()
    with pytest.raises(IngestionRejected) as error:
        pipeline.ingest_document(
            user_id=USER,
            workspace_id=WS,
            raw=b"",
            filename="empty.txt",
            declared_mime="text/plain",
            title=None,
        )
    assert error.value.details == {"reason": "empty_file"}
    assert storage.objects == {}
    assert sources.sources == {}


def test_forged_mime_is_rejected_with_a_reason_code() -> None:
    pipeline, _, storage = build_pipeline()
    with pytest.raises(IngestionRejected) as error:
        pipeline.ingest_document(
            user_id=USER,
            workspace_id=WS,
            raw=b"plain text",
            filename="fake.pdf",
            declared_mime="application/pdf",
            title=None,
        )
    assert error.value.details == {"reason": "type_mismatch"}
    assert storage.objects == {}


def test_non_contributor_cannot_ingest() -> None:
    pipeline, _, storage = build_pipeline()
    with pytest.raises(ForbiddenError):
        pipeline.ingest_document(
            user_id=OTHER,
            workspace_id=WS,
            raw=b"text",
            filename="a.txt",
            declared_mime="text/plain",
            title=None,
        )
    assert storage.objects == {}


def test_extraction_failure_keeps_original_and_marks_failed() -> None:
    """A PDF with no text layer must not lose the file or claim success."""
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)

    pipeline, sources, storage = build_pipeline()
    result = pipeline.ingest_document(
        user_id=USER,
        workspace_id=WS,
        raw=buffer.getvalue(),
        filename="scan.pdf",
        declared_mime="application/pdf",
        title=None,
    )
    assert result.source.processing_status is ProcessingStatus.FAILED
    assert result.extraction.status == "failed"
    assert result.extraction.error_code == "no_text_layer"
    assert result.extraction.error_message
    # The original is preserved even though extraction failed.
    assert len(storage.objects) == 1
    assert sources.sources[result.source.id].processing_attempts == 1


def test_storage_failure_creates_no_rows() -> None:
    storage = FakeStorage()
    storage.fail_upload = True
    pipeline, sources, _ = build_pipeline(storage=storage)

    from app.infrastructure.storage import StorageError

    with pytest.raises(StorageError):
        pipeline.ingest_document(
            user_id=USER,
            workspace_id=WS,
            raw=b"text",
            filename="a.txt",
            declared_mime="text/plain",
            title=None,
        )
    assert sources.sources == {}
    assert sources.versions == {}


def test_version_creation_failure_cleans_up_the_stored_object() -> None:
    sources = FakeSourceRepository()
    sources.fail_create_version = True
    pipeline, sources, storage = build_pipeline(sources=sources)

    with pytest.raises(RuntimeError):
        pipeline.ingest_document(
            user_id=USER,
            workspace_id=WS,
            raw=b"text",
            filename="a.txt",
            declared_mime="text/plain",
            title=None,
        )
    # No orphaned object, and the source is marked failed rather than pending.
    assert storage.objects == {}
    assert len(storage.deleted) == 1
    (source,) = sources.sources.values()
    assert source.processing_status is ProcessingStatus.FAILED


# --- notes ---------------------------------------------------------------


def test_note_is_a_versioned_source_not_a_string() -> None:
    pipeline, sources, storage = build_pipeline()
    result = pipeline.ingest_note(
        user_id=USER, workspace_id=WS, content="A thought.\n", title="Thought"
    )
    assert result.source.kind is SourceKind.NOTE
    assert result.source.original_filename is None
    assert result.version_number == 1
    assert result.extraction.char_count == len(b"A thought.")
    assert len(sources.versions) == 1
    # Notes are stored through the same private path as files.
    assert next(iter(storage.objects)).startswith(f"{USER}/")


def test_empty_note_rejected() -> None:
    pipeline, sources, _ = build_pipeline()
    with pytest.raises(IngestionRejected) as error:
        pipeline.ingest_note(user_id=USER, workspace_id=WS, content="  ", title="N")
    assert error.value.details == {"reason": "empty_file"}
    assert sources.sources == {}


def test_note_by_non_contributor_rejected() -> None:
    pipeline, _, _ = build_pipeline()
    with pytest.raises(ForbiddenError):
        pipeline.ingest_note(user_id=OTHER, workspace_id=WS, content="x", title="N")


# --- versions ------------------------------------------------------------


def test_new_version_retires_previous_version_and_preserves_it() -> None:
    pipeline, sources, _ = build_pipeline()
    first = pipeline.ingest_document(
        user_id=USER,
        workspace_id=WS,
        raw=b"v1 text",
        filename="a.txt",
        declared_mime="text/plain",
        title=None,
    )
    second = pipeline.add_version(
        user_id=USER,
        source_id=first.source.id,
        raw=b"v2 text",
        filename="a.txt",
        declared_mime="text/plain",
    )
    assert second.version_number == 2
    versions = {v.version_number: v for v in sources.list_versions(first.source.id)}
    assert versions[1].is_current is False
    assert versions[2].is_current is True
    # The old version still exists with its own content hash.
    assert versions[1].content_hash != versions[2].content_hash


def test_new_note_version_replaces_content_not_history() -> None:
    pipeline, sources, _ = build_pipeline()
    first = pipeline.ingest_note(user_id=USER, workspace_id=WS, content="v1", title="Note")
    second = pipeline.add_version(user_id=USER, source_id=first.source.id, content="v2")
    assert second.version_number == 2
    assert len(sources.list_versions(first.source.id)) == 2


def test_version_on_unknown_source_is_not_found() -> None:
    pipeline, _, _ = build_pipeline()
    with pytest.raises(NotFoundError):
        pipeline.add_version(user_id=USER, source_id="missing", content="x")


def test_version_requires_a_payload_matching_the_source_kind() -> None:
    pipeline, _, _ = build_pipeline()
    note = pipeline.ingest_note(user_id=USER, workspace_id=WS, content="x", title="N")
    with pytest.raises(IngestionRejected):
        pipeline.add_version(user_id=USER, source_id=note.source.id)


# --- deletion ------------------------------------------------------------


def test_delete_removes_storage_objects_and_rows() -> None:
    pipeline, sources, storage = build_pipeline()
    created = pipeline.ingest_document(
        user_id=USER,
        workspace_id=WS,
        raw=b"text",
        filename="a.txt",
        declared_mime="text/plain",
        title=None,
    )
    pipeline.add_version(
        user_id=USER,
        source_id=created.source.id,
        raw=b"text2",
        filename="a.txt",
        declared_mime="text/plain",
    )
    assert len(storage.objects) == 2

    pipeline.delete_source(user_id=USER, source_id=created.source.id)
    assert storage.objects == {}
    assert sources.sources == {}
    assert sources.versions == {}


def test_delete_by_non_owner_rejected() -> None:
    workspaces = FakeWorkspaceService({WS: {USER, OTHER}})
    pipeline, sources, storage = build_pipeline(workspaces=workspaces)
    created = pipeline.ingest_document(
        user_id=USER,
        workspace_id=WS,
        raw=b"text",
        filename="a.txt",
        declared_mime="text/plain",
        title=None,
    )
    with pytest.raises(ForbiddenError):
        pipeline.delete_source(user_id=OTHER, source_id=created.source.id)
    assert sources.sources != {}
    assert storage.objects != {}


def test_delete_unknown_source_is_not_found() -> None:
    pipeline, _, _ = build_pipeline()
    with pytest.raises(NotFoundError):
        pipeline.delete_source(user_id=USER, source_id="missing")


def test_download_url_is_scoped_and_expiring() -> None:
    pipeline, _, _ = build_pipeline()
    created = pipeline.ingest_document(
        user_id=USER,
        workspace_id=WS,
        raw=b"text",
        filename="a.txt",
        declared_mime="text/plain",
        title=None,
    )
    url = pipeline.download_url(user_id=USER, source_id=created.source.id, expires_in=60)
    assert url.startswith(f"https://storage.test/{USER}/")
    assert "expires=60" in url
