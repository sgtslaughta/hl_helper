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
        dispatcher: CommandDispatcher | None = None,
        result_handler: ResultHandler | None = None,
        revocation: RevocationService | None = None,
        sessionmaker: Any | None = None,
        audit_chain: Any | None = None,
        advisory_worker: Any | None = None,
        event_bus: Any | None = None,
        rotation_orchestrator: Any | None = None,
        exposure_handler: Any | None = None,
        risk_recomputer: Any | None = None,
        log_broker: Any | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._result_handler = result_handler
        self._revocation = revocation
        self._sessionmaker = sessionmaker
        self._audit_chain = audit_chain
        self._advisory_worker = advisory_worker
        self._event_bus = event_bus
        self._rotation_orchestrator = rotation_orchestrator
        self._exposure_handler = exposure_handler
        self._risk_recomputer = risk_recomputer
        self._log_broker = log_broker
        # Per-session log dictionaries: session_id -> {int_key -> string_value}
        self._log_dicts: dict[str, dict[int, str]] = {}

    async def _enqueue_match(self, host_id: str) -> None:
        """Best-effort: ask the advisory worker to re-match this host.

        Silently no-op when the worker is not wired (tests / advisory_enabled=false).
        """
        worker = self._advisory_worker
        if worker is None:
            return
        try:
            await worker.enqueue_match(host_id)
        except Exception:
            log.warning("agent_bridge.enqueue_match_failed", host_id=host_id, exc_info=True)

    async def handle_cert_rotate_for_test(
        self,
        *,
        host_id: str,
        csr_pem: bytes,
        signing_pubkey: bytes,
        prev_serial: str,
        peer_ip: str,
        push,
    ):
        """Test-only entrypoint mirroring the recv_loop cert_rotate branch."""
        from server.app.grpc.cert_rotate_policy import RotationContext

        resp = await self._rotation_orchestrator.rotate(
            RotationContext(
                host_id=host_id,
                csr_pem=csr_pem,
                signing_pubkey=signing_pubkey,
                prev_serial=prev_serial,
                peer_ip=peer_ip,
            )
        )
        out = agent_bridge_pb2.ServerToAgent(
            cert_issue=agent_bridge_pb2.CertIssueResponse(
                cert_chain_pem=resp.cert_chain_pem,
            )
        )
        out.cert_issue.not_after.FromDatetime(resp.not_after)
        push(out)

    def set_test_pusher(self, host_id: str, fn) -> None:  # type: ignore[no-untyped-def]
        """Test override for per-host send queue.

        Allows tests to inject a callback that receives ServerToAgent messages
        instead of pushing to the control queue.
        """
        if not hasattr(self, "_test_pushers"):
            self._test_pushers = {}
        self._test_pushers[host_id] = fn

    async def push_run_cert_rotate(self, host_id: str, reason: str) -> bool:
        """Send RunCertRotate to a connected agent. Returns False if not connected.

        Args:
            host_id: Target host identifier.
            reason: Reason for rotation (e.g. "operator-initiated").

        Returns:
            True if the message was queued; False if the host is offline.
        """
        msg = agent_bridge_pb2.ServerToAgent(
            run_cert_rotate=agent_bridge_pb2.RunCertRotate(reason=reason)
        )
        if hasattr(self, "_test_pushers") and host_id in self._test_pushers:
            self._test_pushers[host_id](msg)
            return True
        return push_control(host_id, msg)

    async def handle_runtime_exposure_for_test(
        self, *, host_id, scanned_at, scan, host_packages, advisories
    ):
        """Test-only entrypoint for runtime_exposure ingestion."""
        from server.app.posture.exposure.derive import derive_exposure

        derived = derive_exposure(scan, host_packages, advisories)
        await self._exposure_handler.ingest(
            host_id=host_id, scanned_at=scanned_at, derived=derived
        )

    async def push_run_exposure_scan(self, host_id: str, reason: str) -> bool:
        """Send RunExposureScan to a connected agent. Returns False if not connected."""
        msg = agent_bridge_pb2.ServerToAgent(
            run_exposure_scan=agent_bridge_pb2.RunExposureScan(reason=reason)
        )
        if hasattr(self, "_test_pushers") and host_id in self._test_pushers:
            self._test_pushers[host_id](msg)
            return True
        return push_control(host_id, msg)

    async def RegisterLogDictionary(self, request, context):
        """Cache a session-scoped string dictionary for log payload compression.

        The dictionary is stored keyed by agent_session_id on the next heartbeat,
        or by a temporary peer-based key if the session_id is not yet known.
        Allows agent to send @id:N references in log payloads instead of full strings.

        Args:
            request: LogDictionary proto with version and strings map.
            context: gRPC service context.

        Returns:
            DictionaryAck proto with version and ok=True on success.
        """
        # Store dictionary with a fallback to a temp key if session_id unknown
        # The next heartbeat from this peer will reassign it to the correct session_id
        dict_data = dict(request.strings)
        # Use a peer-based temp key; when heartbeat arrives, we move it to the
        # correct session_id
        temp_key = f"_pending_{id(context)}"
        self._log_dicts[temp_key] = dict_data

        log.info(
            "log_dictionary.registered",
            version=request.version,
            dict_size=len(dict_data),
        )

        return agent_bridge_pb2.DictionaryAck(version=request.version, ok=True)

    async def _load_host_tags(self, host_id: str) -> list[str]:
        """Load tags assigned to a host for policy resolution."""
        if self._sessionmaker is None:
            return []
        try:
            from server.app.models.host import Host

            async with self._sessionmaker() as session:
                host = await session.get(Host, host_id)
                if host is None:
                    return []
                labels = host.labels or {}
                tags = labels.get("tags", [])
                if isinstance(tags, list):
                    return tags
                return []
        except Exception as e:
            log.warning("host_tags.load_failed", host_id=host_id, error=str(e))
            return []

    async def _load_host_packages(self, host_id: str) -> list[dict]:
        """Load installed packages for derive_exposure."""
        from sqlalchemy import select
        from server.app.models.host_package import HostPackage

        async with self._sessionmaker() as session:
            rows = (
                await session.execute(
                    select(HostPackage).where(HostPackage.host_id == host_id)
                )
            ).scalars().all()
        return [{"name": r.name, "version": r.version} for r in rows]

    async def _load_advisories_for_host(self, host_id: str) -> list[dict]:
        """Load open advisories already matched to this host's packages.

        Pulls from HostAdvisory rows (already populated by the advisory
        matching worker). Each row maps an advisory_id to a package on the
        host. derive_exposure() uses {id, package, affected_paths} shape; we
        leave affected_paths empty (catalog doesn't expose it yet — exposure
        derivation falls through to package-name and process-pkg matches).
        """
        from sqlalchemy import select
        from server.app.models.host_advisory import HostAdvisory

        async with self._sessionmaker() as session:
            rows = (
                await session.execute(
                    select(HostAdvisory).where(
                        HostAdvisory.host_id == host_id,
                        HostAdvisory.status == "open",
                    )
                )
            ).scalars().all()
        return [
            {"id": r.advisory_id, "package": r.package, "affected_paths": []}
            for r in rows
        ]

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
                self._recv_loop(host_id, request_iterator, context, control_q)
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
        context: Any,
        control_q: asyncio.Queue[agent_bridge_pb2.ServerToAgent],
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
        from server.app.grpc.tls import extract_peer_cert_info

        peer_info = extract_peer_cert_info(context)
        log.info(
            "mtls.handshake.ok",
            host_id=host_id,
            cn=peer_info.get("cn", "?"),
            serial=peer_info.get("serial", "?"),
            not_after=peer_info.get("not_after", "?"),
        )
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
                            transitioned_to_online = False
                            host_hostname: str | None = None
                            if host:
                                now = datetime.now(timezone.utc)
                                if host.status == "offline":
                                    transitioned_to_online = True
                                    host_hostname = host.hostname
                                host.last_seen_at = now
                                host.status = "healthy"
                                host.metrics = metrics_dict
                                host.metrics_at = now
                            # Persist agent version and update status
                            await _persist_heartbeat(session, host_id, msg.heartbeat)
                            if transitioned_to_online and self._event_bus is not None:
                                from server.app.events.after_commit import (
                                    publish_after_commit,
                                )
                                from server.app.events.ticker import (
                                    TICKER_CHANNEL,
                                    format_host_status,
                                    make_ticker_payload,
                                )

                                fmt = format_host_status(
                                    host_id=host_id,
                                    hostname=host_hostname or host_id,
                                    online=True,
                                )
                                publish_after_commit(
                                    session,
                                    self._event_bus,
                                    TICKER_CHANNEL,
                                    make_ticker_payload(**fmt),  # type: ignore[arg-type]
                                )
                            await session.commit()

                            # Ingest log batch if present
                            hb = msg.heartbeat
                            if hb.HasField("logs") and len(hb.logs.entries) > 0:
                                try:
                                    from server.app.logs.ingest import ingest_batch_async
                                    from server.app.logs.policy import resolve as resolve_policy

                                    # Convert proto entries to ingest-friendly dicts
                                    entries = [
                                        {
                                            "seq": e.seq,
                                            "ts": e.ts.ToDatetime() if e.ts else None,
                                            "level": e.level,
                                            "action": e.action,
                                            "category": e.category,
                                            "outcome": e.outcome,
                                            "payload": bytes(e.payload),
                                        }
                                        for e in hb.logs.entries
                                    ]

                                    # Resolve or move session's log dictionary
                                    dictionary = None
                                    session_id = hb.agent_session_id
                                    # Check for pending dict keyed by context
                                    for k in list(self._log_dicts.keys()):
                                        if k.startswith("_pending_"):
                                            dictionary = self._log_dicts.pop(k)
                                            if session_id:
                                                self._log_dicts[session_id] = dictionary
                                            break
                                    if not dictionary and session_id:
                                        dictionary = self._log_dicts.get(session_id)

                                    # Ingest the batch — async variant uses AsyncSession directly,
                                    # avoiding run_sync state quirks where committed inserts get
                                    # rolled back by the outer async session lifecycle.
                                    try:
                                        last_seq = await ingest_batch_async(
                                            session,
                                            self._log_broker,
                                            host_id=host_id,
                                            agent_id=host_id,
                                            agent_session_id=session_id,
                                            agent_version=hb.agent_version,
                                            entries=entries,
                                            dictionary=dictionary,
                                        )
                                        backoff_ms = 0
                                    except Exception as ingest_err:
                                        log.warning(
                                            "log_ingest.failed",
                                            host_id=host_id,
                                            error=str(ingest_err),
                                        )
                                        last_seq = 0
                                        backoff_ms = 1000

                                    # Resolve effective policy. resolve_policy is sync; run in a fresh
                                    # short-lived sync session to avoid async-session entanglement.
                                    host_tags = await self._load_host_tags(host_id)
                                    eff = await session.run_sync(
                                        lambda s: resolve_policy(s, host_id=host_id, host_tags=host_tags)
                                    )
                                    # Note: resolve_policy reads only; run_sync is safe for reads.

                                    # Build HeartbeatAck with policy
                                    ack = agent_bridge_pb2.HeartbeatAck()
                                    ack.logs_acked_seq = last_seq
                                    ack.log_policy.policy_version = eff.policy_version or 1
                                    ack.log_policy.default_level = eff.default_level
                                    ack.log_policy.batch_max_bytes = eff.batch_max_bytes
                                    ack.log_policy.batch_max_interval_s = eff.batch_max_interval_s
                                    ack.log_policy.buffer_max_mb = eff.buffer_max_mb
                                    ack.log_policy.buffer_max_days = eff.buffer_max_days
                                    ack.log_policy.default_sample_rate = eff.default_sample_rate
                                    ack.log_policy.backoff_ms = backoff_ms
                                    if eff.expires_at:
                                        ack.log_policy.expires_at.FromDatetime(eff.expires_at)
                                    for cr in eff.categories:
                                        rule = ack.log_policy.categories.add()
                                        rule.category = cr.category
                                        if cr.level:
                                            rule.level = cr.level
                                        if cr.sample_rate is not None:
                                            rule.sample_rate = cr.sample_rate
                                        rule.drop = cr.drop

                                    # Send HbAck via control queue
                                    control_q.put_nowait(
                                        agent_bridge_pb2.ServerToAgent(hb_ack=ack)
                                    )
                                    log.info(
                                        "log_ingest.success",
                                        host_id=host_id,
                                        entries=len(entries),
                                        last_seq=last_seq,
                                    )
                                except Exception as e:
                                    log.exception(
                                        "log_ingest.handle_failed",
                                        host_id=host_id,
                                        error=str(e),
                                    )
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
            elif kind == "audit":
                if self._sessionmaker is not None and self._audit_chain is not None:
                    audit_event = msg.audit
                    try:
                        async with self._sessionmaker() as audit_session:
                            await self._audit_chain.append(
                                audit_session,
                                actor=f"agent:{host_id}",
                                action=f"exec.elevated.{audit_event.phase}",
                                subject=audit_event.task_id,
                                payload={
                                    "binary": audit_event.binary,
                                    "args": list(audit_event.args),
                                    "elevator": audit_event.elevator,
                                    "reason": audit_event.reason,
                                    "exit_code": audit_event.exit_code,
                                    "error": audit_event.error,
                                },
                            )
                            await audit_session.commit()
                    except Exception as e:
                        log.warning(
                            "audit.append_failed",
                            host_id=host_id,
                            phase=audit_event.phase,
                            error=str(e),
                        )
            elif kind == "package_inventory":
                if self._sessionmaker is not None:
                    from .inventory_servicer import handle_package_inventory

                    try:
                        await handle_package_inventory(
                            self._sessionmaker, msg.package_inventory
                        )
                        await self._enqueue_match(host_id)
                    except Exception as e:
                        log.warning(
                            "package_inventory.handle_failed",
                            host_id=host_id,
                            error=str(e),
                        )
            elif kind == "container_inventory":
                if self._sessionmaker is not None:
                    from .inventory_servicer import handle_container_inventory

                    try:
                        await handle_container_inventory(
                            self._sessionmaker, msg.container_inventory
                        )
                        await self._enqueue_match(host_id)
                    except Exception as e:
                        log.warning(
                            "container_inventory.handle_failed",
                            host_id=host_id,
                            error=str(e),
                        )
            elif kind == "host_facts":
                if self._sessionmaker is not None:
                    from .inventory_servicer import handle_host_facts

                    try:
                        await handle_host_facts(self._sessionmaker, msg.host_facts)
                    except Exception as e:
                        log.warning(
                            "host_facts.handle_failed",
                            host_id=host_id,
                            error=str(e),
                        )
            elif kind == "cert_rotate":
                if self._rotation_orchestrator is None:
                    log.warning("cert_rotate.no_orchestrator", host_id=host_id)
                    continue
                try:
                    from server.app.grpc.cert_rotate_policy import (
                        PolicyDeniedError,
                        RateLimitedError,
                        RotationContext,
                    )

                    resp = await self._rotation_orchestrator.rotate(
                        RotationContext(
                            host_id=host_id,
                            csr_pem=msg.cert_rotate.csr_pem,
                            signing_pubkey=msg.cert_rotate.signing_pubkey,
                            prev_serial=msg.cert_rotate.prev_serial,
                            peer_ip="",
                        )
                    )
                    out = agent_bridge_pb2.ServerToAgent(
                        cert_issue=agent_bridge_pb2.CertIssueResponse(
                            cert_chain_pem=resp.cert_chain_pem,
                        )
                    )
                    out.cert_issue.not_after.FromDatetime(resp.not_after)
                    # Push via control queue (this method used in tests)
                    control_q.put_nowait(out)
                except RateLimitedError as e:
                    log.warning(
                        "cert_rotate.rate_limited", host_id=host_id, error=str(e)
                    )
                except PolicyDeniedError as e:
                    log.warning(
                        "cert_rotate.denied", host_id=host_id, error=str(e)
                    )
                except Exception as e:
                    log.exception(
                        "cert_rotate.unhandled", host_id=host_id, error=str(e)
                    )
            elif kind == "runtime_exposure":
                if self._exposure_handler is None:
                    log.warning("runtime_exposure.no_handler", host_id=host_id)
                    continue
                try:
                    from google.protobuf.json_format import MessageToDict

                    scan_dict = MessageToDict(
                        msg.runtime_exposure, preserving_proto_field_name=True
                    )
                    # Load host packages + advisories
                    host_packages = await self._load_host_packages(host_id)
                    advisories = await self._load_advisories_for_host(host_id)
                    from server.app.posture.exposure.derive import derive_exposure

                    derived = derive_exposure(scan_dict, host_packages, advisories)
                    procs = scan_dict.get("processes") or []
                    procs_with_pkg = sum(1 for p in procs if p.get("pkg"))
                    log.info(
                        "runtime_exposure.derive",
                        host_id=host_id,
                        procs=len(procs),
                        procs_with_pkg=procs_with_pkg,
                        listeners=len(scan_dict.get("listeners") or []),
                        services=len(scan_dict.get("services") or []),
                        host_packages=len(host_packages),
                        advisories=len(advisories),
                        derived_rows=len(derived),
                    )
                    await self._exposure_handler.ingest(
                        host_id=host_id,
                        scanned_at=msg.runtime_exposure.scanned_at.ToDatetime(),
                        derived=derived,
                    )
                    if self._risk_recomputer is not None:
                        await self._risk_recomputer.request(
                            host_id, trigger_reason="exposure_scan"
                        )
                except Exception as e:
                    log.exception(
                        "runtime_exposure.handle_failed", host_id=host_id, error=str(e)
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

    # Update sleeping status and sleep_until timestamp
    host.sleeping = hb.sleeping
    if hb.sleeping and hb.sleep_until:
        # Convert protobuf Timestamp to datetime with timezone
        host.sleep_until = hb.sleep_until.ToDatetime()
    else:
        host.sleep_until = None

    await session.flush()
