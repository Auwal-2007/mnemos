"""Private object storage adapter (Phase 2B).

Originals live in the private `sources` bucket. Access is always through a
client bound to the caller's token, so the bucket policy — first path segment
must equal `auth.uid()` — applies to every write and read.

There is no public URL and no signed-URL shortcut in this module: the only way
out of the bucket is a short-lived signed URL minted for the authenticated
owner by the download endpoint.
"""

from __future__ import annotations

import logging
from typing import Protocol

from storage3.utils import StorageException
from supabase import Client

from app.core.config import Settings
from app.core.errors import MnemosError

logger = logging.getLogger("mnemos.storage")


class StorageError(MnemosError):
    """Object storage failed in a way the caller must know about."""

    status_code = 502
    code = "storage_error"
    default_message = "The file store is unavailable. Please try again."


class PrivateStorage(Protocol):
    """Minimal object-store surface used by ingestion."""

    def upload(self, path: str, content: bytes, mime_type: str) -> None: ...

    def download(self, path: str) -> bytes: ...

    def delete(self, path: str) -> None: ...

    def signed_url(self, path: str, expires_in: int) -> str: ...


class SupabaseStorage:
    """`PrivateStorage` over Supabase Storage, using a user-scoped client."""

    def __init__(self, client: Client, settings: Settings) -> None:
        self._client = client
        self._bucket = settings.supabase_storage_bucket_sources

    def upload(self, path: str, content: bytes, mime_type: str) -> None:
        try:
            self._client.storage.from_(self._bucket).upload(
                path,
                content,
                file_options={"content-type": mime_type, "upsert": "false"},
            )
        except StorageException as exc:
            logger.error("Storage upload failed (status=%s)", getattr(exc, "status", "?"))
            raise StorageError(message="The file could not be stored. Please try again.") from exc

    def download(self, path: str) -> bytes:
        try:
            content = self._client.storage.from_(self._bucket).download(path)
        except StorageException as exc:
            logger.error("Storage download failed (status=%s)", getattr(exc, "status", "?"))
            raise StorageError(message="The stored file could not be read.") from exc
        if not isinstance(content, bytes):
            raise StorageError(message="The file store returned an unexpected response.")
        return content

    def delete(self, path: str) -> None:
        try:
            self._client.storage.from_(self._bucket).remove([path])
        except StorageException as exc:
            # Deletion of an already-absent object is not worth failing a
            # source deletion over; log and move on so the database cascade
            # still happens.
            logger.warning("Storage delete failed (status=%s)", getattr(exc, "status", "?"))
            del exc

    def signed_url(self, path: str, expires_in: int) -> str:
        try:
            response = self._client.storage.from_(self._bucket).create_signed_url(path, expires_in)
        except StorageException as exc:
            logger.error("Signed URL creation failed (status=%s)", getattr(exc, "status", "?"))
            raise StorageError(message="A download link could not be created.") from exc
        if isinstance(response, dict):
            url = response.get("signedURL") or response.get("signedUrl")
            if isinstance(url, str):
                return url
        raise StorageError(message="The file store returned an unexpected response.")
