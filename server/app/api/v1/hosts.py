"""Host management endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    survey: dict[str, Any] | None = None
    survey_at: datetime | None = None
    metrics: dict[str, Any] | None = None
    metrics_at: datetime | None = None
    heartbeat_interval_s: int = 30
    agent_version: str | None = None
    agent_version_updated_at: datetime | None = None
    agent_update_status: str = "idle"
    agent_update_target_version: str | None = None
    pinned_release_id: str | None = None
    sleeping: bool = False
    sleep_until: datetime | None = None


class HostPatchRequest(BaseModel):
    """Patch body for /v1/hosts/{id}."""

    heartbeat_interval_s: int | None = None
    display_name: str | None = None


class RebootActionRequest(BaseModel):
    """Request body for reboot action."""

    delay_s: int = 0
    reason: str = ""


class ShellExecActionRequest(BaseModel):
    """Request body for shell-exec action."""

    command: str
    timeout_s: int = 60
    as_root: bool = False
    reason: str | None = None


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
    now = datetime.now(timezone.utc)
    out: list[HostOut] = []
    for r in rows:
        h = HostOut.model_validate(r)
        # Freshness override: degrade an apparently-healthy host whose last
        # heartbeat is stale. Only touch the "healthy" stored status; leave
        # explicit "online", "warning", "critical", "offline" alone so admins
        # and tests that set those values directly are honored.
        if r.status == "healthy" and r.last_seen_at is not None:
            last = r.last_seen_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age = (now - last).total_seconds()
            if age >= 300:
                h.status = "offline"
            elif age >= 60:
                h.status = "warning"
        out.append(h)
    return out


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


@router.patch("/{host_id}", response_model=HostOut)
async def patch_host(
    host_id: str,
    body: HostPatchRequest,
    actor: str = Depends(admin_required),
    session: AsyncSession = Depends(get_session),
) -> HostOut:
    """Update mutable host fields (``heartbeat_interval_s``, ``display_name``).

    A live ``HeartbeatConfig`` is pushed to the agent on interval change so
    the ticker resets without waiting for the next reconnect.
    """
    host = await session.get(Host, host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="host_not_found")

    pushed_interval: int | None = None
    if body.heartbeat_interval_s is not None:
        ivl = body.heartbeat_interval_s
        if ivl < 5 or ivl > 3600:
            raise HTTPException(
                status_code=400, detail="heartbeat_interval_s must be in [5, 3600]"
            )
        host.heartbeat_interval_s = ivl
        pushed_interval = ivl
    if body.display_name is not None:
        host.display_name = body.display_name
    await session.commit()
    await session.refresh(host)

    if pushed_interval is not None:
        try:
            from server.app.grpc import agent_bridge as _ab
            from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2

            _ab.push_control(
                host_id,
                agent_bridge_pb2.ServerToAgent(
                    hb_config=agent_bridge_pb2.HeartbeatConfig(
                        interval_s=pushed_interval
                    )
                ),
            )
        except Exception:
            pass

    return HostOut.model_validate(host)


@router.post("/{host_id}/resurvey", status_code=202)
async def resurvey_host(
    host_id: str,
    actor: str = Depends(admin_required),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Request a fresh hardware survey from the connected agent.

    Creates a Task + TaskRun row so the operation appears in the host's task
    list with running/succeeded/failed status. 202 if the agent has a live
    stream and the request was queued; 409 otherwise (no buffering for
    later — agent must be online to receive RunSurvey).
    """
    from uuid import uuid4

    from server.app.grpc import agent_bridge as _ab
    from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2
    from server.app.models.task import Task, TaskKind, TaskRisk, TaskStatus
    from server.app.models.task_run import TaskRun, TaskRunStatus

    host = await session.get(Host, host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="host_not_found")

    msg = agent_bridge_pb2.ServerToAgent(
        run_survey=agent_bridge_pb2.RunSurvey(reason="manual")
    )
    if not _ab.push_control(host_id, msg):
        raise HTTPException(status_code=409, detail="host_not_connected")

    task = Task(
        id=str(uuid4()),
        kind=TaskKind.CUSTOM,
        created_by=actor,
        status=TaskStatus.RUNNING,
        payload={"action": "resurvey", "host_id": host_id},
        target_selector={"host_ids": [host_id]},
        risk=TaskRisk.LOW,
        requires_approval=False,
    )
    run = TaskRun(
        id=str(uuid4()),
        task_id=task.id,
        host_id=host_id,
        status=TaskRunStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    session.add(task)
    session.add(run)
    await session.commit()
    return {"status": "queued", "task_id": task.id}


@router.post("/prune-stale", status_code=200)
async def prune_stale_hosts(
    actor: str = Depends(admin_required),
    session: AsyncSession = Depends(get_session),
    older_than_minutes: int = 30,
) -> dict[str, int]:
    """Delete host rows that never produced a heartbeat and were enrolled
    more than ``older_than_minutes`` minutes ago. Useful for cleaning up
    failed-enrollment leftovers from the UI without going through revocation.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max(0, older_than_minutes))
    stmt = select(Host).where(Host.last_seen_at.is_(None), Host.enrolled_at < cutoff)
    rows = (await session.execute(stmt)).scalars().all()
    deleted = 0
    for r in rows:
        await session.delete(r)
        deleted += 1
    await session.commit()
    return {"deleted": deleted}


@router.delete("/{host_id}", status_code=204)
async def delete_host(
    host_id: str,
    reason: str | None = None,
    actor: str = Depends(admin_required),
    service: RevocationService = Depends(get_revocation_service),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Permanently delete a host record.

    Revokes the host's certificate (best-effort, idempotent if already
    revoked) and then removes the row and any group memberships. Use
    POST /v1/hosts/{id}/revoke for soft revocation that preserves history.
    """
    host = await session.get(Host, host_id)
    if host is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="host not found",
        )

    if host.status != "revoked":
        try:
            await service.revoke(
                session, host_id=host_id, actor=actor, reason=reason
            )
        except HostAlreadyRevokedError:
            pass
        except HostNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="host not found",
            )

    from server.app.models.group_membership import GroupMembership

    memberships = await session.execute(
        select(GroupMembership).where(GroupMembership.host_id == host_id)
    )
    for m in memberships.scalars().all():
        await session.delete(m)
    await session.flush()

    await session.delete(host)
    await session.commit()


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
    payload = ShellExecPayload(
        command=body.command,
        timeout_s=body.timeout_s,
        as_root=body.as_root,
        reason=(body.reason or "").strip(),
    )
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

    # Write server-side audit entry
    async with state.sessionmaker() as audit_session:
        try:
            action = "exec.elevated.dispatched" if body.as_root else "exec.dispatched"
            await state.audit_chain.append(
                audit_session,
                actor=f"user:{principal.user_id}",
                action=action,
                subject=host_id,
                payload={
                    "command": body.command,
                    "as_root": body.as_root,
                    "reason": payload.reason,
                    "task_id": result.task_id,
                },
            )
            await audit_session.commit()
        except Exception:
            # Audit failure must not break the dispatch response.
            pass

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
