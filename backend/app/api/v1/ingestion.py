"""Ingestion endpoints (Phase 2B).

Uploads are multipart/form-data. The server never trusts the client's MIME
type: `IngestionPipeline` inspects the bytes and stores what it detected.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, UploadFile, status

from app.api.deps import AuthContextDep, IngestionPipelineDep
from app.schemas.knowledge import (
    DownloadUrlResponse,
    ExtractionOutcomeResponse,
    IngestionResponse,
    NoteCreateRequest,
    SourceResponse,
)
from app.services.ingestion.pipeline import IngestionResult

logger = logging.getLogger("mnemos.api.ingestion")

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _to_response(result: IngestionResult) -> IngestionResponse:
    return IngestionResponse(
        source=SourceResponse.model_validate(result.source, from_attributes=True),
        version_id=result.version_id,
        version_number=result.version_number,
        extraction=ExtractionOutcomeResponse(
            status=result.extraction.status,
            method=result.extraction.method,
            char_count=result.extraction.char_count,
            page_count=result.extraction.page_count,
            segment_count=result.extraction.segment_count,
            error_code=result.extraction.error_code,
            error_message=result.extraction.error_message,
        ),
        duplicate_of_existing=result.duplicate_of_existing,
    )


@router.post(
    "/workspaces/{workspace_id}/sources/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
)
async def upload_document(
    workspace_id: str,
    context: AuthContextDep,
    pipeline: IngestionPipelineDep,
    file: Annotated[UploadFile, File(description="PDF, Markdown or plain text")],
    title: Annotated[str | None, Form(max_length=300)] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> IngestionResponse:
    """Store the original privately, record a version, extract text."""
    raw = await file.read()
    logger.info("Upload received (declared=%s, bytes=%d)", file.content_type, len(raw))
    result = pipeline.ingest_document(
        user_id=context.identity.user_id,
        workspace_id=workspace_id,
        raw=raw,
        filename=file.filename,
        declared_mime=file.content_type,
        title=title,
        idempotency_key=idempotency_key,
    )
    return _to_response(result)


@router.post(
    "/workspaces/{workspace_id}/sources/note",
    status_code=status.HTTP_201_CREATED,
    summary="Create a note",
)
async def create_note(
    workspace_id: str,
    payload: NoteCreateRequest,
    context: AuthContextDep,
    pipeline: IngestionPipelineDep,
) -> IngestionResponse:
    """Create a note as a versioned source, not a loose string."""
    if payload.workspace_id != workspace_id:
        from app.core.errors import ValidationError

        raise ValidationError(message="The workspace in the body does not match the URL.")
    result = pipeline.ingest_note(
        user_id=context.identity.user_id,
        workspace_id=workspace_id,
        content=payload.content,
        title=payload.title,
        idempotency_key=payload.idempotency_key,
    )
    return _to_response(result)


@router.post(
    "/sources/{source_id}/versions/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new version of a document",
)
async def upload_new_version(
    source_id: str,
    context: AuthContextDep,
    pipeline: IngestionPipelineDep,
    file: Annotated[UploadFile, File()],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> IngestionResponse:
    """Append a version. The previous version and its chunks are retained."""
    raw = await file.read()
    result = pipeline.add_version(
        user_id=context.identity.user_id,
        source_id=source_id,
        raw=raw,
        filename=file.filename,
        declared_mime=file.content_type,
        idempotency_key=idempotency_key,
    )
    return _to_response(result)


@router.post(
    "/sources/{source_id}/versions/note",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new version of a note",
)
async def add_note_version(
    source_id: str,
    payload: NoteCreateRequest,
    context: AuthContextDep,
    pipeline: IngestionPipelineDep,
) -> IngestionResponse:
    result = pipeline.add_version(
        user_id=context.identity.user_id,
        source_id=source_id,
        content=payload.content,
        idempotency_key=payload.idempotency_key,
    )
    return _to_response(result)


@router.get(
    "/sources/{source_id}/download",
    summary="Get a short-lived download link for the original file",
)
async def download_original(
    source_id: str,
    context: AuthContextDep,
    pipeline: IngestionPipelineDep,
) -> DownloadUrlResponse:
    """Signed URLs expire quickly and are scoped to the caller by RLS."""
    url = pipeline.download_url(
        user_id=context.identity.user_id, source_id=source_id, expires_in=300
    )
    return DownloadUrlResponse(url=url, expires_in_seconds=300)
