"""Sessions API: list and revoke user browser/auth sessions.

Sessions represent active authenticated connections (e.g., browser tabs, API clients).
Distinct from service_accounts (which are service principals).
TODO: Implement session persistence and lifecycle management.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from server.app.api.middleware.admin_auth import admin_required

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])
log = structlog.get_logger(__name__)


class SessionOut(BaseModel):
    """Active session response."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Session ID")
    created_at: datetime = Field(..., description="Session created timestamp")
    last_seen_at: datetime = Field(..., description="Last activity timestamp")
    ip: str = Field(..., description="Client IP address")
    user_agent: str = Field(..., description="Client user agent")
    current: bool = Field(
        ..., description="Whether this is the current request's session"
    )


class RevokeAllResponse(BaseModel):
    """Response from revoke-all operation."""

    revoked: int = Field(..., description="Number of sessions revoked")


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    actor: str = Depends(admin_required),
) -> list[SessionOut]:
    """List all active sessions for the current user.

    Returns:
        List of active sessions with metadata (TODO: fetch from database).
    """
    # TODO: Fetch sessions for authenticated user from database
    return []


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    actor: str = Depends(admin_required),
) -> None:
    """Revoke a single session by ID.

    Args:
        session_id: Session to revoke

    Returns:
        204 No Content.
    """
    # TODO: Mark session as revoked in database, invalidate any cached tokens
    pass


@router.delete("", response_model=RevokeAllResponse)
async def revoke_all_sessions(
    actor: str = Depends(admin_required),
) -> RevokeAllResponse:
    """Revoke all active sessions for the current user.

    Returns:
        {revoked: count} with 200 OK (TODO: actually revoke all).
    """
    # TODO: Mark all sessions for authenticated user as revoked
    return RevokeAllResponse(revoked=0)
