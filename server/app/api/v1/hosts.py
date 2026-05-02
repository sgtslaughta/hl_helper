"""Host management endpoints."""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.middleware.admin_auth import admin_required
from server.app.revocation.service import (
    HostAlreadyRevokedError,
    HostNotFoundError,
    RevocationService,
)

router = APIRouter(prefix="/v1/hosts", tags=["hosts"])


# Dependency providers (can be overridden in tests)
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Get database session from app state."""
    from server.app.api.app import get_app_state

    state = get_app_state(request)
    async with state.sessionmaker() as session:
        yield session


def get_revocation_service(request: Request) -> RevocationService:
    """Get revocation service from app state."""
    from server.app.api.app import get_app_state

    state = get_app_state(request)
    return state.revocation_service


@router.delete("/{host_id}", status_code=204)
async def revoke_host(
    host_id: str,
    reason: str | None = None,
    actor: str = Depends(admin_required),
    service: RevocationService = Depends(get_revocation_service),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Revoke a host (admin-only)."""
    try:
        await service.revoke(session, host_id=host_id, actor=actor, reason=reason)
        await session.commit()
    except HostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="host not found",
        )
    except HostAlreadyRevokedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="host already revoked",
        )
