"""The ingestion pipeline (Phase 2B).

Order of operations is deliberate and documented in
`docs/INGESTION_PIPELINE.md`:

    1. authorize the caller against the workspace
    2. validate the payload (type, size, encoding, structure)
    3. compute the content hash *before* anything is stored
    4. write the original to private storage at a server-chosen path
    5. create the source row, then the version row
    6. extract text; record the method, offsets and page map
    7. update the version's extraction status and the source's status
    8. report an accurate result to the user

Failure handling follows the same order in reverse: a failure at step 6 leaves
the original and its metadata intact with an explicit `failed` status, never a
half-deleted row and never a silent "ready".

Idempotency: a client may send an `Idempotency-Key`. A repeat with the same key
in the same workspace returns the existing source instead of creating another,
so a retried request cannot duplicate a document.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.errors import ForbiddenError, MnemosError
from app.domain.knowledge import (
    ExtractionStatus,
    ProcessingStatus,
    Source,
    SourceKind,
)
from app.infrastructure.storage import PrivateStorage, StorageError
from app.repositories.base import ChunkRepository, SourceRepository
from app.repositories.knowledge_repositories import SupabaseSourceRepository
from app.services.ingestion.extraction import ExtractionError, ExtractionResult, extract
from app.services.ingestion.validation import (
    DetectedFormat,
    UploadRejected,
    ValidatedUpload,
    storage_path_for,
    validate_note,
    validate_upload,
)
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger("mnemos.ingestion")


class IngestionRejected(MnemosError):
    """A rejected submission, with a code the UI can act on."""

    status_code = 422
    code = "ingestion_rejected"


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    """What happened during extraction, for the API response."""

    status: str
    method: str | None
    char_count: int
    page_count: int
    segment_count: int
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """The accurate outcome of a submission."""

    source: Source
    version_id: str | None
    version_number: int | None
    extraction: ExtractionOutcome
    duplicate_of_existing: bool


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class IngestionPipeline:
    """Coordinator for one ingestion run."""

    def __init__(
        self,
        *,
        sources: SourceRepository,
        chunks: ChunkRepository,
        storage: PrivateStorage,
        workspaces: WorkspaceService,
    ) -> None:
        self._sources = sources
        self._chunks = chunks
        self._storage = storage
        self._workspaces = workspaces

    # --- public entry points --------------------------------------------
    def ingest_document(
        self,
        *,
        user_id: str,
        workspace_id: str,
        raw: bytes,
        filename: str | None,
        declared_mime: str | None,
        title: str | None,
        idempotency_key: str | None = None,
    ) -> IngestionResult:
        """Ingest an uploaded file."""
        duplicate = self._existing(idempotency_key, workspace_id)
        if duplicate is not None:
            return IngestionResult(
                source=duplicate,
                version_id=None,
                version_number=None,
                extraction=ExtractionOutcome(
                    status=duplicate.processing_status.value,
                    method=None,
                    char_count=0,
                    page_count=0,
                    segment_count=0,
                ),
                duplicate_of_existing=True,
            )

        self._require_contributor(workspace_id, user_id)

        try:
            validated = validate_upload(
                raw=raw, filename=filename, declared_mime=declared_mime, title=title
            )
        except UploadRejected as exc:
            raise IngestionRejected(message=exc.message, details={"reason": exc.code}) from exc

        return self._store_and_extract(
            user_id=user_id,
            workspace_id=workspace_id,
            kind=SourceKind.DOCUMENT,
            payload=validated.content,
            validated=validated,
            idempotency_key=idempotency_key,
        )

    def ingest_note(
        self,
        *,
        user_id: str,
        workspace_id: str,
        content: str,
        title: str,
        idempotency_key: str | None = None,
    ) -> IngestionResult:
        """Ingest a typed note as a versioned source."""
        duplicate = self._existing(idempotency_key, workspace_id)
        if duplicate is not None:
            return IngestionResult(
                source=duplicate,
                version_id=None,
                version_number=None,
                extraction=ExtractionOutcome(
                    status=duplicate.processing_status.value,
                    method=None,
                    char_count=0,
                    page_count=0,
                    segment_count=0,
                ),
                duplicate_of_existing=True,
            )

        self._require_contributor(workspace_id, user_id)

        try:
            normalized, size_bytes = validate_note(content=content, title=title)
        except UploadRejected as exc:
            raise IngestionRejected(message=exc.message, details={"reason": exc.code}) from exc

        raw = normalized.encode("utf-8")
        validated = ValidatedUpload(
            format=DetectedFormat.TEXT,
            spec=self._text_spec(),
            mime_type="text/plain",
            size_bytes=size_bytes,
            filename="note.txt",
            title=title.strip(),
            content=raw,
        )
        return self._store_and_extract(
            user_id=user_id,
            workspace_id=workspace_id,
            kind=SourceKind.NOTE,
            payload=raw,
            validated=validated,
            idempotency_key=idempotency_key,
        )

    def add_version(
        self,
        *,
        user_id: str,
        source_id: str,
        raw: bytes | None = None,
        content: str | None = None,
        filename: str | None = None,
        declared_mime: str | None = None,
        idempotency_key: str | None = None,
    ) -> IngestionResult:
        """Submit a new version of an existing source.

        The previous version is retired (never deleted), and its chunks and
        provenance remain resolvable for historical questions.
        """
        source = self._sources.get(source_id)
        if source is None:
            # RLS makes another user's source indistinguishable from missing.
            from app.core.errors import NotFoundError

            raise NotFoundError(message="Source not found.")
        self._require_contributor(source.workspace_id, user_id)

        if source.kind is SourceKind.NOTE:
            if content is None:
                raise IngestionRejected(message="A new note version requires note content.")
            normalized, _ = validate_note(content=content, title=source.title)
            payload = normalized.encode("utf-8")
            validated = ValidatedUpload(
                format=DetectedFormat.TEXT,
                spec=self._text_spec(),
                mime_type="text/plain",
                size_bytes=len(payload),
                filename="note.txt",
                title=source.title,
                content=payload,
            )
        else:
            if raw is None:
                raise IngestionRejected(message="A new document version requires a file.")
            try:
                validated = validate_upload(
                    raw=raw,
                    filename=filename or source.original_filename,
                    declared_mime=declared_mime,
                    title=source.title,
                )
            except UploadRejected as exc:
                raise IngestionRejected(message=exc.message, details={"reason": exc.code}) from exc
            payload = validated.content

        return self._store_and_extract(
            user_id=user_id,
            workspace_id=source.workspace_id,
            kind=source.kind,
            payload=payload,
            validated=validated,
            idempotency_key=idempotency_key,
            existing_source=source,
        )

    def delete_source(self, *, user_id: str, source_id: str) -> None:
        """Delete a source, its storage object and every derived row."""
        source = self._sources.get(source_id)
        if source is None:
            from app.core.errors import NotFoundError

            raise NotFoundError(message="Source not found.")
        if source.owner_id != user_id:
            raise ForbiddenError(message="Only the user who submitted this source may delete it.")

        # Remove the bytes first: if this fails we have not yet destroyed the
        # only pointer to an orphaned object, and the database is untouched.
        self._storage.delete(source.storage_path)
        for version in self._sources.list_versions(source_id):
            self._storage.delete(version.storage_path)

        if not self._sources.delete(source_id):
            from app.core.errors import NotFoundError

            raise NotFoundError(message="Source not found.")
        logger.info(
            "Source deleted (kind=%s, versions=%d)",
            source.kind.value,
            len(self._sources.list_versions(source_id)),
        )

    def download_url(self, *, user_id: str, source_id: str, expires_in: int = 300) -> str:
        """Mint a short-lived download URL for the source's current original."""
        del user_id  # RLS already scoped the lookup to the caller
        source = self._sources.get(source_id)
        if source is None:
            from app.core.errors import NotFoundError

            raise NotFoundError(message="Source not found.")
        current = self._sources.current_version(source_id)
        path = current.storage_path if current else source.storage_path
        return self._storage.signed_url(path, expires_in)

    # --- internals -------------------------------------------------------
    @staticmethod
    def _text_spec() -> Any:
        from app.services.ingestion.validation import FORMAT_SPECS

        return FORMAT_SPECS[DetectedFormat.TEXT]

    def _existing(self, idempotency_key: str | None, workspace_id: str) -> Source | None:
        if not idempotency_key:
            return None
        return self._sources.find_by_idempotency_key(workspace_id, idempotency_key)

    def _require_contributor(self, workspace_id: str, user_id: str) -> None:
        """Check membership before any bytes are stored."""
        workspace = self._workspaces.get_workspace(workspace_id, user_id)
        del workspace

    def _store_and_extract(
        self,
        *,
        user_id: str,
        workspace_id: str,
        kind: SourceKind,
        payload: bytes,
        validated: ValidatedUpload,
        idempotency_key: str | None,
        existing_source: Source | None = None,
    ) -> IngestionResult:
        content_hash = _sha256(payload)
        object_id = str(uuid.uuid4())
        path = storage_path_for(user_id, object_id, validated.spec.extension)

        # 4. store the original before any database row exists, so a database
        #    failure leaves an unreferenced object rather than a row that
        #    points at nothing.
        try:
            self._storage.upload(path, payload, validated.mime_type)
        except StorageError:
            raise

        if existing_source is None:
            source = self._create_source(
                user_id=user_id,
                workspace_id=workspace_id,
                kind=kind,
                validated=validated,
                content_hash=content_hash,
                path=path,
                idempotency_key=idempotency_key,
            )
        else:
            source = existing_source
            self._retire_current(source.id)

        try:
            version = self._sources.create_version(
                workspace_id=workspace_id,
                source_id=source.id,
                content_hash=content_hash,
                size_bytes=len(payload),
                mime_type=validated.mime_type,
                storage_path=path,
                submitted_by=user_id,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            # The object is stored but no version references it: remove it so a
            # retry does not accumulate orphans, then surface the failure.
            self._storage.delete(path)
            self._mark_failed(source.id, "storage_failed", None)
            raise exc

        outcome = self._extract_and_record(
            source=source,
            version_id=version.id,
            payload=payload,
            detected=validated.format,
        )

        refreshed = self._sources.get(source.id) or source
        return IngestionResult(
            source=refreshed,
            version_id=version.id,
            version_number=version.version_number,
            extraction=outcome,
            duplicate_of_existing=False,
        )

    def _create_source(
        self,
        *,
        user_id: str,
        workspace_id: str,
        kind: SourceKind,
        validated: ValidatedUpload,
        content_hash: str,
        path: str,
        idempotency_key: str | None,
    ) -> Source:
        try:
            source = self._sources.create(
                workspace_id=workspace_id,
                owner_id=user_id,
                kind=kind,
                title=validated.title,
                original_filename=None if kind is SourceKind.NOTE else validated.filename,
                mime_type=validated.mime_type,
                size_bytes=validated.size_bytes,
                content_hash=content_hash,
                storage_path=path,
                metadata={
                    "detected_format": validated.format.value,
                    "display_type": validated.spec.display_name,
                },
                idempotency_key=idempotency_key,
            )
        except MnemosError:
            self._storage.delete(path)
            raise
        self._set_status(source.id, ProcessingStatus.VALIDATING)
        return source

    def _retire_current(self, source_id: str) -> None:
        current = self._sources.current_version(source_id)
        if current is not None:
            self._sources.retire_version(current.id)

    def _extract_and_record(
        self,
        *,
        source: Source,
        version_id: str,
        payload: bytes,
        detected: DetectedFormat,
    ) -> ExtractionOutcome:
        self._set_status(source.id, ProcessingStatus.EXTRACTING)
        self._sources.update_version_extraction(
            version_id, status=ExtractionStatus.EXTRACTING, method=None
        )

        try:
            result = extract(detected, payload)
        except ExtractionError as exc:
            self._sources.update_version_extraction(
                version_id, status=ExtractionStatus.FAILED, error_code=exc.code
            )
            self._mark_failed(source.id, exc.code, exc.message)
            logger.warning("Extraction failed (code=%s)", exc.code)
            return ExtractionOutcome(
                status=ProcessingStatus.FAILED.value,
                method=None,
                char_count=0,
                page_count=0,
                segment_count=0,
                error_code=exc.code,
                error_message=exc.message,
            )

        self._persist_extraction(source, version_id, result)
        self._sources.update_version_extraction(
            version_id, status=ExtractionStatus.EXTRACTED, method=result.method
        )
        self._set_status(source.id, ProcessingStatus.EXTRACTED)
        logger.info(
            "Extraction complete (method=%s, chars=%d, segments=%d)",
            result.method,
            result.char_count,
            len(result.segments),
        )
        return ExtractionOutcome(
            status=ProcessingStatus.EXTRACTED.value,
            method=result.method,
            char_count=result.char_count,
            page_count=result.page_count,
            segment_count=len(result.segments),
        )

    def _persist_extraction(
        self, source: Source, version_id: str, result: ExtractionResult
    ) -> None:
        repository = self._sources
        if not isinstance(repository, SupabaseSourceRepository):
            return
        repository.store_extraction(
            workspace_id=source.workspace_id,
            document_version_id=version_id,
            result=result,
        )

    def _set_status(self, source_id: str, status: ProcessingStatus) -> None:
        self._sources.update_processing(source_id, status=status)

    def _mark_failed(self, source_id: str, code: str, detail: str | None) -> None:
        self._sources.update_processing(
            source_id,
            status=ProcessingStatus.FAILED,
            error_code=code[:64],
            error_detail=(detail or None) and detail[:500],
            increment_attempts=True,
        )
