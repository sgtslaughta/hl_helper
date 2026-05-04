"""Tests for server.app.audit.sql_chain."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.sql import text

from server.app.audit.chain import (
    GENESIS_HASH,
    ChainBrokenError,
    CheckpointError,
)
from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.signing import FileBackend
from server.app.db.session import make_engine, make_sessionmaker
from server.app.models import Base


@pytest.fixture
def backend(tmp_path: Path) -> FileBackend:
    return FileBackend.bootstrap(tmp_path / "signing")


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
async def session(sm: async_sessionmaker) -> AsyncSession:
    """Provide a session that auto-commits."""
    s = sm()
    try:
        yield s
    finally:
        await s.close()


@pytest_asyncio.fixture
async def chain(backend: FileBackend) -> SqlAuditChain:
    return SqlAuditChain(backend, checkpoint_interval=100)


class TestGenesisStateEmptyDb:
    @pytest.mark.asyncio
    async def test_genesis_state_empty_db(
        self, chain: SqlAuditChain, session: AsyncSession
    ) -> None:
        assert await chain.length(session) == 0
        assert await chain.head_hash(session) == GENESIS_HASH
        await chain.verify(session)  # Should not raise


class TestAppendPersistsToDb:
    @pytest.mark.asyncio
    async def test_append_persists_to_db(
        self, chain: SqlAuditChain, session: AsyncSession
    ) -> None:
        entry1 = await chain.append(
            session, actor="user1", action="action1"
        )
        entry2 = await chain.append(
            session, actor="user2", action="action2"
        )
        entry3 = await chain.append(
            session, actor="user3", action="action3"
        )

        assert entry1.sequence == 0
        assert entry2.sequence == 1
        assert entry3.sequence == 2
        assert await chain.length(session) == 3

        # Query DB directly
        result = await session.execute(text("SELECT COUNT(*) FROM audit_entries"))
        count = result.scalar()
        assert count == 3


class TestChainLinksPeristed:
    @pytest.mark.asyncio
    async def test_chain_links_persisted(
        self, chain: SqlAuditChain, session: AsyncSession
    ) -> None:
        entry1 = await chain.append(
            session, actor="user1", action="action1"
        )
        entry2 = await chain.append(
            session, actor="user2", action="action2"
        )

        assert entry2.prev_hash == entry1.entry_hash


class TestAutoCheckpointAtInterval:
    @pytest.mark.asyncio
    async def test_auto_checkpoint_at_interval(
        self, backend: FileBackend, sm: async_sessionmaker
    ) -> None:
        chain = SqlAuditChain(backend, checkpoint_interval=3)
        session = sm()
        try:
            await chain.append(session, actor="user1", action="action1")
            await chain.append(session, actor="user2", action="action2")

            result = await session.execute(
                text("SELECT COUNT(*) FROM audit_checkpoints")
            )
            count = result.scalar()
            assert count == 0

            await chain.append(session, actor="user3", action="action3")
            result = await session.execute(
                text("SELECT COUNT(*) FROM audit_checkpoints")
            )
            count = result.scalar()
            assert count == 1

            await chain.append(session, actor="user4", action="action4")
            await chain.append(session, actor="user5", action="action5")

            result = await session.execute(
                text("SELECT COUNT(*) FROM audit_checkpoints")
            )
            count = result.scalar()
            assert count == 1

            await chain.append(session, actor="user6", action="action6")
            result = await session.execute(
                text("SELECT COUNT(*) FROM audit_checkpoints")
            )
            count = result.scalar()
            assert count == 2
        finally:
            await session.close()


class TestCheckpointSignatureVerifies:
    @pytest.mark.asyncio
    async def test_checkpoint_signature_verifies_via_backend(
        self, backend: FileBackend, sm: async_sessionmaker
    ) -> None:
        chain = SqlAuditChain(backend, checkpoint_interval=100)
        session = sm()
        try:
            await chain.append(session, actor="user1", action="action1")
            checkpoint = await chain.force_checkpoint(session)

            signed_message = (
                checkpoint.covers_sequence.to_bytes(8, "big")
                + checkpoint.merkle_root
            )
            assert backend.verify(signed_message, checkpoint.signature)
        finally:
            await session.close()


class TestVerifyPassesCleanChain:
    @pytest.mark.asyncio
    async def test_verify_passes_clean_chain(
        self, chain: SqlAuditChain, session: AsyncSession
    ) -> None:
        for i in range(5):
            await chain.append(session, actor=f"user{i}", action=f"action{i}")
        await session.commit()
        await chain.verify(session)  # Should not raise


class TestVerifyDetectsTamperedPayload:
    @pytest.mark.asyncio
    async def test_verify_detects_tampered_payload(
        self, chain: SqlAuditChain, session: AsyncSession
    ) -> None:
        await chain.append(session, actor="user1", action="action1")
        await chain.append(session, actor="user2", action="action2")
        await chain.append(session, actor="user3", action="action3")

        # Tamper with payload directly via SQL
        await session.execute(
            text("UPDATE audit_entries SET payload='{\"tampered\": true}' WHERE sequence=1")
        )
        await session.commit()

        with pytest.raises(ChainBrokenError):
            await chain.verify(session)


class TestVerifyDetectsBrokenLink:
    @pytest.mark.asyncio
    async def test_verify_detects_broken_link(
        self, chain: SqlAuditChain, session: AsyncSession
    ) -> None:
        await chain.append(session, actor="user1", action="action1")
        await chain.append(session, actor="user2", action="action2")

        # Tamper with prev_hash directly via SQL
        await session.execute(
            text(
                "UPDATE audit_entries SET "
                "prev_hash=X'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' "
                "WHERE sequence=1"
            )
        )
        await session.commit()

        with pytest.raises(ChainBrokenError):
            await chain.verify(session)


class TestVerifyDetectsTamperedCheckpoint:
    @pytest.mark.asyncio
    async def test_verify_detects_tampered_checkpoint(
        self, chain: SqlAuditChain, session: AsyncSession
    ) -> None:
        await chain.append(session, actor="user1", action="action1")
        await chain.force_checkpoint(session)

        # Tamper with merkle_root directly via SQL
        await session.execute(
            text(
                "UPDATE audit_checkpoints SET "
                "merkle_root=X'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'"
            )
        )
        await session.commit()

        with pytest.raises(CheckpointError):
            await chain.verify(session)


class TestPersistenceAcrossSessions:
    @pytest.mark.asyncio
    async def test_persistence_across_sessions(
        self, chain: SqlAuditChain, sm: async_sessionmaker
    ) -> None:
        session1 = sm()
        try:
            await chain.append(session1, actor="user1", action="action1")
            await chain.append(session1, actor="user2", action="action2")
            await session1.commit()
        finally:
            await session1.close()

        # Open new session and verify
        session2 = sm()
        try:
            assert await chain.length(session2) == 2
            await chain.verify(session2)  # Should not raise
        finally:
            await session2.close()


class TestForceCheckpoint:
    @pytest.mark.asyncio
    async def test_force_checkpoint(
        self, backend: FileBackend, sm: async_sessionmaker
    ) -> None:
        chain = SqlAuditChain(backend, checkpoint_interval=100)
        session = sm()
        try:
            await chain.append(session, actor="user1", action="action1")
            await chain.append(session, actor="user2", action="action2")

            checkpoint = await chain.force_checkpoint(session)
            assert checkpoint.covers_sequence == 1
        finally:
            await session.close()


class TestConcurrentAppends:
    @pytest.mark.asyncio
    async def test_concurrent_appends_no_duplicate_sequences(
        self, backend: FileBackend, sm: async_sessionmaker
    ) -> None:
        """Fire N concurrent appends and verify all succeed with unique sequences."""
        chain = SqlAuditChain(backend, checkpoint_interval=100)
        n = 20

        async def append_entry(i: int) -> int:
            session = sm()
            try:
                entry = await chain.append(session, actor=f"user{i}", action=f"action{i}")
                await session.commit()
                return entry.sequence
            finally:
                await session.close()

        # Fire all concurrent appends
        sequences = await asyncio.gather(*[append_entry(i) for i in range(n)])

        # All sequences should be unique and form exact permutation 0..n-1
        assert sorted(sequences) == list(range(n))
        assert len(set(sequences)) == n


class TestLargeChainVerify:
    @pytest.mark.asyncio
    async def test_large_chain_verify_succeeds(
        self, chain: SqlAuditChain, session: AsyncSession
    ) -> None:
        """Verify large chain (1000+ entries) without loading all into memory."""
        # Add 1000 entries
        for i in range(1000):
            await chain.append(session, actor=f"user{i}", action=f"action{i}")
        await session.commit()

        # Verify should succeed without excessive memory usage
        await chain.verify(session)  # Should not raise


class TestCheckpointFilePersistence:
    @pytest.mark.asyncio
    async def test_checkpoint_writes_to_disk(
        self, backend: FileBackend, session: AsyncSession, tmp_path: Path
    ) -> None:
        """Verify checkpoint file is written to disk with correct content."""
        checkpoint_dir = tmp_path / "audit_checkpoints"
        chain = SqlAuditChain(
            backend, checkpoint_interval=100, checkpoint_dir=checkpoint_dir
        )

        # Add 100 entries to trigger checkpoint
        for i in range(100):
            await chain.append(session, actor=f"user{i}", action=f"action{i}")
        await session.commit()

        # Wait a moment to ensure flush
        await asyncio.sleep(0.1)

        # Verify checkpoint file exists
        checkpoint_files = list(checkpoint_dir.glob("*.json"))
        assert len(checkpoint_files) > 0, "No checkpoint files written"

        # Read and validate checkpoint file
        checkpoint_file = checkpoint_files[0]
        with open(checkpoint_file) as f:
            checkpoint_data = json.load(f)

        # Verify structure
        assert "sequence" in checkpoint_data
        assert "root_hash" in checkpoint_data
        assert "signed_at" in checkpoint_data
        assert "signature" in checkpoint_data
        assert checkpoint_data["sequence"] == 99  # 0-indexed, 100 entries
