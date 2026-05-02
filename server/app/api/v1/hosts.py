"""Host management endpoints."""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.revocation.service import (
    HostAlreadyRevokedError,
    HostNotFoundError,
    RevocationService,
)

router = APIRouter(prefix="/v1/hosts", tags=["hosts"])

# Dependency providers (will be overridden in tests)
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session. Override in tests."""
    raise NotImplementedError("get_session must be provided by app startup")


def get_revocation_service() -> RevocationService:
    """Get revocation service. Override in tests."""
    raise NotImplementedError("get_revocation_service must be provided by app startup")


@router.delete("/{host_id}", status_code=204)
async def revoke_host(
    host_id: str,
    reason: str | None = None,
    actor: str = "admin",
    service: RevocationService = Depends(get_revocation_service),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Revoke a host (admin-only).

    TODO: Replace actor with authenticated user once C2/C3 auth is implemented.
    """
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
