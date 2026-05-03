"""Tasks API routes."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select

from server.app.api.middleware.admin_auth import admin_required
from server.app.dispatcher.dispatcher import (
    RebootPayload,
    ShellExecPayload,
    PkgUpdatePayload,
)
from server.app.dispatcher.targets import (
    HostListSelector,
    GroupSelector,
    TagSelector,
)
from server.app.models import Task, TaskRun, Command
from server.app.models.task import TaskKind, TaskStatus, TaskRisk
from server.app.models.task_run import TaskRunStatus
from server.app.models.command import CommandStatus
from server.app.pagination import apply_cursor, build_page
from server.app.rbac.provider import Principal


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


class TasksPage(BaseModel):
    """Paginated response for list tasks."""

    items: list[TaskListItem]
    next_cursor: str | None


class TaskDispatchRequest(BaseModel):
    """Request body for dispatching a task."""

    model_config = ConfigDict(extra="forbid")

    targets: dict[str, object] | None = None


class DispatchResult(BaseModel):
    """Result from dispatching a task."""

    task_id: str
    dispatched: int
    denied: int
    pending_approval_ids: list[str]


class TaskCancelOut(BaseModel):
    """Response from cancel endpoint."""

    task_id: str
    cancelled_count: int


class TaskResultItem(BaseModel):
    """Single result item."""

    host_id: str
    status: str
    last_command_id: str
    error: str | None = None


class TaskResultsOut(BaseModel):
    """Response from results endpoint."""

    results: list[TaskResultItem]


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
    _: str = Depends(admin_required),
) -> TasksPage:
    """List tasks with cursor pagination.

    Requires admin authentication.
    Supports ?cursor= and ?limit= query params (limit default 100, max 500).
    Returns next_cursor if more items exist.
    """
    limit = min(max(1, limit), 500)

    sm = _sessionmaker(request)
    async with sm() as session:
        query = select(Task)
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


@router.post("/{task_id}/dispatch", response_model=DispatchResult)
async def dispatch_task(
    request: Request,
    task_id: str,
    body: TaskDispatchRequest,
    _: str = Depends(admin_required),
) -> DispatchResult:
    """Dispatch a task now.

    Requires X-Acting-Principal header for actor identity.
    Returns 503 if dispatcher not available.
    Returns 400 if X-Acting-Principal missing.
    Returns 404 if task not found.
    Returns 400 if task kind or target selector unsupported.
    """
    _principal = _get_acting_principal(request)

    dispatcher = _dispatcher(request)
    if dispatcher is None:
        raise HTTPException(
            status_code=503,
            detail="Dispatcher not available",
        )

    # Load Task from DB
    sm = _sessionmaker(request)
    async with sm() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Build payload object from task.kind and task.payload
        payload: RebootPayload | ShellExecPayload | PkgUpdatePayload

        if task.kind == TaskKind.REBOOT:
            payload = RebootPayload(
                delay_s=int(task.payload.get("delay_s", 0)),
                reason=str(task.payload.get("reason", "")),
            )
        elif task.kind == TaskKind.SHELL_EXEC:
            payload = ShellExecPayload(
                command=str(task.payload.get("command", "")),
                timeout_s=int(task.payload.get("timeout_s", 60)),
            )
        elif task.kind == TaskKind.PKG_UPDATE:
            classes_raw = task.payload.get("classes", [])
            classes_list = classes_raw if isinstance(classes_raw, list) else []
            payload = PkgUpdatePayload(
                classes=tuple(str(c) for c in classes_list),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="unsupported_task_kind",
            )

        # Build selector from body.targets (if provided) or task.target_selector
        selector_dict = body.targets if body.targets is not None else task.target_selector

        # Type hint for selector variable
        targets: HostListSelector | GroupSelector | TagSelector

        if "host_id" in selector_dict:
            host_id_v = selector_dict["host_id"]
            if not isinstance(host_id_v, str):
                raise HTTPException(status_code=400, detail="unsupported_selector_shape")
            targets = HostListSelector(host_ids=[host_id_v])
        elif "host_ids" in selector_dict:
            raw = selector_dict.get("host_ids", [])
            if not isinstance(raw, list) or not all(isinstance(h, str) for h in raw):
                raise HTTPException(status_code=400, detail="unsupported_selector_shape")
            targets = HostListSelector(host_ids=list(raw))
        elif "group_id" in selector_dict:
            gid = selector_dict["group_id"]
            if not isinstance(gid, str):
                raise HTTPException(status_code=400, detail="unsupported_selector_shape")
            include_sub = selector_dict.get("include_subgroups", True)
            if not isinstance(include_sub, bool):
                raise HTTPException(status_code=400, detail="unsupported_selector_shape")
            targets = GroupSelector(group_id=gid, include_subgroups=include_sub)
        elif "tag" in selector_dict:
            # Tag selector
            tag_dict = selector_dict["tag"]
            if isinstance(tag_dict, dict) and "key" in tag_dict and "value" in tag_dict:
                targets = TagSelector(
                    key=tag_dict["key"],
                    value=tag_dict["value"],
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="unsupported_selector_shape",
                )
        else:
            raise HTTPException(
                status_code=400,
                detail="unsupported_selector_shape",
            )

        # Construct Principal from acting principal header
        principal = Principal(user_id=_principal)

        # Get idempotency key from header
        idempotency_key = request.headers.get("Idempotency-Key")

        # Call dispatcher.dispatch
        result = await dispatcher.dispatch(
            session,
            principal=principal,
            targets=targets,
            payload=payload,
            idempotency_key=idempotency_key,
        )

        # Commit session
        await session.commit()

    # Return result with real counts
    return DispatchResult(
        task_id=result.task_id,
        dispatched=len(result.dispatched),
        denied=len(result.denied),
        pending_approval_ids=result.pending_approval_ids,
    )


@router.post("/{task_id}/cancel", response_model=TaskCancelOut)
async def cancel_task(
    request: Request,
    task_id: str,
    _: str = Depends(admin_required),
) -> TaskCancelOut:
    """Cancel a task: mark all in-flight Commands as CANCELLED.

    Requires X-Acting-Principal header.
    Returns 400 if X-Acting-Principal missing.
    """
    _principal = _get_acting_principal(request)

    sm = _sessionmaker(request)
    async with sm() as session:
        # Get all TaskRuns for this task
        task_runs = (
            await session.execute(
                select(TaskRun).where(TaskRun.task_id == task_id)
            )
        ).scalars().all()

        cancelled_count = 0
        for tr in task_runs:
            # Cancel both QUEUED and IN_FLIGHT — QUEUED commands haven't been
            # popped yet but would otherwise dispatch on the next loop tick.
            cmds = (
                await session.execute(
                    select(Command).where(
                        and_(
                            Command.task_run_id == tr.id,
                            Command.status.in_(
                                [CommandStatus.QUEUED, CommandStatus.IN_FLIGHT]
                            ),
                        )
                    )
                )
            ).scalars().all()

            for cmd in cmds:
                cmd.status = CommandStatus.CANCELLED
                cancelled_count += 1

        await session.commit()

    return TaskCancelOut(
        task_id=task_id,
        cancelled_count=cancelled_count,
    )


@router.get("/{task_id}/results", response_model=TaskResultsOut)
async def get_task_results(
    request: Request,
    task_id: str,
    _: str = Depends(admin_required),
) -> TaskResultsOut:
    """Get aggregated results by host for a task.

    Shows last Command status per host across all TaskRuns.
    """
    sm = _sessionmaker(request)
    async with sm() as session:
        # Get all TaskRuns for this task
        task_runs = (
            await session.execute(
                select(TaskRun).where(TaskRun.task_id == task_id)
            )
        ).scalars().all()

        results_dict: dict[str, TaskResultItem] = {}

        # For each TaskRun, find the latest Command per host
        for tr in task_runs:
            latest_cmd = (
                await session.execute(
                    select(Command)
                    .where(Command.task_run_id == tr.id)
                    .order_by(Command.sequence.desc())
                    .limit(1)
                )
            ).scalar()

            if latest_cmd:
                results_dict[tr.host_id] = TaskResultItem(
                    host_id=tr.host_id,
                    status=latest_cmd.status.value,
                    last_command_id=latest_cmd.id,
                    error=None,
                )

    return TaskResultsOut(results=list(results_dict.values()))
