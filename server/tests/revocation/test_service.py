"""Tests for RevocationService."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.signing import FileBackend
from server.app.db.session import make_engine, make_sessionmaker
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.models import Base, Host, RevokedCert
from server.app.revocation.service import (
    HostAlreadyRevokedError,
    HostNotFoundError,
    RevocationService,
)


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    """Create an in-memory SQLite engine and initialize all tables."""
    e = make_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def sm(engine: AsyncEngine) -> async_sessionmaker:
    """Create a sessionmaker for the test engine."""
    return make_sessionmaker(engine)


@pytest_asyncio.fixture
def dispatcher() -> CommandDispatcher:
    """Create a command dispatcher."""
    return CommandDispatcher()


@pytest_asyncio.fixture
def signing_backend(tmp_path):
    """Create a signing backend."""
    return FileBackend.bootstrap(tmp_path / "signing")


@pytest_asyncio.fixture
def audit_chain(signing_backend: FileBackend) -> SqlAuditChain:
    """Create an audit chain."""
    return SqlAuditChain(signing_backend, checkpoint_interval=100)


@pytest_asyncio.fixture
def revocation_service(
    dispatcher: CommandDispatcher,
    audit_chain: SqlAuditChain,
) -> RevocationService:
    """Create a revocation service."""
    return RevocationService(dispatcher=dispatcher, audit=audit_chain)


@pytest.mark.asyncio
async def test_revoke_inserts_revoked_cert_row(
    sm: async_sessionmaker,
    revocation_service: RevocationService,
):
    """Test that revoke() inserts a RevokedCert row."""
    async with sm() as session:
        # Create a host with cert_serial
        host = Host(
            id="test-host-1",
            hostname="test.example.com",
            agent_pubkey=b"x" * 32,
            cert_serial="abc123",
        )
        session.add(host)
        await session.flush()

        # Revoke
        now = datetime.now(timezone.utc)
        await revocation_service.revoke(
            session,
            host_id="test-host-1",
            actor="admin",
            reason="decommissioned",
            now=now,
        )

        # Query the revoked_cert row
        result = await session.execute(select(RevokedCert))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].serial == "abc123"
        assert rows[0].host_id == "test-host-1"
        assert rows[0].reason == "decommissioned"


@pytest.mark.asyncio
async def test_revoke_sets_host_status_revoked(
    sm: async_sessionmaker,
    revocation_service: RevocationService,
):
    """Test that revoke() sets host.status='revoked'."""
    async with sm() as session:
        host = Host(
            id="test-host-1",
            hostname="test.example.com",
            agent_pubkey=b"x" * 32,
            cert_serial="abc123",
        )
        session.add(host)
        await session.flush()

        await revocation_service.revoke(
            session,
            host_id="test-host-1",
            actor="admin",
        )

        # Refresh the host
        refreshed = await session.get(Host, "test-host-1")
        assert refreshed.status == "revoked"


@pytest.mark.asyncio
async def test_revoke_unknown_host_raises_not_found(
    sm: async_sessionmaker,
    revocation_service: RevocationService,
):
    """Test that revoke() raises HostNotFoundError for unknown host."""
    async with sm() as session:
        with pytest.raises(HostNotFoundError):
            await revocation_service.revoke(
                session,
                host_id="nonexistent",
                actor="admin",
            )


@pytest.mark.asyncio
async def test_revoke_already_revoked_raises_conflict(
    sm: async_sessionmaker,
    revocation_service: RevocationService,
):
    """Test that revoke() raises HostAlreadyRevokedError if already revoked."""
    async with sm() as session:
        host = Host(
            id="test-host-1",
            hostname="test.example.com",
            agent_pubkey=b"x" * 32,
            cert_serial="abc123",
            status="revoked",
        )
        session.add(host)
        await session.flush()

        with pytest.raises(HostAlreadyRevokedError):
            await revocation_service.revoke(
                session,
                host_id="test-host-1",
                actor="admin",
            )


@pytest.mark.asyncio
async def test_revoke_emits_audit_entry(
    sm: async_sessionmaker,
    revocation_service: RevocationService,
    audit_chain: SqlAuditChain,
):
    """Test that revoke() creates an audit entry."""
    async with sm() as session:
        host = Host(
            id="test-host-1",
            hostname="test.example.com",
            agent_pubkey=b"x" * 32,
            cert_serial="abc123",
        )
        session.add(host)
        await session.flush()

        await revocation_service.revoke(
            session,
            host_id="test-host-1",
            actor="admin",
            reason="decommissioned",
        )

        # Verify audit chain length increased
        from server.app.models.audit import AuditEntry

        result = await session.execute(select(AuditEntry))
        entries = result.scalars().all()
        assert len(entries) == 1
        assert entries[0].action == "host.revoke"
        assert entries[0].actor == "admin"
        assert entries[0].subject == "test-host-1"
        assert entries[0].payload.get("reason") == "decommissioned"


@pytest.mark.asyncio
async def test_revoke_terminates_active_stream(
    sm: async_sessionmaker,
    dispatcher: CommandDispatcher,
    revocation_service: RevocationService,
):
    """Test that revoke() terminates active stream."""
    # Register a host as connected
    state = await dispatcher.register("test-host-1")

    async with sm() as session:
        host = Host(
            id="test-host-1",
            hostname="test.example.com",
            agent_pubkey=b"x" * 32,
            cert_serial="abc123",
        )
        session.add(host)
        await session.flush()

        await revocation_service.revoke(
            session,
            host_id="test-host-1",
            actor="admin",
        )

        # Check that terminate_event is set
        assert state.terminate_event.is_set()


@pytest.mark.asyncio
async def test_is_revoked_reflects_state(
    sm: async_sessionmaker,
    revocation_service: RevocationService,
):
    """Test that is_revoked() reflects in-memory state after revoke."""
    async with sm() as session:
        host = Host(
            id="test-host-1",
            hostname="test.example.com",
            agent_pubkey=b"x" * 32,
            cert_serial="abc123",
        )
        session.add(host)
        await session.flush()

        # Before revoke
        assert not await revocation_service.is_revoked("abc123")

        await revocation_service.revoke(
            session,
            host_id="test-host-1",
            actor="admin",
        )

        # After revoke
        assert await revocation_service.is_revoked("abc123")


@pytest.mark.asyncio
async def test_load_from_db_populates_set(
    sm: async_sessionmaker,
    revocation_service: RevocationService,
):
    """Test that load_from_db() populates in-memory CRL from DB."""
    async with sm() as session:
        # Pre-insert revoked cert rows
        cert1 = RevokedCert(
            serial="serial1",
            host_id="host1",
            revoked_at=datetime.now(timezone.utc),
        )
        cert2 = RevokedCert(
            serial="serial2",
            host_id="host2",
            revoked_at=datetime.now(timezone.utc),
        )
        session.add(cert1)
        session.add(cert2)
        await session.flush()

        # Load from DB
        await revocation_service.load_from_db(session)

        # Verify is_revoked works
        assert await revocation_service.is_revoked("serial1")
        assert await revocation_service.is_revoked("serial2")
        assert not await revocation_service.is_revoked("serial3")
