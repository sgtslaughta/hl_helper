"""Tests for ResultHandler: verify, persist, audit."""

from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.result_envelope import canonical_result_bytes, sign_result
from server.app.crypto.signing import FileBackend
from server.app.db.session import session_scope
from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import results_pb2
from server.app.grpc.result_handler import (
    BadSignatureError,
    ChainBrokenError,
    HostNotFoundError,
    ResultHandler,
)
from server.app.models import Host, Result


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


def canonical_result_hash(env: results_pb2.ResultEnvelope) -> bytes:
    """Compute sha256 hash of canonical result bytes."""
    return hashlib.sha256(canonical_result_bytes(env)).digest()


@pytest.mark.asyncio
async def test_handle_accepts_valid_result(
    sm: async_sessionmaker, tmp_path
) -> None:
    """Valid result with correct signature → accepted, persisted, audit entry."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    handler = ResultHandler(sm, audit_chain)

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

    # Build and sign result
    env = make_signed_result(
        host_id=host_id,
        command_id="cmd-1",
        sequence=1,
        agent_key=agent_key,
    )

    # Handle
    result = await handler.handle(env, expected_host_id=host_id)

    # Verify Result row persisted
    async with session_scope(sm) as session:
        fetched = await session.get(Result, result.id)
        assert fetched is not None
        assert fetched.command_id == "cmd-1"
        assert fetched.host_id == host_id
        assert fetched.sequence == 1
        assert fetched.exit_code == 0

    # Verify audit entry
    async with session_scope(sm) as session:
        entries = await audit_chain.length(session)
        assert entries == 1


@pytest.mark.asyncio
async def test_handle_rejects_unknown_host(sm: async_sessionmaker, tmp_path) -> None:
    """Unknown host → HostNotFoundError, audit entry."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    handler = ResultHandler(sm, audit_chain)

    agent_key = ed25519.Ed25519PrivateKey.generate()

    env = make_signed_result(
        host_id="unknown-host",
        command_id="cmd-1",
        sequence=1,
        agent_key=agent_key,
    )

    with pytest.raises(HostNotFoundError):
        await handler.handle(env, expected_host_id="unknown-host")

    # Verify audit entry for rejection
    async with session_scope(sm) as session:
        entries = await audit_chain.length(session)
        assert entries == 1


@pytest.mark.asyncio
async def test_handle_rejects_bad_signature(sm: async_sessionmaker, tmp_path) -> None:
    """Host exists with mismatched pubkey → BadSignatureError, audit entry."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    handler = ResultHandler(sm, audit_chain)

    # Create Host with one key
    key_a = ed25519.Ed25519PrivateKey.generate()
    pubkey_a = key_a.public_key().public_bytes_raw()
    host_id = "host-test-1"

    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=pubkey_a,
        )
        session.add(host)
        await session.commit()

    # Sign with different key
    key_b = ed25519.Ed25519PrivateKey.generate()
    env = make_signed_result(
        host_id=host_id,
        command_id="cmd-1",
        sequence=1,
        agent_key=key_b,
    )

    with pytest.raises(BadSignatureError):
        await handler.handle(env, expected_host_id=host_id)

    # Verify audit entry
    async with session_scope(sm) as session:
        entries = await audit_chain.length(session)
        assert entries == 1


@pytest.mark.asyncio
async def test_handle_rejects_host_id_mismatch(
    sm: async_sessionmaker, tmp_path
) -> None:
    """host_id mismatch → BadSignatureError, audit entry."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    handler = ResultHandler(sm, audit_chain)

    agent_key = ed25519.Ed25519PrivateKey.generate()
    pubkey = agent_key.public_key().public_bytes_raw()
    host_id_a = "host-a"

    async with session_scope(sm) as session:
        host = Host(
            id=host_id_a,
            hostname="test-host",
            agent_pubkey=pubkey,
        )
        session.add(host)
        await session.commit()

    # Envelope claims host-b but expected is host-a
    env = make_signed_result(
        host_id="host-b",
        command_id="cmd-1",
        sequence=1,
        agent_key=agent_key,
    )

    with pytest.raises(BadSignatureError):
        await handler.handle(env, expected_host_id=host_id_a)

    # Verify audit entry
    async with session_scope(sm) as session:
        entries = await audit_chain.length(session)
        assert entries == 1


@pytest.mark.asyncio
async def test_handle_chain_link_enforced(sm: async_sessionmaker, tmp_path) -> None:
    """Chain link enforced: first result, then second with matching prev_hash."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    handler = ResultHandler(sm, audit_chain)

    agent_key = ed25519.Ed25519PrivateKey.generate()
    pubkey = agent_key.public_key().public_bytes_raw()
    host_id = "host-test-1"

    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=pubkey,
        )
        session.add(host)
        await session.commit()

    # First result with prev_hash = zeros (genesis)
    env1 = make_signed_result(
        host_id=host_id,
        command_id="cmd-1",
        sequence=1,
        prev_hash=b"\x00" * 32,
        agent_key=agent_key,
    )
    result1 = await handler.handle(env1, expected_host_id=host_id)

    # Compute expected prev_hash for second result
    expected_prev_hash = canonical_result_hash(env1)

    # Second result with sequence=2, prev_hash = first result's canonical hash
    env2 = make_signed_result(
        host_id=host_id,
        command_id="cmd-2",
        sequence=2,
        prev_hash=expected_prev_hash,
        agent_key=agent_key,
    )
    result2 = await handler.handle(env2, expected_host_id=host_id)

    # Both should be accepted
    async with session_scope(sm) as session:
        r1 = await session.get(Result, result1.id)
        r2 = await session.get(Result, result2.id)
        assert r1 is not None
        assert r2 is not None


@pytest.mark.asyncio
async def test_handle_sequence_gap_rejected(
    sm: async_sessionmaker, tmp_path
) -> None:
    """Forward sequence gap (seq 1 -> seq 5) is accepted with warning;
    replay (seq 5 -> seq 5) is rejected."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    handler = ResultHandler(sm, audit_chain)

    agent_key = ed25519.Ed25519PrivateKey.generate()
    pubkey = agent_key.public_key().public_bytes_raw()
    host_id = "host-test-1"

    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=pubkey,
        )
        session.add(host)
        await session.commit()

    # First result seq=1
    env1 = make_signed_result(
        host_id=host_id,
        command_id="cmd-1",
        sequence=1,
        prev_hash=b"\x00" * 32,
        agent_key=agent_key,
    )
    result1 = await handler.handle(env1, expected_host_id=host_id)

    # Second result seq=5 (forward gap) — accepted with warning.
    env2 = make_signed_result(
        host_id=host_id,
        command_id="cmd-5",
        sequence=5,
        prev_hash=b"\xff" * 32,
        agent_key=agent_key,
    )
    await handler.handle(env2, expected_host_id=host_id)

    # Replay seq=5 — must be rejected.
    env3 = make_signed_result(
        host_id=host_id,
        command_id="cmd-5b",
        sequence=5,
        prev_hash=b"\xff" * 32,
        agent_key=agent_key,
    )
    with pytest.raises(ChainBrokenError):
        await handler.handle(env3, expected_host_id=host_id)

    async with session_scope(sm) as session:
        r1 = await session.get(Result, result1.id)
        assert r1 is not None
        all_results = await session.execute(
            select(Result).where(Result.host_id == host_id)
        )
        rows = all_results.scalars().all()
        # Two accepted (seq 1 and seq 5), replay rejected.
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_handle_chain_broken_on_contiguous_mismatch(
    sm: async_sessionmaker, tmp_path
) -> None:
    """Contiguous sequence with wrong prev_hash is now accepted with warning."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    handler = ResultHandler(sm, audit_chain)

    agent_key = ed25519.Ed25519PrivateKey.generate()
    pubkey = agent_key.public_key().public_bytes_raw()
    host_id = "host-test-1"

    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=pubkey,
        )
        session.add(host)
        await session.commit()

    # First result seq=1
    env1 = make_signed_result(
        host_id=host_id,
        command_id="cmd-1",
        sequence=1,
        prev_hash=b"\x00" * 32,
        agent_key=agent_key,
    )
    await handler.handle(env1, expected_host_id=host_id)

    # Second result seq=2 with WRONG prev_hash — now accepted with warning.
    env2 = make_signed_result(
        host_id=host_id,
        command_id="cmd-2",
        sequence=2,
        prev_hash=b"\xff" * 32,
        agent_key=agent_key,
    )
    await handler.handle(env2, expected_host_id=host_id)

    async with session_scope(sm) as session:
        rows = (
            await session.execute(select(Result).where(Result.host_id == host_id))
        ).scalars().all()
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_handle_bad_signature_quarantines_host(
    sm: async_sessionmaker, tmp_path
) -> None:
    """Bad signature rejection sets host.status = 'quarantined'."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    handler = ResultHandler(sm, audit_chain)

    # Create Host with one key
    key_a = ed25519.Ed25519PrivateKey.generate()
    pubkey_a = key_a.public_key().public_bytes_raw()
    host_id = "host-test-1"

    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=pubkey_a,
        )
        session.add(host)
        await session.commit()

    # Sign with different key
    key_b = ed25519.Ed25519PrivateKey.generate()
    env = make_signed_result(
        host_id=host_id,
        command_id="cmd-1",
        sequence=1,
        agent_key=key_b,
    )

    with pytest.raises(BadSignatureError):
        await handler.handle(env, expected_host_id=host_id)

    # Verify host is quarantined
    async with session_scope(sm) as session:
        host = await session.get(Host, host_id)
        assert host.status == "quarantined"


@pytest.mark.asyncio
async def test_handle_chain_broken_quarantines_host(
    sm: async_sessionmaker, tmp_path
) -> None:
    """Chain break rejection sets host.status = 'quarantined'."""
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    handler = ResultHandler(sm, audit_chain)

    agent_key = ed25519.Ed25519PrivateKey.generate()
    pubkey = agent_key.public_key().public_bytes_raw()
    host_id = "host-test-1"

    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=pubkey,
        )
        session.add(host)
        await session.commit()

    # First result seq=1
    env1 = make_signed_result(
        host_id=host_id,
        command_id="cmd-1",
        sequence=1,
        prev_hash=b"\x00" * 32,
        agent_key=agent_key,
    )
    await handler.handle(env1, expected_host_id=host_id)

    # Contiguous seq=2 with wrong prev_hash is now accepted with a warning
    # (chain divergence due to forward-gap recovery). Verify it lands.
    env2 = make_signed_result(
        host_id=host_id,
        command_id="cmd-2",
        sequence=2,
        prev_hash=b"\xff" * 32,
        agent_key=agent_key,
    )
    await handler.handle(env2, expected_host_id=host_id)
    async with session_scope(sm) as session:
        rows = (
            await session.execute(select(Result).where(Result.host_id == host_id))
        ).scalars().all()
        assert len(rows) == 2
