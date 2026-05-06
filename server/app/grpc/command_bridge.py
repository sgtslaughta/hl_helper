"""Bridge: bus 'command.issued' events -> grpc per-host live queue.

The API CommandDispatcher persists Command rows and publishes
`command.issued` events on the bus. The gRPC AgentBridge.Stream
handler pulls envelopes from an in-memory per-host asyncio.Queue
managed by `server.app.grpc.dispatcher.CommandDispatcher`. Without
this bridge, persisted commands never reach the live stream.

This task subscribes to the bus and, for each `command.issued`,
loads the Command row, deserializes envelope_bytes back into a
CommandEnvelope proto, and enqueues it on the live dispatcher.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from server.app.events.bus import Bus
from server.app.grpc._pb.fleet.v1 import envelope_pb2
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.models.command import Command

log = structlog.get_logger(__name__)


async def run_command_bridge(
    bus: Bus,
    grpc_dispatcher: CommandDispatcher,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Long-running task: forward command.issued events to grpc queue."""
    sub = bus.subscribe("commands")
    log.info("command_bridge.started")
    try:
        async for ev in sub:
            payload: Any = ev.payload
            if not isinstance(payload, dict):
                continue
            if payload.get("event") != "command.issued":
                continue
            command_id = payload.get("command_id")
            host_id = payload.get("host_id")
            if not isinstance(command_id, str) or not isinstance(host_id, str):
                continue
            try:
                async with sessionmaker() as session:
                    cmd = await session.get(Command, command_id)
                    if cmd is None or not cmd.envelope_bytes:
                        log.warning(
                            "command_bridge.command_not_found",
                            command_id=command_id,
                        )
                        continue
                    envelope = envelope_pb2.CommandEnvelope()
                    envelope.ParseFromString(cmd.envelope_bytes)
                await grpc_dispatcher.enqueue(host_id, envelope)
                log.info(
                    "command_bridge.enqueued",
                    command_id=command_id,
                    host_id=host_id,
                )
            except Exception as e:
                log.exception(
                    "command_bridge.dispatch_failed",
                    command_id=command_id,
                    error=str(e),
                )
    except asyncio.CancelledError:
        log.info("command_bridge.cancelled")
        raise
    finally:
        await sub.close()
