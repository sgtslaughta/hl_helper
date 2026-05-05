# Register BEFORE users_router to avoid /me being matched as {user_id}.
"""User Preferences API: get and update user settings.

This router handles /v1/users/me/prefs and must be registered before the
main users router to prevent /me from being parsed as a user_id path parameter.

Preferences include theme, locale, timezone, UI density, and nav state.
TODO: Implement user session auth (currently uses admin_required as placeholder).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from server.app.api.middleware.admin_auth import admin_required

router = APIRouter(prefix="/v1/users/me", tags=["user-prefs"])
log = structlog.get_logger(__name__)

# Default preferences


class UserPrefsOut(BaseModel):
    """User preferences response."""

    theme: str = Field(
        "system",
        description="UI theme: 'light', 'dark', or 'system'",
    )
    locale: str = Field("en", description="Preferred locale (e.g., 'en', 'fr')")
    timezone: str = Field("UTC", description="Preferred timezone (IANA)")
    density: str = Field(
        "comfortable",
        description="UI density: 'compact', 'comfortable', or 'spacious'",
    )
    side_nav_collapsed: bool = Field(False, description="Side nav collapsed state")


class UserPrefsUpdate(BaseModel):
    """Request to update user preferences (partial)."""

    theme: str | None = Field(None, description="UI theme")
    locale: str | None = Field(None, description="Preferred locale")
    timezone: str | None = Field(None, description="Preferred timezone")
    density: str | None = Field(None, description="UI density")
    side_nav_collapsed: bool | None = Field(None, description="Side nav state")


@router.get("/prefs", response_model=UserPrefsOut)
async def get_user_prefs(
    # TODO: Switch from admin_required to user-session auth
    actor: str = Depends(admin_required),
) -> UserPrefsOut:
    """Get user preferences (defaults if not saved).

    Returns:
        User preferences with default values (TODO: fetch from database).
    """
    # TODO: Fetch preferences for authenticated user from database
    return UserPrefsOut(
        theme="system",
        locale="en",
        timezone="UTC",
        density="comfortable",
        side_nav_collapsed=False,
    )


@router.put("/prefs", response_model=UserPrefsOut, status_code=status.HTTP_200_OK)
async def update_user_prefs(
    body: UserPrefsUpdate,
    # TODO: Switch from admin_required to user-session auth
    actor: str = Depends(admin_required),
) -> UserPrefsOut:
    """Update user preferences (partial update).

    Args:
        body: Preferences to update (any fields not in request are unchanged)

    Returns:
        Merged preferences with defaults (TODO: save to database).
    """
    # TODO: Fetch current prefs, merge with request body, validate, save
    current: dict[str, str | bool] = {
        "theme": "system",
        "locale": "en",
        "timezone": "UTC",
        "density": "comfortable",
        "side_nav_collapsed": False,
    }
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            current[key] = value

    return UserPrefsOut.model_validate(current)
