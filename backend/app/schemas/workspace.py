"""API schemas for foundational entities."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{1,48}[a-z0-9])$")


class ProfileResponse(BaseModel):
    """Publicly safe profile representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str | None
    display_name: str | None
    avatar_url: str | None
    created_at: datetime
    updated_at: datetime


class ProfileUpdateRequest(BaseModel):
    """Only fields a user may change about themselves."""

    display_name: str | None = Field(default=None, max_length=80)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return cleaned


class WorkspaceResponse(BaseModel):
    """Workspace representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class WorkspaceCreateRequest(BaseModel):
    """Create a workspace for the authenticated caller."""

    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=50)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must contain visible characters")
        return cleaned

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        lowered = value.strip().lower()
        if not SLUG_PATTERN.match(lowered):
            raise ValueError(
                "slug must be 3-50 characters of lowercase letters, digits or hyphens, "
                "and cannot start or end with a hyphen"
            )
        return lowered


class WorkspaceUpdateRequest(BaseModel):
    """Partial workspace update."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must contain visible characters")
        return cleaned


class WorkspaceMemberResponse(BaseModel):
    """Membership row."""

    model_config = ConfigDict(from_attributes=True)

    workspace_id: str
    user_id: str
    role: Literal["owner", "editor", "viewer"]
    created_at: datetime


class MemberListResponse(BaseModel):
    """Members of a workspace."""

    items: list[WorkspaceMemberResponse]
    total: int


class PreferencesResponse(BaseModel):
    """Per-user preferences."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    theme: Literal["system", "light", "dark"]
    locale: str
    created_at: datetime
    updated_at: datetime


class PreferencesUpdateRequest(BaseModel):
    """Theme preference update."""

    theme: Literal["system", "light", "dark"]
