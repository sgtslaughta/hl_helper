"""Repeat hot paths under pytest-memray to catch unbounded allocations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from server.app.audit.chain import AuditChain, AuditEntry
from server.app.crypto.signing import FileBackend
from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import envelope_pb2
from server.app.grpc.dispatcher import CommandDispatcher


@pytest.fixture
def backend(tmp_path: Path) -> FileBackend:
    """Create a temporary signing backend for tests."""
    return FileBackend.bootstrap(tmp_path / "signing")


@pytest.mark.limit_memory("50 MB")
def test_audit_chain_append_bounded(backend: FileBackend) -> None:
    """Appending 1000 entries should not retain memory beyond a constant + payload."""
    chain = AuditChain(backend, checkpoint_interval=100)

    # Append 1000 entries with varying payloads
    for i in range(1000):
        entry = chain.append(
            actor=f"test-actor-{i % 10}",
            action=f"auth.action.{i % 20}",
        )
        assert entry.sequence == i

    # Chain should be valid after all appends
    chain.verify()
    assert chain.length == 1000


@pytest.mark.limit_memory("100 MB")
def test_dispatcher_queue_drain_no_leak() -> None:
    """CommandDispatcher: enqueue 5000 commands, drain via mock pull, ensure no unbounded growth."""
    import asyncio

    async def run_test() -> None:
        dispatcher = CommandDispatcher()

        # Enqueue 5000 commands across 10 hosts
        for i in range(5000):
            env = envelope_pb2.CommandEnvelope()
            env.command_id = f"cmd-{i}"
            env.host_id = f"host-{i % 10}"
            env.sequence = i
            env.nonce = f"nonce-{i}".encode()
            now = datetime.now(timezone.utc)
            env.issued_at.FromDatetime(now)
            env.expires_at.FromDatetime(now)
            env.issued_by = "test-server"
            env.pkg_update.classes.append("base")

            await dispatcher.enqueue(env.host_id, env)

        # Register and drain all commands
        for host_id in {f"host-{i}" for i in range(10)}:
            state = await dispatcher.register(host_id)
            while not state.queue.empty():
                try:
                    await asyncio.wait_for(state.queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    break

    asyncio.run(run_test())
