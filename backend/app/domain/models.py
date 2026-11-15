"""Domain models for the Phase 1 foundational entities.

These are plain dataclasses so the domain stays independent of Pydantic,
FastAPI and the database driver. API schemas adapt them at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class WorkspaceRole(StrEnum):
    """Role a user holds within a workspace."""

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


@dataclass(frozen=True, slots=True)
class Profile:
    """Application-level identity mirror."""

    id: str
    email: str | None
    display_name: str | None
    avatar_url: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Workspace:
    """A user-owned knowledge container."""

    id: str
    owner_id: str
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    """Explicit membership of a user in a workspace."""

    workspace_id: str
    user_id: str
    role: WorkspaceRole
    created_at: datetime


@dataclass(frozen=True, slots=True)
class UserPreferences:
    """Per-user application preferences."""

    user_id: str
    theme: str
    locale: str
    created_at: datetime
    updated_at: datetime
