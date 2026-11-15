"""Workspace application service.

Authorization policy lives here, expressed in terms the domain understands:

* A user may see workspaces RLS shows them.
* Creating a workspace always assigns the caller as owner; the owner id is
  never taken from the request body.
* Mutations and deletions require owner/editor (update) or owner (delete),
  checked against membership before calling the repository.
"""

from __future__ import annotations

import logging

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.domain.models import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.base import WorkspaceRepository

logger = logging.getLogger("mnemos.workspaces")


class WorkspaceService:
    """Business rules for workspaces."""

    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository

    def list_workspaces(self, user_id: str) -> list[Workspace]:
        """Workspaces visible to the caller."""
        return self._repository.list_for_user(user_id)

    def get_workspace(self, workspace_id: str, user_id: str) -> Workspace:
        """Fetch a workspace the caller is allowed to see."""
        workspace = self._repository.get(workspace_id)
        if workspace is None:
            raise NotFoundError(message="Workspace not found.")
        self._require_role(
            workspace_id, user_id, {WorkspaceRole.OWNER, WorkspaceRole.EDITOR, WorkspaceRole.VIEWER}
        )
        return workspace

    def create_workspace(
        self, owner_id: str, name: str, slug: str, description: str | None = None
    ) -> Workspace:
        """Create a workspace owned by the authenticated caller."""
        existing = {workspace.slug for workspace in self._repository.list_for_user(owner_id)}
        if slug in existing:
            raise ValidationError(message="You already have a workspace with that slug.")
        workspace = self._repository.create(owner_id, name, slug, description)
        logger.info("Workspace created (slug=%s)", workspace.slug)
        return workspace

    def update_workspace(
        self,
        workspace_id: str,
        user_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Workspace:
        """Update a workspace; requires owner or editor."""
        self._require_role(workspace_id, user_id, {WorkspaceRole.OWNER, WorkspaceRole.EDITOR})
        updated = self._repository.update(workspace_id, name=name, description=description)
        if updated is None:
            raise NotFoundError(message="Workspace not found.")
        return updated

    def delete_workspace(self, workspace_id: str, user_id: str) -> None:
        """Delete a workspace; requires owner."""
        self._require_role(workspace_id, user_id, {WorkspaceRole.OWNER})
        if not self._repository.delete(workspace_id):
            raise NotFoundError(message="Workspace not found.")

    def list_members(self, workspace_id: str, user_id: str) -> list[WorkspaceMember]:
        """Members of a workspace the caller belongs to."""
        self._require_role(
            workspace_id,
            user_id,
            {WorkspaceRole.OWNER, WorkspaceRole.EDITOR, WorkspaceRole.VIEWER},
        )
        return self._repository.list_members(workspace_id)

    # --- internals -------------------------------------------------------

    def _require_role(
        self, workspace_id: str, user_id: str, allowed: set[WorkspaceRole]
    ) -> WorkspaceMember:
        members = self._repository.list_members(workspace_id)
        for member in members:
            if member.user_id == user_id and member.role in allowed:
                return member
        # Do not disclose whether the workspace exists to unauthorized callers.
        raise ForbiddenError(message="You do not have access to this workspace.")
