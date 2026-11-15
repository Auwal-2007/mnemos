"""Supabase-backed repository implementations.

All queries run through the PostgREST client, which means RLS policies
still apply for user-scoped clients. Upserts and deletes are written so
that a policy denial surfaces as an error rather than a silent no-op.

Only parameterised, pre-declared queries exist here. There is no generic
`execute(sql)` entry point, by design.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, cast

from postgrest.exceptions import APIError
from supabase import Client

from app.core.errors import ForbiddenError, MnemosError, NotFoundError
from app.domain.models import Profile, UserPreferences, Workspace, WorkspaceMember, WorkspaceRole

logger = logging.getLogger("mnemos.repositories")


class RepositoryError(MnemosError):
    """Raised when a data operation fails unexpectedly."""

    status_code = 500
    code = "repository_error"
    default_message = "A data operation failed. Please try again."


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # PostgREST returns ISO-8601 with a trailing Z.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise RepositoryError(message="Unexpected timestamp value returned by the database.")


def _profile(row: dict[str, Any]) -> Profile:
    return Profile(
        id=str(row["id"]),
        email=cast("str | None", row.get("email")),
        display_name=cast("str | None", row.get("display_name")),
        avatar_url=cast("str | None", row.get("avatar_url")),
        created_at=_parse_datetime(row.get("created_at")),
        updated_at=_parse_datetime(row.get("updated_at")),
    )


def _workspace(row: dict[str, Any]) -> Workspace:
    return Workspace(
        id=str(row["id"]),
        owner_id=str(row["owner_id"]),
        name=str(row["name"]),
        slug=str(row["slug"]),
        description=cast("str | None", row.get("description")),
        created_at=_parse_datetime(row.get("created_at")),
        updated_at=_parse_datetime(row.get("updated_at")),
    )


def _member(row: dict[str, Any]) -> WorkspaceMember:
    return WorkspaceMember(
        workspace_id=str(row["workspace_id"]),
        user_id=str(row["user_id"]),
        role=WorkspaceRole(row["role"]),
        created_at=_parse_datetime(row.get("created_at")),
    )


def _preferences(row: dict[str, Any]) -> UserPreferences:
    return UserPreferences(
        user_id=str(row["user_id"]),
        theme=str(row["theme"]),
        locale=str(row["locale"]),
        created_at=_parse_datetime(row.get("created_at")),
        updated_at=_parse_datetime(row.get("updated_at")),
    )


class _BaseSupabaseRepository:
    """Shared error translation for PostgREST interactions."""

    def __init__(self, client: Client) -> None:
        self._client = client

    @staticmethod
    def _translate(exc: APIError, *, not_found_ok: bool = False) -> MnemosError:
        code = getattr(exc, "code", "") or ""
        message = (getattr(exc, "message", "") or str(exc)).lower()
        if code == "PGRST116" or "no rows" in message:
            return NotFoundError()
        # RLS rejections surface as insufficient privilege / policy errors.
        if code in {"42501", "PGRST301"} or "permission denied" in message or "policy" in message:
            logger.warning("RLS rejected a data operation (code=%s)", code or "unknown")
            return ForbiddenError()
        logger.error("Database error (code=%s)", code or "unknown")
        return RepositoryError()


class SupabaseProfileRepository(_BaseSupabaseRepository):
    """Profile reads and updates."""

    def get_by_id(self, user_id: str) -> Profile | None:
        try:
            response = (
                self._client.table("profiles")
                .select("*")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        data = response.data if response else None
        return _profile(cast("dict[str, Any]", data)) if data else None

    def list_workspace_colleagues(self, user_id: str) -> list[Profile]:
        """Profiles of users who share at least one workspace with `user_id`."""
        try:
            memberships = (
                self._client.table("workspace_members")
                .select("workspace_id")
                .eq("user_id", user_id)
                .execute()
            )
            workspace_ids = [row["workspace_id"] for row in memberships.data or []]
            if not workspace_ids:
                return []
            colleagues = (
                self._client.table("workspace_members")
                .select("user_id")
                .in_("workspace_id", workspace_ids)
                .execute()
            )
            colleague_ids = sorted({row["user_id"] for row in colleagues.data or []})
            if not colleague_ids:
                return []
            profiles = self._client.table("profiles").select("*").in_("id", colleague_ids).execute()
        except APIError as exc:
            raise self._translate(exc) from exc
        return [_profile(cast("dict[str, Any]", row)) for row in profiles.data or []]

    def update_display_name(self, user_id: str, display_name: str | None) -> Profile | None:
        try:
            response = (
                self._client.table("profiles")
                .update({"display_name": display_name})
                .eq("id", user_id)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        return _profile(cast("dict[str, Any]", rows[0])) if rows else None


class SupabaseWorkspaceRepository(_BaseSupabaseRepository):
    """Workspace CRUD scoped by RLS."""

    def list_for_user(self, _user_id: str) -> list[Workspace]:
        """List workspaces visible to the current client identity.

        The user id parameter documents intent; authorization is enforced by
        RLS on the supplied client, so passing a different id cannot widen
        access.
        """
        try:
            response = (
                self._client.table("workspaces")
                .select("*")
                .order("created_at", desc=False)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        return [_workspace(cast("dict[str, Any]", row)) for row in response.data or []]

    def get(self, workspace_id: str) -> Workspace | None:
        try:
            response = (
                self._client.table("workspaces")
                .select("*")
                .eq("id", workspace_id)
                .maybe_single()
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        data = response.data if response else None
        return _workspace(cast("dict[str, Any]", data)) if data else None

    def create(
        self, owner_id: str, name: str, slug: str, description: str | None = None
    ) -> Workspace:
        payload = {"owner_id": owner_id, "name": name, "slug": slug, "description": description}
        try:
            response = self._client.table("workspaces").insert(payload).execute()
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        if not rows:
            # An insert blocked by RLS returns no rows; never pretend success.
            raise ForbiddenError(message="You are not allowed to create this workspace.")
        return _workspace(cast("dict[str, Any]", rows[0]))

    def update(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Workspace | None:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if not payload:
            return self.get(workspace_id)

        try:
            response = (
                self._client.table("workspaces").update(payload).eq("id", workspace_id).execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        if not rows:
            raise ForbiddenError(message="You are not allowed to modify this workspace.")
        return _workspace(cast("dict[str, Any]", rows[0]))

    def delete(self, workspace_id: str) -> bool:
        try:
            response = self._client.table("workspaces").delete().eq("id", workspace_id).execute()
        except APIError as exc:
            raise self._translate(exc) from exc
        return bool(response.data)

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        try:
            response = (
                self._client.table("workspace_members")
                .select("*")
                .eq("workspace_id", workspace_id)
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        return [_member(cast("dict[str, Any]", row)) for row in response.data or []]


class SupabasePreferencesRepository(_BaseSupabaseRepository):
    """User preference reads and updates."""

    def get(self, user_id: str) -> UserPreferences | None:
        try:
            response = (
                self._client.table("user_preferences")
                .select("*")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        data = response.data if response else None
        return _preferences(cast("dict[str, Any]", data)) if data else None

    def upsert_theme(self, user_id: str, theme: str) -> UserPreferences | None:
        try:
            response = (
                self._client.table("user_preferences")
                .upsert({"user_id": user_id, "theme": theme}, on_conflict="user_id")
                .execute()
            )
        except APIError as exc:
            raise self._translate(exc) from exc
        rows = response.data or []
        return _preferences(cast("dict[str, Any]", rows[0])) if rows else None
