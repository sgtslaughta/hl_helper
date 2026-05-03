"""Tests for ResultHandler bus event publishing with after_commit pattern."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.result_envelope import sign_result
from server.app.crypto.signing import FileBackend
from server.app.db.session import session_scope
from server.app.events.bus import Bus
from server.app.grpc._pb.fleet.v1 import results_pb2
from server.app.grpc.result_handler import ResultHandler
from server.app.models import Host


def make_signed_result(
    *,
    host_id: str = "host1",
    command_id: str = "cmd1",
    sequence: int = 1,
    prev_hash: bytes = b"\x00" * 32,
    agent_key: ed25519.Ed25519PrivateKey,
    exit_code: int = 0,
    status: int = results_pb2.RESULT_OK,
    final: bool = True,
) -> results_pb2.ResultEnvelope:
    """Factory to build and sign a ResultEnvelope."""
    env = results_pb2.ResultEnvelope()
    env.command_id = command_id
    env.host_id = host_id
    env.sequence = sequence
    env.exit_code = exit_code
    env.status = status
    env.final = final
    env.prev_result_hash = prev_hash
    return sign_result(env, agent_key)


@pytest.mark.asyncio
async def test_result_handler_publishes_after_commit_succeed(
    sm: async_sessionmaker, tmp_path
) -> None:
    """Result success → publishes command.result event to hosts.status on commit."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    bus = Bus()
    handler = ResultHandler(sm, audit_chain, event_bus=bus)

    # Pre-create Host with agent_pubkey
    agent_key = ed25519.Ed25519PrivateKey.generate()
    agent_pubkey = agent_key.public_key().public_bytes_raw()
    host_id = "host-test-1"

    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=agent_pubkey,
        )
        session.add(host)
        await session.commit()

    # Collect events from the bus
    events: list[Any] = []

    async def collect_events():
        sub = bus.subscribe("hosts.status")
        try:
            async for event in sub:
                events.append(event)
                if len(events) >= 1:
                    break
        finally:
            await sub.close()

    collect_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)  # Let subscriber start

    # Build and sign result with success status
    env = make_signed_result(
        host_id=host_id,
        command_id="cmd-1",
        sequence=1,
        exit_code=0,
        status=results_pb2.RESULT_OK,
        agent_key=agent_key,
    )

    # Handle result
    await handler.handle(env, expected_host_id=host_id)

    # Wait for event to be published
    try:
        await asyncio.wait_for(collect_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Verify event published on commit
    assert len(events) >= 1, "Event not published after commit"
    event = events[0]
    assert event.channel == "hosts.status"
    assert event.payload["event"] == "command.result"
    assert event.payload["command_id"] == "cmd-1"
    assert event.payload["host_id"] == host_id
    assert event.payload["status"] == "ok"
    assert event.payload["exit_code"] == 0


@pytest.mark.asyncio
async def test_result_handler_publishes_after_commit_failed(
    sm: async_sessionmaker, tmp_path
) -> None:
    """Result failure → publishes command.result event with status=fail."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    bus = Bus()
    handler = ResultHandler(sm, audit_chain, event_bus=bus)

    agent_key = ed25519.Ed25519PrivateKey.generate()
    agent_pubkey = agent_key.public_key().public_bytes_raw()
    host_id = "host-test-1"

    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=agent_pubkey,
        )
        session.add(host)
        await session.commit()

    # Collect events from the bus
    events: list[Any] = []

    async def collect_events():
        sub = bus.subscribe("hosts.status")
        try:
            async for event in sub:
                events.append(event)
                if len(events) >= 1:
                    break
        finally:
            await sub.close()

    collect_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    # Build and sign result with failure status
    env = make_signed_result(
        host_id=host_id,
        command_id="cmd-1",
        sequence=1,
        exit_code=127,
        status=results_pb2.RESULT_FAIL,
        agent_key=agent_key,
    )

    # Handle result
    await handler.handle(env, expected_host_id=host_id)

    # Wait for event to be published
    try:
        await asyncio.wait_for(collect_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Verify event published
    assert len(events) >= 1, "Event not published after commit"
    event = events[0]
    assert event.channel == "hosts.status"
    assert event.payload["event"] == "command.result"
    assert event.payload["command_id"] == "cmd-1"
    assert event.payload["host_id"] == host_id
    assert event.payload["status"] == "fail"
    assert event.payload["exit_code"] == 127


@pytest.mark.asyncio
async def test_result_handler_no_publish_on_rollback(
    sm: async_sessionmaker, tmp_path
) -> None:
    """Publish scheduled on transaction, but rollback → no event published."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    bus = Bus()
    # Handler not invoked here — test exercises publish_after_commit + rollback directly.
    ResultHandler(sm, audit_chain, event_bus=bus)

    agent_key = ed25519.Ed25519PrivateKey.generate()
    agent_pubkey = agent_key.public_key().public_bytes_raw()
    host_id = "host-test-1"

    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=agent_pubkey,
        )
        session.add(host)
        await session.commit()

    # Collect events from the bus
    events: list[Any] = []

    async def collect_events():
        sub = bus.subscribe("hosts.status")
        try:
            async for event in sub:
                events.append(event)
                if len(events) >= 1:
                    break
        finally:
            await sub.close()

    collect_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    # Test: the handle() method will internally rollback on error cases
    # This tests that rollback prevents publish. We'll manually trigger a rollback
    # by using publish_after_commit directly in a manual session, then rollback.
    from server.app.events.after_commit import publish_after_commit

    async with sm() as session:
        # Schedule publish on this session
        publish_after_commit(
            session,
            bus,
            "hosts.status",
            {
                "event": "command.result",
                "command_id": "cmd-rollback",
                "host_id": host_id,
                "status": "ok",
                "exit_code": 0,
            },
        )

        # Rollback instead of commit
        await session.rollback()

    # Wait briefly to see if event was published (it shouldn't be)
    await asyncio.sleep(0.05)
    assert len(events) == 0, "Event was published despite rollback"

    # Clean up
    try:
        collect_task.cancel()
    except Exception:
        pass
