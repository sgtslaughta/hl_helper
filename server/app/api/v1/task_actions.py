"""Task action endpoints: dispatch, cancel, results."""

from __future__ import annotations

from datetime import datetime, timezone

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


# Detailed per-host result with captured stdout/stderr.
_OUTPUT_CAP_BYTES = 64 * 1024


class TaskResultDetail(BaseModel):
    host_id: str
    command_id: str
    status: str
    exit_code: int | None
    received_at: datetime
    stdout: str
    stdout_truncated: bool
    stderr: str
    stderr_truncated: bool
    rejection_reason: str | None = None


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


def _decode_blob(blob: bytes | None) -> tuple[str, bool]:
    """Decode a stdout/stderr blob; cap at _OUTPUT_CAP_BYTES.

    Returns (text, truncated). Non-utf-8 bytes are replaced.
    """
    if not blob:
        return "", False
    truncated = len(blob) > _OUTPUT_CAP_BYTES
    chunk = blob[:_OUTPUT_CAP_BYTES] if truncated else blob
    return chunk.decode("utf-8", errors="replace"), truncated


@router.get("/{task_id}/results/{host_id}", response_model=TaskResultDetail)
async def get_task_result_for_host(
    request: Request,
    task_id: str,
    host_id: str,
    _: str = Depends(admin_required),
) -> TaskResultDetail:
    """Return the latest captured stdout/stderr/exit_code for a host on a task.

    Inventory-style tasks (``resurvey``/``rescan``) don't produce stdout — the
    agent answers with HostSurvey + PackageInventory + ContainerInventory
    envelopes that update host/package/container tables directly. For those,
    synthesize a summary using the latest collected counts so the UI shows
    something useful instead of a 404.
    """
    from server.app.models.host import Host
    from server.app.models.host_container import HostContainer
    from server.app.models.host_package import HostPackage
    from server.app.models.result import Result

    sm = _sessionmaker(request)
    async with sm() as session:
        # Find the latest command for this task+host, then latest result for it.
        run = (
            await session.execute(
                select(TaskRun).where(
                    TaskRun.task_id == task_id, TaskRun.host_id == host_id
                )
            )
        ).scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="task_run_not_found")

        latest_cmd = (
            await session.execute(
                select(Command)
                .where(Command.task_run_id == run.id)
                .order_by(Command.sequence.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        latest_result = None
        if latest_cmd is not None:
            latest_result = (
                await session.execute(
                    select(Result)
                    .where(Result.command_id == latest_cmd.id)
                    .order_by(Result.sequence.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        if latest_result is None:
            # Inventory tasks don't write Result rows — synthesize from snapshot.
            task = await session.get(Task, task_id)
            payload = task.payload if task is not None else {}
            action = (payload or {}).get("action") if isinstance(payload, dict) else None
            if action in ("resurvey", "rescan"):
                host = await session.get(Host, host_id)
                from sqlalchemy import func as _func
                pkg_count = int(
                    (
                        await session.execute(
                            select(_func.count(HostPackage.id)).where(
                                HostPackage.host_id == host_id
                            )
                        )
                    ).scalar_one()
                )
                ctr_count = int(
                    (
                        await session.execute(
                            select(_func.count(HostContainer.id)).where(
                                HostContainer.host_id == host_id
                            )
                        )
                    ).scalar_one()
                )
                survey_at = host.survey_at.isoformat() if host and host.survey_at else "—"
                summary = (
                    f"Inventory collected\n"
                    f"  packages: {pkg_count}\n"
                    f"  containers: {ctr_count}\n"
                    f"  survey_at: {survey_at}\n"
                )
                received_at = run.completed_at or run.started_at or datetime.now(timezone.utc)
                return TaskResultDetail(
                    host_id=host_id,
                    command_id=latest_cmd.id if latest_cmd else "",
                    status=str(run.status),
                    exit_code=0 if str(run.status).lower().endswith("succeeded") else None,
                    received_at=received_at,
                    stdout=summary,
                    stdout_truncated=False,
                    stderr="",
                    stderr_truncated=False,
                    rejection_reason=None,
                )
            raise HTTPException(status_code=404, detail="result_not_found")

    stdout, stdout_trunc = _decode_blob(latest_result.stdout_blob)
    stderr, stderr_trunc = _decode_blob(latest_result.stderr_blob)
    return TaskResultDetail(
        host_id=latest_result.host_id,
        command_id=latest_result.command_id,
        status=latest_result.status,
        exit_code=latest_result.exit_code,
        received_at=latest_result.received_at,
        stdout=stdout,
        stdout_truncated=stdout_trunc,
        stderr=stderr,
        stderr_truncated=stderr_trunc,
        rejection_reason=latest_result.rejection_reason,
    )
