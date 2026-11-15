"""Repository interfaces.

Data access is expressed as narrow, intention-revealing interfaces so that
services depend on behaviour rather than on a specific database driver.
Implementations live in `supabase_repositories`.

Rules enforced by this boundary:
* No SQL is accepted from callers (agents included); only these methods.
* Every method is scoped to an authenticated user or an explicitly
  privileged operation that a service has already authorized.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from app.domain.knowledge import (
    Chunk,
    ChunkDraft,
    DocumentVersion,
    ExtractionStatus,
    InformationStatus,
    ProcessingStatus,
    ProvenanceReference,
    Source,
    SourceKind,
)
from app.domain.models import Profile, UserPreferences, Workspace, WorkspaceMember


class ProfileRepository(Protocol):
    """Read and update the current user's profile."""

    def get_by_id(self, user_id: str) -> Profile | None: ...

    def list_workspace_colleagues(self, user_id: str) -> list[Profile]: ...

    def update_display_name(self, user_id: str, display_name: str | None) -> Profile | None: ...


class WorkspaceRepository(Protocol):
    """Workspace access scoped to the authenticated user."""

    def list_for_user(self, user_id: str) -> list[Workspace]: ...

    def get(self, workspace_id: str) -> Workspace | None: ...

    def create(
        self, owner_id: str, name: str, slug: str, description: str | None = None
    ) -> Workspace: ...

    def update(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Workspace | None: ...

    def delete(self, workspace_id: str) -> bool: ...

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]: ...


class PreferencesRepository(Protocol):
    """Per-user preferences."""

    def get(self, user_id: str) -> UserPreferences | None: ...

    def upsert_theme(self, user_id: str, theme: str) -> UserPreferences | None: ...


class SourceRepository(Protocol):
    """Sources and their immutable versions.

    Every method is scoped by the caller's RLS-visible rows; a workspace id is
    never trusted on its own and ownership is re-checked by policy.
    """

    def list_for_workspace(
        self, workspace_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Source]: ...

    def get(self, source_id: str) -> Source | None: ...

    def find_by_idempotency_key(self, workspace_id: str, idempotency_key: str) -> Source | None: ...

    def create(
        self,
        *,
        workspace_id: str,
        owner_id: str,
        kind: SourceKind,
        title: str,
        original_filename: str | None,
        mime_type: str,
        size_bytes: int,
        content_hash: str,
        storage_path: str,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Source: ...

    def update_processing(
        self,
        source_id: str,
        *,
        status: ProcessingStatus,
        error_code: str | None = None,
        error_detail: str | None = None,
        increment_attempts: bool = False,
    ) -> Source | None: ...

    def delete(self, source_id: str) -> bool: ...

    def create_version(
        self,
        *,
        workspace_id: str,
        source_id: str,
        content_hash: str,
        size_bytes: int,
        mime_type: str,
        storage_path: str,
        submitted_by: str,
        idempotency_key: str | None = None,
    ) -> DocumentVersion: ...

    def list_versions(self, source_id: str) -> list[DocumentVersion]: ...

    def get_version(self, version_id: str) -> DocumentVersion | None: ...

    def current_version(self, source_id: str) -> DocumentVersion | None: ...

    def retire_version(self, version_id: str) -> None:
        """Mark a version as no longer current. Never deletes content."""
        ...

    def update_version_extraction(
        self,
        version_id: str,
        *,
        status: ExtractionStatus,
        method: str | None = None,
        error_code: str | None = None,
    ) -> DocumentVersion | None: ...


class ChunkRepository(Protocol):
    """Chunks and the provenance records that point at them."""

    def create_many(
        self,
        *,
        workspace_id: str,
        source_id: str,
        document_version_id: str,
        chunks: Sequence[ChunkDraft],
        chunking_method: str,
        chunking_version: int,
    ) -> list[Chunk]: ...

    def list_for_version(self, version_id: str) -> list[Chunk]: ...

    def count_for_version(self, version_id: str) -> int: ...

    def delete_for_version(self, version_id: str) -> int:
        """Remove chunks of a version before re-chunking.

        Provenance rows cascade, so this is only safe for a version whose
        chunks have never been used as evidence. Services enforce that rule.
        """
        ...

    def create_provenance(
        self,
        *,
        workspace_id: str,
        source_id: str,
        document_version_id: str,
        chunk_id: str,
        source_location: dict[str, Any],
        submitted_at: datetime,
        information_status: InformationStatus = InformationStatus.CURRENT,
    ) -> ProvenanceReference: ...

    def list_provenance_for_version(self, version_id: str) -> list[ProvenanceReference]: ...

    def resolve_for_chunk(self, chunk_id: str) -> ProvenanceReference | None: ...
