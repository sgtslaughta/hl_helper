"""AgentBridge.Stream RPC handler."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from typing import TYPE_CHECKING, Any

import grpc
import structlog

from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import (
    agent_bridge_pb2,
    agent_bridge_pb2_grpc,
    envelope_pb2,
)

from .dispatcher import CommandDispatcher
from .peer_context import peer_context, peer_serial

if TYPE_CHECKING:
    from server.app.revocation.service import RevocationService
    from .result_handler import ResultHandler

log = structlog.get_logger(__name__)


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

            log.info("agent.connected", host_id=host_id, spiffe=spiffe_uri)

            recv_task = asyncio.create_task(
                self._recv_loop(host_id, request_iterator)
            )
            try:
                while True:
                    # Pull next command from queue + watch for termination.
                    pull_task = asyncio.create_task(state.queue.get())
                    term_task = asyncio.create_task(state.terminate_event.wait())
                    done, _pending = await asyncio.wait(
                        {pull_task, recv_task, term_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if term_task in done:
                        # Host was revoked; terminate stream.
                        # If pull_task already got an envelope, requeue it to avoid loss.
                        if pull_task in done and pull_task.exception() is None:
                            state.queue.put_nowait(pull_task.result())
                        pull_task.cancel()
                        recv_task.cancel()
                        await context.abort(grpc.StatusCode.PERMISSION_DENIED, "host revoked")
                        return

                    if recv_task in done:
                        # Agent closed sending side. Cancel pending pull.
                        # If pull_task already got an envelope, requeue it to avoid loss.
                        if pull_task in done and pull_task.exception() is None:
                            state.queue.put_nowait(pull_task.result())
                        pull_task.cancel()
                        term_task.cancel()
                        break

                    cmd: envelope_pb2.CommandEnvelope = pull_task.result()
                    term_task.cancel()
                    await self._dispatcher.mark_in_flight(host_id, cmd)
                    yield agent_bridge_pb2.ServerToAgent(command=cmd)
            finally:
                recv_task.cancel()
                await self._dispatcher.unregister(host_id)
                log.info("agent.disconnected", host_id=host_id)

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

        async for msg in request_iterator:
            kind = msg.WhichOneof("msg")
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
                # Update Host.last_seen_at
                if self._sessionmaker is not None:
                    from server.app.models.host import Host

                    try:
                        async with self._sessionmaker() as session:
                            host = await session.get(Host, host_id)
                            if host:
                                host.last_seen_at = datetime.now(timezone.utc)
                                await session.commit()
                    except Exception as e:
                        log.warning(
                            "heartbeat.update_failed",
                            host_id=host_id,
                            error=str(e),
                        )
            else:
                log.warning("agent.unknown_message", host_id=host_id, kind=kind)
