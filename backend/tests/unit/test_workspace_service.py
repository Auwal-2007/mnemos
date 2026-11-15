"""Unit tests for workspace authorization rules.

The repository is an in-memory fake, so these tests pin the *policy*
(owner/editor/viewer) independently of Supabase.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.domain.models import Workspace, WorkspaceMember, WorkspaceRole
from app.services.workspace_service import WorkspaceService

OWNER = "owner-id"
EDITOR = "editor-id"
VIEWER = "viewer-id"
STRANGER = "stranger-id"


def _workspace(workspace_id: str = "ws-1", owner: str = OWNER) -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=workspace_id,
        owner_id=owner,
        name="Personal",
        slug="personal",
        description=None,
        created_at=now,
        updated_at=now,
    )


class FakeWorkspaceRepository:
    """In-memory stand-in that also mimics RLS scoping for list/get."""

    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.workspaces: dict[str, Workspace] = {"ws-1": _workspace()}
        self.members: list[WorkspaceMember] = [
            WorkspaceMember("ws-1", OWNER, WorkspaceRole.OWNER, now),
            WorkspaceMember("ws-1", EDITOR, WorkspaceRole.EDITOR, now),
            WorkspaceMember("ws-1", VIEWER, WorkspaceRole.VIEWER, now),
        ]

    def list_for_user(self, user_id: str) -> list[Workspace]:
        visible = {m.workspace_id for m in self.members if m.user_id == user_id}
        return [w for wid, w in self.workspaces.items() if wid in visible]

    def get(self, workspace_id: str) -> Workspace | None:
        return self.workspaces.get(workspace_id)

    def create(
        self, owner_id: str, name: str, slug: str, description: str | None = None
    ) -> Workspace:
        now = datetime.now(UTC)
        workspace_id = f"ws-{len(self.workspaces) + 1}"
        workspace = Workspace(workspace_id, owner_id, name, slug, description, now, now)
        self.workspaces[workspace_id] = workspace
        self.members.append(WorkspaceMember(workspace_id, owner_id, WorkspaceRole.OWNER, now))
        return workspace

    def update(
        self, workspace_id: str, *, name: str | None = None, description: str | None = None
    ) -> Workspace | None:
        current = self.workspaces.get(workspace_id)
        if current is None:
            return None
        updated = Workspace(
            current.id,
            current.owner_id,
            name if name is not None else current.name,
            current.slug,
            description if description is not None else current.description,
            current.created_at,
            datetime.now(UTC),
        )
        self.workspaces[workspace_id] = updated
        return updated

    def delete(self, workspace_id: str) -> bool:
        return self.workspaces.pop(workspace_id, None) is not None

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return [m for m in self.members if m.workspace_id == workspace_id]


@pytest.fixture
def service() -> WorkspaceService:
    return WorkspaceService(FakeWorkspaceRepository())


def test_list_only_returns_memberships(service: WorkspaceService) -> None:
    assert len(service.list_workspaces(OWNER)) == 1
    assert service.list_workspaces(STRANGER) == []


def test_owner_can_read(service: WorkspaceService) -> None:
    assert service.get_workspace("ws-1", OWNER).slug == "personal"


def test_viewer_can_read_but_not_update(service: WorkspaceService) -> None:
    assert service.get_workspace("ws-1", VIEWER).id == "ws-1"
    with pytest.raises(ForbiddenError):
        service.update_workspace("ws-1", VIEWER, name="Nope")


def test_editor_can_update(service: WorkspaceService) -> None:
    updated = service.update_workspace("ws-1", EDITOR, name="Shared")
    assert updated.name == "Shared"


def test_viewer_cannot_delete(service: WorkspaceService) -> None:
    with pytest.raises(ForbiddenError):
        service.delete_workspace("ws-1", VIEWER)


def test_editor_cannot_delete(service: WorkspaceService) -> None:
    with pytest.raises(ForbiddenError):
        service.delete_workspace("ws-1", EDITOR)


def test_owner_can_delete(service: WorkspaceService) -> None:
    service.delete_workspace("ws-1", OWNER)
    with pytest.raises(NotFoundError):
        service.get_workspace("ws-1", OWNER)


def test_stranger_gets_forbidden_not_not_found(service: WorkspaceService) -> None:
    """Unauthorized callers must not learn whether a workspace exists."""
    with pytest.raises(ForbiddenError):
        service.get_workspace("ws-1", STRANGER)


def test_missing_workspace_returns_not_found(service: WorkspaceService) -> None:
    with pytest.raises(NotFoundError):
        service.get_workspace("does-not-exist", OWNER)


def test_create_assigns_caller_as_owner(service: WorkspaceService) -> None:
    created = service.create_workspace(STRANGER, "Second", "second")
    assert created.owner_id == STRANGER
    members = service.list_members(created.id, STRANGER)
    assert any(m.user_id == STRANGER and m.role is WorkspaceRole.OWNER for m in members)


def test_duplicate_slug_for_same_owner_is_rejected(service: WorkspaceService) -> None:
    with pytest.raises(ValidationError):
        service.create_workspace(OWNER, "Duplicate", "personal")


def test_members_listed_for_viewer(service: WorkspaceService) -> None:
    assert len(service.list_members("ws-1", VIEWER)) == 3


def test_members_hidden_from_stranger(service: WorkspaceService) -> None:
    with pytest.raises(ForbiddenError):
        service.list_members("ws-1", STRANGER)
