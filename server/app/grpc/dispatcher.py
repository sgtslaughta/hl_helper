"""In-memory per-host command dispatcher.

Lifecycle:
  - Stream handler registers an active session with `register(host_id)`
    when an agent connects (after authn).
  - `enqueue(host_id, envelope)` puts a command on the host's queue.
  - Stream handler pulls from queue and sends to agent.
  - When sending, handler calls `mark_in_flight(host_id, envelope)` to track
    the command awaiting ack.
  - On ack, handler calls `ack(host_id, command_id)` to remove from unacked.
  - On disconnect, handler calls `unregister(host_id)`. Pending un-acked
    commands stay in the queue for resume.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field

from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import envelope_pb2


@dataclass
class _HostState:
    """State for a single host's command queue."""

    queue: asyncio.Queue[envelope_pb2.CommandEnvelope] = field(
        default_factory=asyncio.Queue
    )
    # In-flight commands awaiting ack (command_id -> CommandEnvelope), preserves order.
    unacked: OrderedDict[str, envelope_pb2.CommandEnvelope] = field(
        default_factory=OrderedDict
    )
    connected: bool = False


class CommandDispatcher:
    """Per-host async command queue with resume support."""

    def __init__(self) -> None:
        self._hosts: dict[str, _HostState] = {}
        self._lock = asyncio.Lock()

    async def enqueue(
        self, host_id: str, envelope: envelope_pb2.CommandEnvelope
    ) -> None:
        """Enqueue a command for delivery to a host.

        Args:
            host_id: Target host identifier.
            envelope: CommandEnvelope to queue.
        """
        async with self._lock:
            state = self._hosts.setdefault(host_id, _HostState())
        await state.queue.put(envelope)

    async def register(self, host_id: str) -> _HostState:
        """Mark host connected and replay any un-acked commands at the front of queue.

        When a host reconnects, un-acked commands (those sent but not yet acked) are
        replayed at the front of the queue so they are resent before new commands.

        Args:
            host_id: Host identifier.

        Returns:
            The host state so the stream handler can pull from state.queue.

        Raises:
            RuntimeError: If the host already has an active stream.
        """
        async with self._lock:
            state = self._hosts.setdefault(host_id, _HostState())
            if state.connected:
                raise RuntimeError(f"host {host_id} already has an active stream")
            state.connected = True

            # Replay un-acked: drain queue, prepend un-acked, append pending.
            pending = []
            while not state.queue.empty():
                pending.append(state.queue.get_nowait())

            for cmd in state.unacked.values():
                state.queue.put_nowait(cmd)
            for cmd in pending:
                state.queue.put_nowait(cmd)

        return state

    async def unregister(self, host_id: str) -> None:
        """Mark host disconnected (stream closed).

        Un-acked commands remain in the queue for the next reconnect.

        Args:
            host_id: Host identifier.
        """
        async with self._lock:
            state = self._hosts.get(host_id)
            if state is not None:
                state.connected = False

    async def mark_in_flight(
        self, host_id: str, envelope: envelope_pb2.CommandEnvelope
    ) -> None:
        """Track a command sent to the agent (waiting for ack).

        Args:
            host_id: Host identifier.
            envelope: CommandEnvelope that was sent.
        """
        async with self._lock:
            state = self._hosts.setdefault(host_id, _HostState())
            state.unacked[envelope.command_id] = envelope

    async def ack(self, host_id: str, command_id: str) -> bool:
        """Acknowledge a command, removing it from un-acked set.

        Args:
            host_id: Host identifier.
            command_id: Command ID to ack.

        Returns:
            True if the command was in the unacked set and removed; False otherwise.
        """
        async with self._lock:
            state = self._hosts.get(host_id)
            if state is None:
                return False
            return state.unacked.pop(command_id, None) is not None

    def is_connected(self, host_id: str) -> bool:
        """Check if a host currently has an active stream.

        Args:
            host_id: Host identifier.

        Returns:
            True if the host is connected; False otherwise.
        """
        state = self._hosts.get(host_id)
        return bool(state and state.connected)
