"""User preferences application service."""

from __future__ import annotations

import logging

from app.core.errors import NotFoundError
from app.domain.models import UserPreferences
from app.repositories.base import PreferencesRepository

logger = logging.getLogger("mnemos.preferences")


class PreferencesService:
    """Per-user preference operations."""

    def __init__(self, preferences: PreferencesRepository) -> None:
        self._preferences = preferences

    def get_preferences(self, user_id: str) -> UserPreferences:
        """Return preferences, creating the default row if it is missing."""
        preferences = self._preferences.get(user_id)
        if preferences is not None:
            return preferences
        created = self._preferences.upsert_theme(user_id, "system")
        if created is None:
            raise NotFoundError(message="Preferences could not be initialized.")
        logger.info("Initialised default preferences for user")
        return created

    def update_theme(self, user_id: str, theme: str) -> UserPreferences:
        """Persist a theme preference."""
        updated = self._preferences.upsert_theme(user_id, theme)
        if updated is None:
            raise NotFoundError(message="Preferences could not be updated.")
        return updated
