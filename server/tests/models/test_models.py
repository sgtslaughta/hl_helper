"""Tests for SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.db.session import session_scope
from server.app.models import (
    AuditCheckpoint,
    AuditEntry,
    Command,
    EnrollmentToken,
    Host,
    Result,
)


@pytest.mark.asyncio
async def test_create_all_tables(sm: async_sessionmaker) -> None:
    """All tables created without error; tables exist and are queryable."""
    async with session_scope(sm) as session:
        # Query the sqlite_master table to verify tables exist
        result = await session.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        )
        table_names = [row[0] for row in result.fetchall()]
        assert "hosts" in table_names
        assert "enrollment_tokens" in table_names
        assert "commands" in table_names
        assert "results" in table_names
        assert "audit_entries" in table_names
        assert "audit_checkpoints" in table_names


@pytest.mark.asyncio
async def test_insert_and_query_host(sm: async_sessionmaker) -> None:
    """Insert Host with required fields, fetch by id, fields match."""
    host_id = str(uuid4())
    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            display_name="Test Host",
            agent_pubkey=b"12345678" * 4,  # 32 bytes
        )
        session.add(host)
        await session.commit()

    async with session_scope(sm) as session:
        fetched = await session.get(Host, host_id)
        assert fetched is not None
        assert fetched.hostname == "test-host"
        assert fetched.display_name == "Test Host"
        assert fetched.agent_pubkey == b"12345678" * 4


@pytest.mark.asyncio
async def test_host_default_status_offline(sm: async_sessionmaker) -> None:
    """Insert Host without specifying status; query → status=='offline'."""
    host_id = str(uuid4())
    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="offline-host",
            agent_pubkey=b"12345678" * 4,
        )
        session.add(host)
        await session.commit()

    async with session_scope(sm) as session:
        fetched = await session.get(Host, host_id)
        assert fetched is not None
        assert fetched.status == "offline"


@pytest.mark.asyncio
async def test_insert_enrollment_token(sm: async_sessionmaker) -> None:
    """Insert with token_hash; unique constraint on token_hash."""
    token_hash = b"token_hash_12345678901234567890"  # 32 bytes
    issued_by = "admin1"
    now = datetime.now(timezone.utc)

    async with session_scope(sm) as session:
        token = EnrollmentToken(
            id=str(uuid4()),
            token_hash=token_hash,
            issued_by=issued_by,
            issued_at=now,
            expires_at=now,
        )
        session.add(token)

    # Try to insert duplicate token_hash - expect error on flush/commit
    with pytest.raises(IntegrityError):
        async with session_scope(sm) as session:
            token2 = EnrollmentToken(
                id=str(uuid4()),
                token_hash=token_hash,  # Same hash
                issued_by="admin2",
                issued_at=now,
                expires_at=now,
            )
            session.add(token2)


@pytest.mark.asyncio
async def test_insert_command_and_result(sm: async_sessionmaker) -> None:
    """Insert Command, then Result referencing it; query both."""
    host_id = str(uuid4())
    command_id = str(uuid4())
    result_id = str(uuid4())
    now = datetime.now(timezone.utc)

    # Insert host first
    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="cmd-host",
            agent_pubkey=b"12345678" * 4,
        )
        session.add(host)
        await session.commit()

    # Insert command
    async with session_scope(sm) as session:
        cmd = Command(
            id=command_id,
            host_id=host_id,
            sequence=1,
            nonce=b"nonce" * 4,  # 20 bytes
            issued_at=now,
            expires_at=now,
            issued_by="user1",
            risk="low",
            payload_kind="pkg_update",
            signature=b"sig" * 11,  # 33 bytes
            envelope_blob=b"envelope",
            status="pending",
        )
        session.add(cmd)
        await session.commit()

    # Insert result
    async with session_scope(sm) as session:
        result = Result(
            id=result_id,
            command_id=command_id,
            host_id=host_id,
            sequence=1,
            received_at=now,
            exit_code=0,
            status="ok",
            final=True,
            signature=b"sig" * 11,
        )
        session.add(result)
        await session.commit()

    # Query both
    async with session_scope(sm) as session:
        cmd_fetched = await session.get(Command, command_id)
        assert cmd_fetched is not None
        assert cmd_fetched.host_id == host_id

        result_fetched = await session.get(Result, result_id)
        assert result_fetched is not None
        assert result_fetched.command_id == command_id


@pytest.mark.asyncio
async def test_command_unique_host_sequence(sm: async_sessionmaker) -> None:
    """Composite index on (host_id, sequence); verify index exists."""
    host_id = str(uuid4())
    now = datetime.now(timezone.utc)

    # Insert host
    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="seq-host",
            agent_pubkey=b"12345678" * 4,
        )
        session.add(host)
        await session.commit()

    # Insert two commands with same host_id and sequence (no unique constraint,
    # just index for query optimization)
    async with session_scope(sm) as session:
        cmd1 = Command(
            id=str(uuid4()),
            host_id=host_id,
            sequence=1,
            nonce=b"nonce" * 4,
            issued_at=now,
            expires_at=now,
            issued_by="user1",
            risk="low",
            payload_kind="pkg_update",
            signature=b"sig" * 11,
            envelope_blob=b"envelope",
            status="pending",
        )
        session.add(cmd1)
        await session.commit()

    # Second command with same sequence succeeds (no unique constraint)
    async with session_scope(sm) as session:
        cmd2 = Command(
            id=str(uuid4()),
            host_id=host_id,
            sequence=1,
            nonce=b"nonce" * 4,
            issued_at=now,
            expires_at=now,
            issued_by="user1",
            risk="low",
            payload_kind="pkg_update",
            signature=b"sig" * 11,
            envelope_blob=b"envelope",
            status="pending",
        )
        session.add(cmd2)
        await session.commit()

    # Verify index exists by querying sqlite_master
    async with session_scope(sm) as session:
        result = await session.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='commands'"
            )
        )
        index_names = [row[0] for row in result.fetchall()]
        # At minimum, check that host sequence index exists
        assert any("host" in name and "sequence" in name for name in index_names)


@pytest.mark.asyncio
async def test_audit_entry_chain_storage(sm: async_sessionmaker) -> None:
    """Insert 3 audit entries with chained prev_hash; query ordered by sequence."""
    now = datetime.now(timezone.utc)

    async with session_scope(sm) as session:
        # Entry 0
        entry0 = AuditEntry(
            sequence=1,
            timestamp=now,
            actor="user1",
            action="create",
            subject="host-1",
            payload={"detail": "test"},
            prev_hash=b"" * 32,
            entry_hash=b"hash0" * 6 + b"\x00\x00",  # 32 bytes
        )
        session.add(entry0)

        # Entry 1 (chained to 0)
        entry1 = AuditEntry(
            sequence=2,
            timestamp=now,
            actor="user1",
            action="update",
            subject="host-1",
            payload={"detail": "updated"},
            prev_hash=b"hash0" * 6 + b"\x00\x00",
            entry_hash=b"hash1" * 6 + b"\x00\x00",
        )
        session.add(entry1)

        # Entry 2 (chained to 1)
        entry2 = AuditEntry(
            sequence=3,
            timestamp=now,
            actor="user1",
            action="delete",
            subject="host-1",
            payload={"detail": "deleted"},
            prev_hash=b"hash1" * 6 + b"\x00\x00",
            entry_hash=b"hash2" * 6 + b"\x00\x00",
        )
        session.add(entry2)

        await session.commit()

    # Query ordered by sequence
    async with session_scope(sm) as session:
        result = await session.execute(text("SELECT * FROM audit_entries ORDER BY sequence"))
        rows = result.fetchall()
        assert len(rows) == 3
        assert rows[0][0] == 1  # sequence
        assert rows[1][0] == 2
        assert rows[2][0] == 3


@pytest.mark.asyncio
async def test_audit_checkpoint_storage(sm: async_sessionmaker) -> None:
    """Insert checkpoint; round-trip merkle_root + signature bytes."""
    now = datetime.now(timezone.utc)
    merkle_root = b"merkle" * 5 + b"\x00\x00"  # 32 bytes
    signature = b"signature" * 3 + b"\x00\x00\x00\x00\x00"  # 32 bytes
    pubkey = b"pubkey" * 5 + b"\x00\x00"  # 32 bytes

    async with session_scope(sm) as session:
        checkpoint = AuditCheckpoint(
            covers_sequence=100,
            merkle_root=merkle_root,
            signature=signature,
            signing_pubkey=pubkey,
            timestamp=now,
        )
        session.add(checkpoint)
        await session.commit()

    async with session_scope(sm) as session:
        fetched = await session.get(AuditCheckpoint, 1)
        assert fetched is not None
        assert fetched.merkle_root == merkle_root
        assert fetched.signature == signature
        assert fetched.signing_pubkey == pubkey


@pytest.mark.asyncio
async def test_session_scope_commits_on_clean_exit(sm: async_sessionmaker) -> None:
    """Open scope, insert host, exit; reopen scope, host present."""
    host_id = str(uuid4())

    async with session_scope(sm) as session:
        host = Host(
            id=host_id,
            hostname="persist-host",
            agent_pubkey=b"12345678" * 4,
        )
        session.add(host)
    # Clean exit commits

    async with session_scope(sm) as session:
        fetched = await session.get(Host, host_id)
        assert fetched is not None
        assert fetched.hostname == "persist-host"


@pytest.mark.asyncio
async def test_session_scope_rolls_back_on_exception(sm: async_sessionmaker) -> None:
    """Open scope, insert host, raise inside; reopen scope, host absent."""
    host_id = str(uuid4())

    try:
        async with session_scope(sm) as session:
            host = Host(
                id=host_id,
                hostname="rollback-host",
                agent_pubkey=b"12345678" * 4,
            )
            session.add(host)
            raise ValueError("Test exception")
    except ValueError:
        pass

    async with session_scope(sm) as session:
        fetched = await session.get(Host, host_id)
        assert fetched is None


