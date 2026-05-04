"""Tests for server.app.audit.retention."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from server.app.audit.retention import RetentionSweeper
from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.signing import FileBackend
from server.app.db.session import make_engine, make_sessionmaker
from server.app.models import Base
from server.app.models.audit import AuditCheckpoint, AuditEntry


@pytest.fixture
def backend(tmp_path: Path) -> FileBackend:
    return FileBackend.bootstrap(tmp_path / "signing")


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    e = make_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def sm(engine: AsyncEngine) -> async_sessionmaker:
    return make_sessionmaker(engine)


@pytest_asyncio.fixture
async def chain(backend: FileBackend) -> SqlAuditChain:
    return SqlAuditChain(backend, checkpoint_interval=1000)


@pytest.mark.asyncio
async def test_no_op_when_retention_disabled(sm, chain) -> None:
    sweeper = RetentionSweeper(sm, chain, retention_days=0)
    deleted = await sweeper.sweep()
    assert deleted == 0


@pytest.mark.asyncio
async def test_no_op_on_empty_chain(sm, chain) -> None:
    sweeper = RetentionSweeper(sm, chain, retention_days=7)
    deleted = await sweeper.sweep()
    assert deleted == 0


@pytest.mark.asyncio
async def test_sweep_deletes_old_entries_keeps_recent(sm, chain) -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)
    recent = now - timedelta(days=1)

    async with sm() as s:
        await chain.append(s, actor="a", action="old.1", timestamp=old)
        await chain.append(s, actor="a", action="old.2", timestamp=old)
        await chain.append(s, actor="a", action="recent", timestamp=recent)
        await s.commit()

    sweeper = RetentionSweeper(sm, chain, retention_days=7)
    deleted = await sweeper.sweep(now=now)
    assert deleted == 2

    async with sm() as s:
        remaining = (await s.execute(select(AuditEntry))).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].action == "recent"


@pytest.mark.asyncio
async def test_sweep_preserves_checkpoints(sm, chain) -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)

    async with sm() as s:
        for i in range(3):
            await chain.append(s, actor="a", action=f"e{i}", timestamp=old)
        await s.commit()

    sweeper = RetentionSweeper(sm, chain, retention_days=7)
    await sweeper.sweep(now=now)

    async with sm() as s:
        checkpoints = (await s.execute(select(AuditCheckpoint))).scalars().all()
    # force_checkpoint creates one prune-checkpoint before delete; preserved
    assert len(checkpoints) >= 1


@pytest.mark.asyncio
async def test_oldest_age_diagnostic(sm, chain) -> None:
    now = datetime.now(timezone.utc)
    async with sm() as s:
        await chain.append(s, actor="a", action="x", timestamp=now - timedelta(days=10))
        await s.commit()
    sweeper = RetentionSweeper(sm, chain, retention_days=30)
    age = await sweeper.oldest_entry_age_days(now=now)
    assert age is not None
    assert 9.5 < age < 10.5


@pytest.mark.asyncio
async def test_sweep_idempotent(sm, chain) -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)

    async with sm() as s:
        await chain.append(s, actor="a", action="x", timestamp=old)
        await chain.append(s, actor="a", action="recent", timestamp=now)
        await s.commit()

    sweeper = RetentionSweeper(sm, chain, retention_days=7)
    first = await sweeper.sweep(now=now)
    second = await sweeper.sweep(now=now)
    assert first == 1
    assert second == 0
