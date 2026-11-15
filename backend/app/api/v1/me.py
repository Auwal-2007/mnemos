"""Authenticated user endpoints: profile and preferences."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import IdentityDep, PreferencesRepoDep, ProfileRepoDep
from app.schemas.workspace import (
    PreferencesResponse,
    PreferencesUpdateRequest,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.services.preferences_service import PreferencesService
from app.services.profile_service import ProfileService

router = APIRouter(tags=["me"])


@router.get("/me", response_model=ProfileResponse, summary="Current user profile")
async def get_me(identity: IdentityDep, profiles: ProfileRepoDep) -> ProfileResponse:
    """Return the authenticated caller's profile.

    The user id comes from the verified token only — never from the request.
    """
    profile = ProfileService(profiles).get_profile(identity.user_id)
    return ProfileResponse.model_validate(profile)


@router.patch("/me", response_model=ProfileResponse, summary="Update own profile")
async def update_me(
    payload: ProfileUpdateRequest,
    identity: IdentityDep,
    profiles: ProfileRepoDep,
) -> ProfileResponse:
    """Update the caller's display name."""
    profile = ProfileService(profiles).update_display_name(identity.user_id, payload.display_name)
    return ProfileResponse.model_validate(profile)


@router.get("/me/preferences", response_model=PreferencesResponse, summary="Get preferences")
async def get_preferences(
    identity: IdentityDep,
    preferences: PreferencesRepoDep,
) -> PreferencesResponse:
    """Return the caller's preferences, creating defaults when absent."""
    result = PreferencesService(preferences).get_preferences(identity.user_id)
    return PreferencesResponse.model_validate(result)


@router.put("/me/preferences", response_model=PreferencesResponse, summary="Update preferences")
async def update_preferences(
    payload: PreferencesUpdateRequest,
    identity: IdentityDep,
    preferences: PreferencesRepoDep,
) -> PreferencesResponse:
    """Persist the caller's theme preference."""
    updated = PreferencesService(preferences).update_theme(identity.user_id, payload.theme)
    return PreferencesResponse.model_validate(updated)
