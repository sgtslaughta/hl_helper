"""Tests for the per-host command dispatcher."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import envelope_pb2
from server.app.grpc.dispatcher import CommandDispatcher


def make_env(host_id: str, command_id: str) -> envelope_pb2.CommandEnvelope:
    """Build a CommandEnvelope for testing."""
    env = envelope_pb2.CommandEnvelope()
    env.command_id = command_id
    env.host_id = host_id
    env.sequence = 1
    env.nonce = b"test"
    now = datetime.now(timezone.utc)
    env.issued_at.FromDatetime(now)
    env.expires_at.FromDatetime(now)
    env.issued_by = "test-server"
    env.pkg_update.classes.append("base")
    return env


class TestCommandDispatcher:
    """Tests for CommandDispatcher class."""

    @pytest.mark.asyncio
    async def test_enqueue_and_pull(self) -> None:
        """Enqueue a CommandEnvelope; register host; queue.get() returns it."""
        dispatcher = CommandDispatcher()
        env = make_env("host1", "cmd-1")

        await dispatcher.enqueue("host1", env)
        state = await dispatcher.register("host1")

        pulled = await asyncio.wait_for(state.queue.get(), timeout=1.0)
        assert pulled.command_id == "cmd-1"

    @pytest.mark.asyncio
    async def test_register_replays_unacked(self) -> None:
        """Enqueue cmd1, mark_in_flight cmd1, register again, verify queue.get() returns cmd1 first."""
        dispatcher = CommandDispatcher()
        env1 = make_env("host1", "cmd-1")

        # First registration + send + mark in flight
        await dispatcher.enqueue("host1", env1)
        state1 = await dispatcher.register("host1")
        pulled = await asyncio.wait_for(state1.queue.get(), timeout=1.0)
        assert pulled.command_id == "cmd-1"
        await dispatcher.mark_in_flight("host1", env1)

        # Disconnect and reconnect
        await dispatcher.unregister("host1")
        state2 = await dispatcher.register("host1")

        # cmd1 should be replayed first
        replayed = await asyncio.wait_for(state2.queue.get(), timeout=1.0)
        assert replayed.command_id == "cmd-1"

    @pytest.mark.asyncio
    async def test_register_preserves_pending_after_unacked(self) -> None:
        """Mark cmd1 in-flight, enqueue cmd2, register → queue order is cmd1 then cmd2."""
        dispatcher = CommandDispatcher()
        env1 = make_env("host1", "cmd-1")
        env2 = make_env("host1", "cmd-2")

        # Set up: mark cmd1 as unacked (simulating sent but not acked)
        await dispatcher.mark_in_flight("host1", env1)
        # Then enqueue cmd2
        await dispatcher.enqueue("host1", env2)

        # Register (reconnect)
        state = await dispatcher.register("host1")

        # Queue order should be: cmd1 (unacked), cmd2 (pending)
        first = await asyncio.wait_for(state.queue.get(), timeout=1.0)
        second = await asyncio.wait_for(state.queue.get(), timeout=1.0)

        assert first.command_id == "cmd-1"
        assert second.command_id == "cmd-2"

    @pytest.mark.asyncio
    async def test_ack_removes_unacked(self) -> None:
        """Mark cmd in-flight, ack(cmd_id) → True; ack again → False."""
        dispatcher = CommandDispatcher()
        env = make_env("host1", "cmd-1")

        await dispatcher.mark_in_flight("host1", env)

        # First ack should succeed
        result = await dispatcher.ack("host1", "cmd-1")
        assert result is True

        # Second ack should fail
        result = await dispatcher.ack("host1", "cmd-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_register_rejects_concurrent_stream(self) -> None:
        """Register host, register same host → RuntimeError."""
        dispatcher = CommandDispatcher()

        await dispatcher.register("host1")

        with pytest.raises(RuntimeError, match="already has an active stream"):
            await dispatcher.register("host1")

    @pytest.mark.asyncio
    async def test_unregister_allows_reconnect(self) -> None:
        """Register, unregister, register again → ok."""
        dispatcher = CommandDispatcher()

        await dispatcher.register("host1")
        await dispatcher.unregister("host1")
        # Should not raise
        await dispatcher.register("host1")

    @pytest.mark.asyncio
    async def test_is_connected(self) -> None:
        """is_connected reflects state."""
        dispatcher = CommandDispatcher()

        # Not connected initially
        assert dispatcher.is_connected("host1") is False

        # Connected after register
        await dispatcher.register("host1")
        assert dispatcher.is_connected("host1") is True

        # Disconnected after unregister
        await dispatcher.unregister("host1")
        assert dispatcher.is_connected("host1") is False
