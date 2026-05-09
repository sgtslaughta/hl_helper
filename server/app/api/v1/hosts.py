"""Host management endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
from server.app.models.advisory import Advisory
from server.app.models.host import Host
from server.app.models.host_advisory import HostAdvisory
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


class HostAdvisoryOut(BaseModel):
    """Host advisory with embedded advisory details.

    Field naming is duplicated (e.g. ``severity`` and ``advisory_severity``)
    so the JSON shape matches the webui's HostAdvisory interface while
    older callers reading ``advisory_*`` keep working.
    """

    id: int
    host_id: str
    advisory_id: str
    package: str
    ecosystem: str
    current_version: str
    fixed_version: str | None = None
    status: str
    suppressed_until: datetime | None = None
    suppressed_by: str | None = None
    suppressed_reason: str | None = None
    advisory_severity: str
    advisory_summary: str
    advisory_kev: bool
    advisory_epss: float | None
    # ---- aliases consumed by the webui ----
    severity: str
    summary: str
    package_name: str
    epss: float | None
    kev: bool


class HostAdvisoryListResponse(BaseModel):
    """Response wrapper for host advisory list."""

    items: list[HostAdvisoryOut]


class HostCertOut(BaseModel):
    """Host certificate lifecycle state."""

    serial: str | None
    issued_at: datetime | None  # cert_rotated_at OR enrolled_at
    expires_at: datetime | None
    rotation_count: int
    last_rotated_at: datetime | None
    last_reenroll_at: datetime | None
    status: str  # healthy | rotating | halted | expired


async def _emit_dispatch_ticker(
    request: "Request",
    host_id: str,
    action: str,
    *,
    actor: str | None = None,
    task_id: str | None = None,
    severity: str = "info",
    detail: str | None = None,
) -> None:
    """Best-effort: publish a ticker event for an action dispatch.

    Resolves hostname from the DB; falls back to an id prefix if the host
    row isn't available. Logs (not raises) on failure — ticker emit must
    never break the dispatch response itself.
    """
    import logging as _logging

    _log = _logging.getLogger(__name__)
    try:
        from server.app.events.ticker import format_action_dispatch, publish_ticker

        state = get_app_state(request)
        bus = getattr(state, "bus", None)
        if bus is None:
            _log.warning("dispatch_ticker.no_bus", extra={"action": action, "host_id": host_id})
            return
        async with state.sessionmaker() as s:
            host = await s.get(Host, host_id)
            hostname = host.hostname if host else host_id[:8]
        fmt = format_action_dispatch(
            action=action,
            host_id=host_id,
            hostname=hostname,
            actor=actor,
            task_id=task_id,
            severity=severity,  # type: ignore[arg-type]
            detail=detail,
        )
        await publish_ticker(bus, **fmt)  # type: ignore[arg-type]
        _log.info(
            "dispatch_ticker.published",
            extra={"action": action, "host_id": host_id, "task_id": task_id},
        )
    except Exception:
        _log.exception("dispatch_ticker.failed", extra={"action": action, "host_id": host_id})


async def _request_risk_recompute(
    request: "Request",
    host_id: str,
    *,
    trigger_reason: str,
) -> None:
    """Best-effort: nudge the recomputer for a host. Never raises."""
    import logging as _logging

    _log = _logging.getLogger(__name__)
    try:
        state = get_app_state(request)
        rc = getattr(state, "risk_recomputer", None)
        if rc is None:
            return
        await rc.request(host_id, trigger_reason=trigger_reason)
    except Exception:
        _log.exception(
            "risk.request_failed",
            extra={"host_id": host_id, "trigger_reason": trigger_reason},
        )


def _build_host_advisory_out(ha: Any, adv: Any) -> HostAdvisoryOut:
    """Compose a HostAdvisoryOut from a HostAdvisory row + Advisory row.

    Tolerates a missing Advisory (split-DB race / orphaned ID) by falling
    back to placeholder values.
    """
    severity = adv.severity if adv else "unknown"
    if adv is not None:
        summary = (adv.summary or "").strip()
        if not summary and getattr(adv, "description_md", None):
            for _line in (adv.description_md or "").splitlines():
                _line = _line.strip().lstrip("# ").strip()
                if _line:
                    summary = _line[:500]
                    break
    else:
        summary = ""
    epss = adv.epss if adv else None
    kev = bool(adv.kev) if adv else False
    return HostAdvisoryOut(
        id=ha.id,
        host_id=ha.host_id,
        advisory_id=ha.advisory_id,
        package=ha.package,
        ecosystem=ha.ecosystem,
        current_version=ha.current_version,
        fixed_version=ha.fixed_version,
        status=ha.status,
        suppressed_until=ha.suppressed_until,
        suppressed_by=ha.suppressed_by,
        suppressed_reason=ha.suppressed_reason,
        advisory_severity=severity,
        advisory_summary=summary,
        advisory_kev=kev,
        advisory_epss=epss,
        severity=severity,
        summary=summary,
        package_name=ha.package,
        epss=epss,
        kev=kev,
    )


class SuppressHostAdvisoryRequest(BaseModel):
    """Request to suppress a host advisory."""

    reason: str
    expires_at: datetime


# ===== Dependency providers (can be overridden in tests) =====
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Get database session from app state."""

    state = get_app_state(request)
    async with state.sessionmaker() as session:
        yield session


def get_agent_bridge(request: Request):
    """Get agent_bridge from app state."""
    return get_app_state(request).agent_bridge


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


@router.get("/{host_id}/cert", response_model=HostCertOut)
async def get_host_cert(
    host_id: str,
    actor: str = Depends(admin_required),
    session: AsyncSession = Depends(get_session),
) -> HostCertOut:
    """Get certificate lifecycle state for a host."""
    row = await session.get(Host, host_id)
    if row is None:
        raise HTTPException(status_code=404, detail="host_not_found")

    now = datetime.now(timezone.utc)
    expires = row.cert_expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if expires is None:
        status_str = "halted"
    elif expires < now:
        status_str = "expired"
    else:
        status_str = "healthy"

    issued = row.cert_rotated_at or row.enrolled_at
    if issued is not None and issued.tzinfo is None:
        issued = issued.replace(tzinfo=timezone.utc)

    return HostCertOut(
        serial=row.cert_serial,
        issued_at=issued,
        expires_at=expires,
        rotation_count=row.cert_rotation_count or 0,
        last_rotated_at=row.cert_rotated_at,
        last_reenroll_at=row.last_reenroll_at,
        status=status_str,
    )


@router.post("/{host_id}/cert/rotate-now", status_code=202)
async def rotate_cert_now(
    host_id: str,
    actor: str = Depends(admin_required),
    session: AsyncSession = Depends(get_session),
    bridge=Depends(get_agent_bridge),
):
    """Request immediate certificate rotation for a host.

    Returns 202 Accepted with delivery status. If the host is offline,
    delivered will be False.
    """
    row = await session.get(Host, host_id)
    if row is None:
        raise HTTPException(status_code=404, detail="host_not_found")

    delivered = await bridge.push_run_cert_rotate(host_id, reason="operator-initiated")
    return {"delivered": bool(delivered)}


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
    request: Request,
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
    await _emit_dispatch_ticker(
        request, host_id, "resurvey", actor=actor, task_id=task.id, severity="info"
    )
    await _request_risk_recompute(request, host_id, trigger_reason="resurvey")
    return {"status": "queued", "task_id": task.id}


@router.post("/{host_id}/rescan", status_code=202)
async def rescan_host(
    request: Request,
    host_id: str,
    actor: str = Depends(admin_required),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Request a fresh inventory + posture scan from the connected agent.

    Pushes RunInventory to the agent (packages, containers, host facts);
    advisory matcher fires server-side after ingest. Creates a Task + TaskRun
    so the rescan appears in the host task list. 202 if queued, 409 if the
    agent has no live stream.
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
        run_inventory=agent_bridge_pb2.RunInventory(
            reason="manual",
            include_lang=False,
        )
    )
    if not _ab.push_control(host_id, msg):
        raise HTTPException(status_code=409, detail="host_not_connected")

    task = Task(
        id=str(uuid4()),
        kind=TaskKind.CUSTOM,
        created_by=actor,
        status=TaskStatus.RUNNING,
        payload={"action": "rescan", "host_id": host_id},
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
    await _emit_dispatch_ticker(
        request, host_id, "rescan", actor=actor, task_id=task.id, severity="info"
    )
    await _request_risk_recompute(request, host_id, trigger_reason="rescan")
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

    await _emit_dispatch_ticker(
        request,
        host_id,
        "reboot",
        actor=f"user:{principal.user_id}",
        task_id=result.task_id,
        severity="warn",
        detail=body.reason or None,
    )
    await _request_risk_recompute(request, host_id, trigger_reason="reboot")

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

    await _emit_dispatch_ticker(
        request,
        host_id,
        "privileged shell command" if body.as_root else "shell command",
        actor=f"user:{principal.user_id}",
        task_id=result.task_id,
        severity="warn" if body.as_root else "info",
    )
    await _request_risk_recompute(request, host_id, trigger_reason="shell_exec")

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

    await _emit_dispatch_ticker(
        request,
        host_id,
        "package update",
        actor=f"user:{principal.user_id}",
        task_id=result.task_id,
        severity="info",
        detail=", ".join(body.classes) if body.classes else None,
    )
    await _request_risk_recompute(request, host_id, trigger_reason="pkg_update")

    return ActionResponse(
        task_id=result.task_id,
        dispatched=result.dispatched,
        denied=result.denied,
        pending_approval_ids=result.pending_approval_ids,
    )

# ===== Host Advisories =====


@router.get("/{host_id}/advisories", response_model=HostAdvisoryListResponse)
async def list_host_advisories(
    request: Request,
    host_id: str,
    status: str = Query("open"),
    severity: str | None = Query(None),
    _: str = Depends(admin_required),
) -> HostAdvisoryListResponse:
    """List advisories for a host. Joins host_advisories (fleet) with the
    Advisory rows from the catalog DB in a second query so the same code path
    works for SQLite split files and a unified Postgres deployment."""
    app_state = get_app_state(request)

    async with app_state.sessionmaker() as session:
        q = select(HostAdvisory).where(HostAdvisory.host_id == host_id)
        if status:
            q = q.where(HostAdvisory.status == status)
        host_advisories = list((await session.execute(q)).scalars().all())

    if not host_advisories:
        return HostAdvisoryListResponse(items=[])

    advisory_ids = list({ha.advisory_id for ha in host_advisories})
    catalog_sm = app_state.catalog_sessionmaker or app_state.sessionmaker
    async with catalog_sm() as cat_session:
        q_adv = select(Advisory).where(Advisory.id.in_(advisory_ids))
        if severity:
            q_adv = q_adv.where(Advisory.severity == severity)
        adv_rows = list((await cat_session.execute(q_adv)).scalars().all())
    by_id = {a.id: a for a in adv_rows}

    items = []
    for ha in host_advisories:
        adv = by_id.get(ha.advisory_id)
        if adv is None and severity:
            # severity filter excluded this advisory — drop the host_advisory too
            continue
        items.append(_build_host_advisory_out(ha, adv))
    return HostAdvisoryListResponse(items=items)


@router.post("/{host_id}/advisories/{id}/suppress", response_model=HostAdvisoryOut)
async def suppress_host_advisory(
    request: Request,
    host_id: str,
    id: int,
    body: SuppressHostAdvisoryRequest,
    actor: str = Depends(admin_required),
) -> HostAdvisoryOut:
    """Suppress a host advisory."""
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as session:
        ha = await session.get(HostAdvisory, id)
        if not ha or ha.host_id != host_id:
            raise HTTPException(status_code=404, detail="Host advisory not found")

        ha.status = "suppressed"
        ha.suppressed_until = body.expires_at
        ha.suppressed_by = actor
        ha.suppressed_reason = body.reason
        await session.commit()

    # Fetch advisory for response from the catalog DB.
    catalog_sm = app_state.catalog_sessionmaker or app_state.sessionmaker
    async with catalog_sm() as cat_session:
        adv = await cat_session.get(Advisory, ha.advisory_id)

    return _build_host_advisory_out(ha, adv)


@router.post("/{host_id}/advisories/{id}/unsuppress", response_model=HostAdvisoryOut)
async def unsuppress_host_advisory(
    request: Request,
    host_id: str,
    id: int,
    _: str = Depends(admin_required),
) -> HostAdvisoryOut:
    """Unsuppress a host advisory."""
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as session:
        ha = await session.get(HostAdvisory, id)
        if not ha or ha.host_id != host_id:
            raise HTTPException(status_code=404, detail="Host advisory not found")

        ha.status = "open"
        ha.suppressed_until = None
        ha.suppressed_by = None
        ha.suppressed_reason = None
        await session.commit()

    # Fetch advisory for response from the catalog DB.
    catalog_sm = app_state.catalog_sessionmaker or app_state.sessionmaker
    async with catalog_sm() as cat_session:
        adv = await cat_session.get(Advisory, ha.advisory_id)

    return _build_host_advisory_out(ha, adv)
