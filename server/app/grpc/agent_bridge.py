"""AgentBridge.Stream RPC handler."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import grpc
import structlog

from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import (
    agent_bridge_pb2,
    agent_bridge_pb2_grpc,
    commands_pb2,
    envelope_pb2,
)

from .dispatcher import CommandDispatcher
from .peer_context import peer_context, peer_serial

if TYPE_CHECKING:
    from server.app.revocation.service import RevocationService
    from .result_handler import ResultHandler

log = structlog.get_logger(__name__)


# Per-host control-message queues. The Stream coroutine drains this queue in
# parallel with the dispatcher's command queue; REST endpoints push entries to
# request a heartbeat-interval change or a manual resurvey on a connected
# host. Empty if the host is offline.
_control_queues: dict[str, "asyncio.Queue[agent_bridge_pb2.ServerToAgent]"] = {}


def is_host_connected(host_id: str) -> bool:
    """Return True if the host currently has an active bidi stream."""
    return host_id in _control_queues


def push_control(host_id: str, msg: agent_bridge_pb2.ServerToAgent) -> bool:
    """Enqueue a ServerToAgent control message for delivery to ``host_id``.

    Returns True if the host has a live stream and the message was queued.
    Returns False if the host is offline (caller should respond accordingly,
    e.g. with a 409 Conflict for a manual resurvey request).
    """
    q = _control_queues.get(host_id)
    if q is None:
        return False
    try:
        q.put_nowait(msg)
    except asyncio.QueueFull:
        return False
    return True


class AgentBridgeService(agent_bridge_pb2_grpc.AgentBridgeServicer):
    """Bidirectional stream handler for agent-server communication."""

    def __init__(
        self,
        dispatcher: CommandDispatcher,
        result_handler: ResultHandler | None = None,
        revocation: RevocationService | None = None,
        sessionmaker: Any | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._result_handler = result_handler
        self._revocation = revocation
        self._sessionmaker = sessionmaker

    async def Stream(
        self,
        request_iterator: AsyncIterable[agent_bridge_pb2.AgentToServer],
        context: Any,  # grpc.aio.ServicerContext
    ) -> AsyncIterator[agent_bridge_pb2.ServerToAgent]:
        """Bidirectional stream: deliver commands to agent, recv acks/results.

        Flow:
          1. Authenticate using SPIFFE peer identity (from client cert).
          2. Check CRL: if cert serial is revoked, abort PERMISSION_DENIED.
          3. Register host with dispatcher; replay unacked commands.
          4. Main loop:
             - Pull command from queue (or recv from agent).
             - When sending command: mark_in_flight.
             - When receiving ack/result: call ack().
             - Watch termination event; abort if set.
          5. On disconnect: unregister host.
        """
        with peer_context(context) as (host_id, spiffe_uri):
            if host_id is None:
                await context.abort(
                    grpc.StatusCode.UNAUTHENTICATED,
                    "peer cert lacks SPIFFE host URI",
                )
                return  # unreachable, satisfies type checker

            # Check CRL before registration
            serial = peer_serial(context)
            if serial and self._revocation and await self._revocation.is_revoked(serial):
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "host revoked")
                return

            try:
                state = await self._dispatcher.register(host_id)
            except RuntimeError as e:
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, str(e))
                return

            try:
                from server.app.observability.metrics import fleet_agent_reconnects_total
                fleet_agent_reconnects_total.inc()
            except Exception:
                pass
            log.info("agent.connected", host_id=host_id, spiffe=spiffe_uri)

            control_q: asyncio.Queue[agent_bridge_pb2.ServerToAgent] = asyncio.Queue(
                maxsize=64
            )
            _control_queues[host_id] = control_q

            # Push initial HeartbeatConfig from DB so the agent adopts the
            # configured interval immediately on every reconnect.
            initial_interval = await self._load_heartbeat_interval(host_id)
            if initial_interval is not None:
                control_q.put_nowait(
                    agent_bridge_pb2.ServerToAgent(
                        hb_config=agent_bridge_pb2.HeartbeatConfig(
                            interval_s=initial_interval
                        )
                    )
                )

            recv_task = asyncio.create_task(
                self._recv_loop(host_id, request_iterator)
            )
            try:
                while True:
                    # Pull next command, control msg, or watch for termination.
                    pull_task = asyncio.create_task(state.queue.get())
                    ctrl_task = asyncio.create_task(control_q.get())
                    term_task = asyncio.create_task(state.terminate_event.wait())
                    done, _pending = await asyncio.wait(
                        {pull_task, ctrl_task, recv_task, term_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if term_task in done:
                        if pull_task in done and pull_task.exception() is None:
                            state.queue.put_nowait(pull_task.result())
                        pull_task.cancel()
                        ctrl_task.cancel()
                        recv_task.cancel()
                        await context.abort(grpc.StatusCode.PERMISSION_DENIED, "host revoked")
                        return

                    if recv_task in done:
                        if pull_task in done and pull_task.exception() is None:
                            state.queue.put_nowait(pull_task.result())
                        pull_task.cancel()
                        ctrl_task.cancel()
                        term_task.cancel()
                        break

                    if ctrl_task in done:
                        # Control messages take priority over commands so a
                        # heartbeat-interval reset or resurvey reaches the
                        # agent without waiting for the next command.
                        if pull_task in done and pull_task.exception() is None:
                            state.queue.put_nowait(pull_task.result())
                        pull_task.cancel()
                        term_task.cancel()
                        yield ctrl_task.result()
                        continue

                    ctrl_task.cancel()
                    cmd: envelope_pb2.CommandEnvelope = pull_task.result()
                    term_task.cancel()
                    await self._dispatcher.mark_in_flight(host_id, cmd)
                    yield agent_bridge_pb2.ServerToAgent(command=cmd)
            finally:
                _control_queues.pop(host_id, None)
                recv_task.cancel()
                await self._dispatcher.unregister(host_id)
                log.info("agent.disconnected", host_id=host_id)

    async def _load_heartbeat_interval(self, host_id: str) -> int | None:
        """Load this host's configured heartbeat interval in seconds, or
        ``None`` if no row exists / sessionmaker is not wired."""
        if self._sessionmaker is None:
            return None
        try:
            from server.app.models.host import Host

            async with self._sessionmaker() as session:
                host = await session.get(Host, host_id)
                if host is None:
                    return None
                return int(getattr(host, "heartbeat_interval_s", 30) or 30)
        except Exception as e:
            log.warning("heartbeat.load_interval_failed", host_id=host_id, error=str(e))
            return None

    async def _recv_loop(
        self,
        host_id: str,
        request_iterator: AsyncIterable[agent_bridge_pb2.AgentToServer],
    ) -> None:
        """Receive and process messages from agent.

        Handles:
          - result: verify signature, persist, audit, then ack.
          - heartbeat: update Host.last_seen_at.
          - other messages: log as unknown.

        Raises:
            Exception: If the stream is closed (normal exit).
        """
        from datetime import datetime, timezone

        log.info("recv_loop.start", host_id=host_id)
        async for msg in request_iterator:
            kind = msg.WhichOneof("msg")
            log.info("recv_loop.msg", host_id=host_id, kind=kind)
            if kind == "result":
                # Result handling: verify signature, persist, audit.
                # Always ack (both accepted and rejected) to avoid retry storm.
                if self._result_handler is not None:
                    from .result_handler import ResultRejectedError

                    try:
                        await self._result_handler.handle(
                            msg.result, expected_host_id=host_id
                        )
                    except ResultRejectedError as e:
                        log.warning(
                            "result.rejected",
                            host_id=host_id,
                            command_id=msg.result.command_id,
                            error=str(e),
                        )
                # Ack regardless of verification result to avoid retry storms.
                # The agent should fix signature issues on its side.
                await self._dispatcher.ack(host_id, msg.result.command_id)
            elif kind == "heartbeat":
                # Update Host.last_seen_at + status + metrics + agent version/update status.
                # Persist HostMetrics so the UI can render live load/mem/disk/uptime without
                # relying on a separate scrape path.
                if self._sessionmaker is not None:
                    from server.app.models.host import Host

                    try:
                        m = msg.heartbeat.metrics
                        metrics_dict = {
                            "load_1": float(m.load_1),
                            "load_5": float(m.load_5),
                            "load_15": float(m.load_15),
                            "mem_used_pct": float(m.mem_used_pct),
                            "disk_used_pct": float(m.disk_used_pct),
                            "uptime_seconds": int(m.uptime_seconds),
                            "net_rx_bps": int(m.net_rx_bps),
                            "net_tx_bps": int(m.net_tx_bps),
                        }
                        async with self._sessionmaker() as session:
                            host = await session.get(Host, host_id)
                            if host:
                                now = datetime.now(timezone.utc)
                                host.last_seen_at = now
                                host.status = "healthy"
                                host.metrics = metrics_dict
                                host.metrics_at = now
                            # Persist agent version and update status
                            await _persist_heartbeat(session, host_id, msg.heartbeat)
                            await session.commit()
                    except Exception as e:
                        log.warning(
                            "heartbeat.update_failed",
                            host_id=host_id,
                            error=str(e),
                        )
            elif kind == "host_survey":
                if self._sessionmaker is not None:
                    from google.protobuf.json_format import MessageToDict
                    from sqlalchemy import select

                    from server.app.models.host import Host
                    from server.app.models.task import Task, TaskStatus
                    from server.app.models.task_run import TaskRun, TaskRunStatus

                    try:
                        survey_dict = MessageToDict(
                            msg.host_survey,
                            preserving_proto_field_name=True,
                        )
                        async with self._sessionmaker() as session:
                            now = datetime.now(timezone.utc)
                            host = await session.get(Host, host_id)
                            if host:
                                host.survey = survey_dict
                                host.survey_at = now

                            # Close out the most recent running resurvey
                            # TaskRun for this host. Match by Task.kind=custom
                            # + payload.action=resurvey rather than reserving
                            # a new TaskKind enum value.
                            stmt = (
                                select(TaskRun, Task)
                                .join(Task, Task.id == TaskRun.task_id)
                                .where(
                                    TaskRun.host_id == host_id,
                                    TaskRun.status == TaskRunStatus.RUNNING,
                                )
                                .order_by(TaskRun.started_at.desc())
                                .limit(5)
                            )
                            for run, task in (await session.execute(stmt)).all():
                                if (
                                    task.kind.value == "custom"
                                    and isinstance(task.payload, dict)
                                    and task.payload.get("action") == "resurvey"
                                ):
                                    run.status = TaskRunStatus.SUCCEEDED
                                    run.finished_at = now
                                    run.summary = "survey collected"
                                    task.status = TaskStatus.SUCCEEDED
                                    break
                            await session.commit()
                    except Exception as e:
                        log.warning(
                            "survey.update_failed",
                            host_id=host_id,
                            error=str(e),
                        )
            else:
                log.warning("agent.unknown_message", host_id=host_id, kind=kind)


# Heartbeat AgentUpdateStatus proto -> model enum mapping
_HB_STATUS_MAP = {
    agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_UNSPECIFIED: "idle",
    agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_IDLE: "idle",
    agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_DOWNLOADING: "downloading",
    agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_SWAPPING: "swapping",
    agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_HEALTHCHECKING: "healthchecking",
    agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_ROLLED_BACK: "rolled_back",
    agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_FAILED: "failed",
}


async def _build_agent_update_cmd(
    payload: dict,
    host_id: str,
    session: Any,
    *,
    public_url: str | None = None,
) -> commands_pb2.AgentUpdateCmd:
    """Build AgentUpdateCmd from a task payload + DB-resolved release.

    Args:
        payload: Task payload dict with 'release_id' and optional 'force'.
        host_id: Target host identifier.
        session: SQLAlchemy async session.
        public_url: Optional public URL. If None, load from config.

    Returns:
        AgentUpdateCmd proto message ready for inclusion in CommandEnvelope.

    Raises:
        RuntimeError: If release is not found or is yanked.
    """
    from server.app.api.v1.agent_releases import make_download_token
    from server.app.models.agent_release import AgentRelease, ReleaseStatus

    # Parse release_id from payload
    release_id = payload.get("release_id")
    if isinstance(release_id, str):
        release_id = release_id
    elif isinstance(release_id, uuid.UUID):
        release_id = str(release_id)
    else:
        raise RuntimeError(f"invalid release_id type: {type(release_id)}")

    # Load release from DB
    rel = await session.get(AgentRelease, release_id)
    if not rel or rel.status == ReleaseStatus.YANKED:
        raise RuntimeError("release unavailable or yanked")

    # Build download URL
    if public_url is None:
        from server.app.settings.config import load_settings
        settings = load_settings()
        public_url = settings.public_url
    binary_url = f"{public_url}/v1/agent-releases/{rel.id}/binary"

    # Create download token
    token = make_download_token(rel.id, host_id)

    return commands_pb2.AgentUpdateCmd(
        release_id=str(rel.id),
        manifest_json=rel.manifest_json,
        manifest_sig=rel.manifest_sig,
        binary_url=binary_url,
        download_token=token,
        expected_sha256=rel.sha256,
        expected_size=rel.size,
        force=bool(payload.get("force", False)),
    )


async def _persist_heartbeat(
    session: Any,
    host_id: str,
    hb: agent_bridge_pb2.Heartbeat,
) -> None:
    """Persist heartbeat version and update status to Host model.

    Args:
        session: SQLAlchemy async session.
        host_id: Host identifier.
        hb: Heartbeat proto message from agent.
    """
    from server.app.models.host import Host, AgentUpdateStatus

    host = await session.get(Host, host_id)
    if not host:
        return

    # Update agent version if present (top-level + mirrored into labels for
    # legacy code paths and FleetRow display).
    if hb.agent_version and host.agent_version != hb.agent_version:
        host.agent_version = hb.agent_version
        host.agent_version_updated_at = datetime.now(timezone.utc)
        labels = dict(host.labels or {})
        labels["agent_version"] = hb.agent_version
        host.labels = labels

    # Map proto update status to model enum
    status_str = _HB_STATUS_MAP.get(hb.update_status, "idle")
    host.agent_update_status = AgentUpdateStatus(status_str)

    # Update target version if present
    if hb.update_target_version:
        host.agent_update_target_version = hb.update_target_version
    else:
        host.agent_update_target_version = None

    await session.flush()
