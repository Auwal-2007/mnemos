"""Repository interfaces and Supabase implementations."""

from app.repositories.base import (
    PreferencesRepository,
    ProfileRepository,
    WorkspaceRepository,
)
from app.repositories.supabase_repositories import (
    SupabasePreferencesRepository,
    SupabaseProfileRepository,
    SupabaseWorkspaceRepository,
)

__all__ = [
    "PreferencesRepository",
    "ProfileRepository",
    "SupabasePreferencesRepository",
    "SupabaseProfileRepository",
    "SupabaseWorkspaceRepository",
    "WorkspaceRepository",
]
