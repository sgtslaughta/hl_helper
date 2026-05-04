"""Task action endpoints: dispatch, cancel, results."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select

from server.app.api.middleware.admin_auth import admin_required
from server.app.dispatcher.dispatcher import (
    PkgUpdatePayload,
    RebootPayload,
    ShellExecPayload,
)
from server.app.dispatcher.targets import (
    GroupSelector,
    HostListSelector,
    TagSelector,
)
from server.app.models import Command, Task, TaskRun
from server.app.models.command import CommandStatus
from server.app.models.task import TaskKind
from server.app.rbac.provider import Principal

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


class TaskDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: dict[str, object] | None = None


class DispatchResult(BaseModel):
    task_id: str
    dispatched: int
    denied: int
    pending_approval_ids: list[str]


class TaskCancelOut(BaseModel):
    task_id: str
    cancelled_count: int


class TaskResultItem(BaseModel):
    host_id: str
    status: str
    last_command_id: str
    error: str | None = None


class TaskResultsOut(BaseModel):
    results: list[TaskResultItem]


def _sessionmaker(request: Request):  # type: ignore[no-untyped-def]
    state = getattr(request.app.state, "app_state", None)
    if state is not None and getattr(state, "sessionmaker", None) is not None:
        return state.sessionmaker
    return request.app.state.sessionmaker


def _dispatcher(request: Request):  # type: ignore[no-untyped-def]
    state = getattr(request.app.state, "app_state", None)
    if state is not None:
        d = getattr(state, "api_dispatcher", None)
        if d is not None:
            return d
    return getattr(request.app.state, "dispatcher", None)


def _get_acting_principal(request: Request) -> str:
    principal = (request.headers.get("X-Acting-Principal") or "").strip()
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="acting_principal_required",
        )
    return principal


@router.post("/{task_id}/dispatch", response_model=DispatchResult)
async def dispatch_task(
    request: Request,
    task_id: str,
    body: TaskDispatchRequest,
    _: str = Depends(admin_required),
) -> DispatchResult:
    """Dispatch a task now."""
    _principal = _get_acting_principal(request)

    dispatcher = _dispatcher(request)
    if dispatcher is None:
        raise HTTPException(status_code=503, detail="Dispatcher not available")

    sm = _sessionmaker(request)
    async with sm() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

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
            payload = PkgUpdatePayload(classes=tuple(str(c) for c in classes_list))
        else:
            raise HTTPException(status_code=400, detail="unsupported_task_kind")

        selector_dict = body.targets if body.targets is not None else task.target_selector
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
            tag_dict = selector_dict["tag"]
            if isinstance(tag_dict, dict) and "key" in tag_dict and "value" in tag_dict:
                targets = TagSelector(key=tag_dict["key"], value=tag_dict["value"])
            else:
                raise HTTPException(status_code=400, detail="unsupported_selector_shape")
        else:
            raise HTTPException(status_code=400, detail="unsupported_selector_shape")

        principal = Principal(user_id=_principal)
        idempotency_key = request.headers.get("Idempotency-Key")
        result = await dispatcher.dispatch(
            session,
            principal=principal,
            targets=targets,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        await session.commit()

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
    """Cancel a task: mark all in-flight Commands as CANCELLED."""
    _principal = _get_acting_principal(request)

    sm = _sessionmaker(request)
    async with sm() as session:
        task_runs = (
            await session.execute(select(TaskRun).where(TaskRun.task_id == task_id))
        ).scalars().all()

        cancelled_count = 0
        for tr in task_runs:
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

    return TaskCancelOut(task_id=task_id, cancelled_count=cancelled_count)


@router.get("/{task_id}/results", response_model=TaskResultsOut)
async def get_task_results(
    request: Request,
    task_id: str,
    _: str = Depends(admin_required),
) -> TaskResultsOut:
    """Get aggregated last-command-per-host for a task."""
    sm = _sessionmaker(request)
    async with sm() as session:
        task_runs = (
            await session.execute(select(TaskRun).where(TaskRun.task_id == task_id))
        ).scalars().all()

        results_dict: dict[str, TaskResultItem] = {}
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
