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

from typing import Protocol

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
