"""Profile application service."""

from __future__ import annotations

import logging

from app.core.errors import NotFoundError
from app.domain.models import Profile
from app.repositories.base import ProfileRepository

logger = logging.getLogger("mnemos.profiles")


class ProfileService:
    """Profile operations for the authenticated user."""

    def __init__(self, profiles: ProfileRepository) -> None:
        self._profiles = profiles

    def get_profile(self, user_id: str) -> Profile:
        """Return the caller's profile, or 404 when the bootstrap row is missing."""
        profile = self._profiles.get_by_id(user_id)
        if profile is None:
            raise NotFoundError(
                message="No profile exists for this account yet. Sign out and back in to retry."
            )
        return profile

    def update_display_name(self, user_id: str, display_name: str | None) -> Profile:
        """Update the caller's display name."""
        profile = self._profiles.update_display_name(user_id, display_name)
        if profile is None:
            raise NotFoundError(message="Profile not found.")
        return profile
