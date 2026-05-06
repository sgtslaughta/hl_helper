"""Host management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.dispatcher.dispatcher import (
    RebootPayload,
    ShellExecPayload,
    PkgUpdatePayload,
)
from server.app.dispatcher.targets import HostListSelector
from server.app.models.host import Host
from server.app.rbac.provider import Principal
from server.app.revocation.service import (
    HostAlreadyRevokedError,
    HostNotFoundError,
    RevocationService,
)

router = APIRouter(prefix="/v1/hosts", tags=["hosts"])


# ===== Request/Response Models =====


class HostOut(BaseModel):
    """Host response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    hostname: str
    display_name: str | None = None
    status: str
    enrolled_at: datetime
    last_seen_at: datetime | None = None
    labels: dict[str, Any] = {}


class RebootActionRequest(BaseModel):
    """Request body for reboot action."""

    delay_s: int = 0
    reason: str = ""


class ShellExecActionRequest(BaseModel):
    """Request body for shell-exec action."""

    command: str
    timeout_s: int = 60


class PkgUpdateActionRequest(BaseModel):
    """Request body for pkg-update action."""

    classes: list[str] = []


class ActionResponse(BaseModel):
    """Response for action dispatch endpoints."""

    task_id: str
    dispatched: list[str]
    denied: list[str]
    pending_approval_ids: list[str]


# ===== Dependency providers (can be overridden in tests) =====
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Get database session from app state."""

    state = get_app_state(request)
    async with state.sessionmaker() as session:
        yield session


def get_revocation_service(request: Request) -> RevocationService:
    """Get revocation service from app state."""

    state = get_app_state(request)
    rs: RevocationService = state.revocation_service
    return rs


@router.get("", response_model=list[HostOut])
async def list_hosts(
    request: Request,
    actor: str = Depends(admin_required),
    session: AsyncSession = Depends(get_session),
    state: str | None = None,
    group_id: str | None = None,
) -> list[HostOut]:
    """List hosts. Optional filters: state, group_id."""
    stmt = select(Host)

    # Apply state filter if provided
    if state:
        stmt = stmt.where(Host.status == state)

    # Note: group_id filter would require a join with GroupMembership
    # Implement if needed when group filtering is required

    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [HostOut.model_validate(r) for r in rows]


@router.get("/{host_id}", response_model=HostOut)
async def get_host(
    host_id: str,
    actor: str = Depends(admin_required),
    session: AsyncSession = Depends(get_session),
) -> HostOut:
    """Get a single host by id."""
    row = await session.get(Host, host_id)
    if row is None:
        raise HTTPException(status_code=404, detail="host_not_found")
    return HostOut.model_validate(row)


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


# ===== Action Endpoints =====


@router.post(
    "/{host_id}/actions/reboot",
    response_model=ActionResponse,
    dependencies=[Depends(admin_required)],
)
async def reboot_host(
    request: Request,
    host_id: str,
    body: RebootActionRequest,
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    """Reboot a host.

    Requires admin authentication and X-Acting-Principal header.
    Returns 200 with dispatch result.
    """
    acting_principal = request.headers.get("X-Acting-Principal", "").strip()
    if not acting_principal:
        raise HTTPException(status_code=400, detail="acting_principal_required")

    principal = Principal(user_id=acting_principal)
    targets = HostListSelector(host_ids=[host_id])
    payload = RebootPayload(delay_s=body.delay_s, reason=body.reason)
    idempotency_key = request.headers.get("Idempotency-Key")


    state = get_app_state(request)
    result = await state.api_dispatcher.dispatch(
        session,
        principal=principal,
        targets=targets,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    await session.commit()

    return ActionResponse(
        task_id=result.task_id,
        dispatched=result.dispatched,
        denied=result.denied,
        pending_approval_ids=result.pending_approval_ids,
    )


@router.post(
    "/{host_id}/actions/shell-exec",
    response_model=ActionResponse,
    dependencies=[Depends(admin_required)],
)
async def shell_exec_host(
    request: Request,
    host_id: str,
    body: ShellExecActionRequest,
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    """Execute a shell command on a host.

    Requires admin authentication and X-Acting-Principal header.
    High-risk action requiring approval. Returns 200 with dispatch result.
    """
    acting_principal = request.headers.get("X-Acting-Principal", "").strip()
    if not acting_principal:
        raise HTTPException(status_code=400, detail="acting_principal_required")

    principal = Principal(user_id=acting_principal)
    targets = HostListSelector(host_ids=[host_id])
    payload = ShellExecPayload(command=body.command, timeout_s=body.timeout_s)
    idempotency_key = request.headers.get("Idempotency-Key")


    state = get_app_state(request)
    result = await state.api_dispatcher.dispatch(
        session,
        principal=principal,
        targets=targets,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    await session.commit()

    return ActionResponse(
        task_id=result.task_id,
        dispatched=result.dispatched,
        denied=result.denied,
        pending_approval_ids=result.pending_approval_ids,
    )


@router.post(
    "/{host_id}/actions/pkg-update",
    response_model=ActionResponse,
    dependencies=[Depends(admin_required)],
)
async def pkg_update_host(
    request: Request,
    host_id: str,
    body: PkgUpdateActionRequest,
    session: AsyncSession = Depends(get_session),
) -> ActionResponse:
    """Update packages on a host.

    Requires admin authentication and X-Acting-Principal header.
    Returns 200 with dispatch result.
    """
    acting_principal = request.headers.get("X-Acting-Principal", "").strip()
    if not acting_principal:
        raise HTTPException(status_code=400, detail="acting_principal_required")

    principal = Principal(user_id=acting_principal)
    targets = HostListSelector(host_ids=[host_id])
    payload = PkgUpdatePayload(classes=tuple(body.classes))
    idempotency_key = request.headers.get("Idempotency-Key")


    state = get_app_state(request)
    result = await state.api_dispatcher.dispatch(
        session,
        principal=principal,
        targets=targets,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    await session.commit()

    return ActionResponse(
        task_id=result.task_id,
        dispatched=result.dispatched,
        denied=result.denied,
        pending_approval_ids=result.pending_approval_ids,
    )
