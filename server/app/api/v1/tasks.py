"""Tasks API routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select

from server.app.api.middleware.admin_auth import admin_required
from server.app.models import Task, TaskRun
from server.app.models.agent_release import AgentRelease, ReleaseStatus
from server.app.models.host import Host
from server.app.models.task import TaskKind, TaskStatus, TaskRisk
from server.app.models.task_run import TaskRunStatus
from server.app.pagination import apply_cursor, build_page


def _sessionmaker(request: Request):  # type: ignore[no-untyped-def]
    """Resolve sessionmaker from app.state.app_state (production lifespan) or
    from app.state.sessionmaker directly (tests inject sm directly).
    """
    state = getattr(request.app.state, "app_state", None)
    if state is not None and getattr(state, "sessionmaker", None) is not None:
        return state.sessionmaker
    return request.app.state.sessionmaker


def _dispatcher(request: Request):  # type: ignore[no-untyped-def]
    """Resolve api_dispatcher from app.state.app_state or fall back to direct attr."""
    state = getattr(request.app.state, "app_state", None)
    if state is not None:
        d = getattr(state, "api_dispatcher", None)
        if d is not None:
            return d
    return getattr(request.app.state, "dispatcher", None)

def _task_summary(kind: str, payload: dict[str, object]) -> str:
    """Human-readable one-liner for a task. Truncated to 160 chars."""
    if kind == "shell_exec":
        cmd = str(payload.get("command", "")).strip()
        if cmd:
            return cmd if len(cmd) <= 160 else cmd[:157] + "..."
    elif kind == "reboot":
        reason = str(payload.get("reason", "")).strip()
        delay = payload.get("delay_s")
        s = "reboot"
        if delay:
            s += f" in {delay}s"
        if reason:
            s += f" — {reason}"
        return s[:160]
    elif kind == "pkg_update":
        classes = payload.get("classes")
        if isinstance(classes, list) and classes:
            return f"pkg update: {', '.join(str(c) for c in classes)}"[:160]
        return "pkg update"
    elif kind == "custom":
        action = str(payload.get("action", "")).strip()
        if action == "resurvey":
            return "resurvey host"
        if action:
            return action[:160]
    return ""


router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    """Request body for creating a task."""

    model_config = ConfigDict(extra="forbid")

    kind: TaskKind
    payload: dict[str, object]
    target_selector: dict[str, object]
    risk: TaskRisk = TaskRisk.LOW
    requires_approval: bool = False
    created_by: str | None = None


class TaskUpdate(BaseModel):
    """Request body for updating a task."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, object] | None = None
    target_selector: dict[str, object] | None = None
    risk: TaskRisk | None = None
    requires_approval: bool | None = None


class TaskOut(BaseModel):
    """Task object in responses."""

    id: str
    kind: str
    payload: dict[str, object]
    target_selector: dict[str, object]
    status: str
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    risk: str
    requires_approval: bool
    idempotency_key: str | None


class TaskListItem(BaseModel):
    """Task item in list responses."""

    id: str
    kind: str
    status: str
    created_at: datetime
    risk: str
    summary: str = ""


class TasksPage(BaseModel):
    """Paginated response for list tasks."""

    items: list[TaskListItem]
    next_cursor: str | None


async def _validate_agent_update(payload: dict[str, object], host: Host, session) -> None:
    """Validate AGENT_UPDATE task payload.

    Checks:
    - release_id (UUID) is required and references existing AgentRelease
    - Release must not be yanked
    - Release OS/arch must match host OS/arch
    - If host.agent_version == release.version and force is not true, reject

    Raises HTTPException 400 on validation failure.
    """
    rid_raw = payload.get("release_id")
    if not rid_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="release_id required",
        )

    # Parse release_id as UUID
    try:
        rid = UUID(str(rid_raw)) if not isinstance(rid_raw, UUID) else rid_raw
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="release_id invalid",
        )

    # Fetch release
    rel = await session.get(AgentRelease, str(rid))
    if not rel:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="release not found",
        )

    # Check if yanked
    if rel.status == ReleaseStatus.YANKED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="release is yanked",
        )

    # Check OS match
    host_os = (host.labels or {}).get("os")
    if host_os and rel.os != host_os:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"os mismatch: host={host_os} release={rel.os}",
        )

    # Check arch match
    host_arch = (host.labels or {}).get("arch")
    if host_arch and rel.arch != host_arch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"arch mismatch: host={host_arch} release={rel.arch}",
        )

    # Check version — if same and force is not true, reject
    if not payload.get("force") and host.agent_version == rel.version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="host already on this version (use force=true)",
        )


def _get_acting_principal(request: Request) -> str:
    """Extract and validate X-Acting-Principal header.

    Raises HTTPException 400 if missing.
    """
    principal = (request.headers.get("X-Acting-Principal") or "").strip()
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="acting_principal_required",
        )
    return principal


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: Request,
    body: TaskCreate,
    _: str = Depends(admin_required),
) -> TaskOut:
    """Create a new task.

    Requires admin authentication.
    """
    sm = _sessionmaker(request)
    task_id = str(uuid4())
    async with sm() as session:
        # Validate AGENT_UPDATE tasks before persistence
        if body.kind == TaskKind.AGENT_UPDATE:
            # Extract host_id from target_selector
            host_id = body.target_selector.get("host_id")
            if host_id:
                host = await session.get(Host, str(host_id))
                if host:
                    await _validate_agent_update(body.payload, host, session)

        task = Task(
            id=task_id,
            kind=body.kind,
            payload=body.payload,
            target_selector=body.target_selector,
            risk=body.risk,
            requires_approval=body.requires_approval,
            created_by=body.created_by,
            status=TaskStatus.PENDING,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)

    return TaskOut(
        id=task.id,
        kind=task.kind.value,
        payload=task.payload,
        target_selector=task.target_selector,
        status=task.status.value,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
        risk=task.risk.value,
        requires_approval=task.requires_approval,
        idempotency_key=task.idempotency_key,
    )


@router.get("", response_model=TasksPage)
async def list_tasks(
    request: Request,
    cursor: str | None = None,
    limit: int = 100,
    host_id: str | None = None,
    _: str = Depends(admin_required),
) -> TasksPage:
    """List tasks with cursor pagination.

    Requires admin authentication.
    Supports ?cursor= and ?limit= query params (limit default 100, max 500).
    Optional ?host_id= filters to tasks with at least one TaskRun on that host.
    Returns next_cursor if more items exist.
    """
    limit = min(max(1, limit), 500)

    sm = _sessionmaker(request)
    async with sm() as session:
        query = select(Task)
        if host_id is not None:
            query = (
                query.join(TaskRun, TaskRun.task_id == Task.id)
                .where(TaskRun.host_id == host_id)
                .distinct()
            )
        query = apply_cursor(
            query,
            sort_column=Task.created_at,
            id_column=Task.id,
            cursor=cursor,
            limit=limit,
            descending=True,
        )
        rows = (await session.execute(query)).scalars().all()

    page = build_page(rows, limit=limit, sort_attr="created_at", id_attr="id")

    return TasksPage(
        items=[
            TaskListItem(
                id=r.id,
                kind=r.kind.value,
                status=r.status.value,
                created_at=r.created_at,
                risk=r.risk.value,
                summary=_task_summary(r.kind.value, r.payload),
            )
            for r in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    request: Request,
    task_id: str,
    _: str = Depends(admin_required),
) -> TaskOut:
    """Get a single task by ID.

    Returns 404 if task not found.
    """
    sm = _sessionmaker(request)
    async with sm() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

    return TaskOut(
        id=task.id,
        kind=task.kind.value,
        payload=task.payload,
        target_selector=task.target_selector,
        status=task.status.value,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
        risk=task.risk.value,
        requires_approval=task.requires_approval,
        idempotency_key=task.idempotency_key,
    )


@router.patch("/{task_id}", response_model=TaskOut)
async def patch_task(
    request: Request,
    task_id: str,
    body: TaskUpdate,
    _: str = Depends(admin_required),
) -> TaskOut:
    """Update a task (payload, target_selector, risk, requires_approval).

    Returns 404 if task not found.
    """
    sm = _sessionmaker(request)
    async with sm() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if body.payload is not None:
            task.payload = body.payload
        if body.target_selector is not None:
            task.target_selector = body.target_selector
        if body.risk is not None:
            task.risk = body.risk
        if body.requires_approval is not None:
            task.requires_approval = body.requires_approval

        await session.commit()
        await session.refresh(task)

    return TaskOut(
        id=task.id,
        kind=task.kind.value,
        payload=task.payload,
        target_selector=task.target_selector,
        status=task.status.value,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
        risk=task.risk.value,
        requires_approval=task.requires_approval,
        idempotency_key=task.idempotency_key,
    )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    request: Request,
    task_id: str,
    _: str = Depends(admin_required),
) -> None:
    """Delete a task.

    Returns 404 if task not found.
    Returns 409 if task has running TaskRuns.
    """
    sm = _sessionmaker(request)
    async with sm() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Check for active TaskRuns — both PENDING (not yet started) and RUNNING
        # are user-visible "in flight"; deleting the parent task would orphan them.
        running_runs = (
            await session.execute(
                select(TaskRun).where(
                    and_(
                        TaskRun.task_id == task_id,
                        TaskRun.status.in_(
                            [TaskRunStatus.PENDING, TaskRunStatus.RUNNING]
                        ),
                    )
                )
            )
        ).scalars().all()

        if running_runs:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete task with running TaskRuns",
            )

        await session.delete(task)
        await session.commit()
