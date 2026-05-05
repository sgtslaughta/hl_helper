"""Shared fixtures for plugin tests."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.signing import FileBackend
from server.app.db.session import make_engine, make_sessionmaker
from server.app.models import Base


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create in-memory SQLite engine and initialize all tables."""
    e = make_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def sm(engine: AsyncEngine) -> async_sessionmaker:
    """Create a sessionmaker for the test engine."""
    return make_sessionmaker(engine)


@pytest.fixture
def signing_backend(tmp_path: Path) -> FileBackend:
    """Create a signing backend for audit chain."""
    return FileBackend.bootstrap(tmp_path / "signing")


@pytest.fixture
def audit_chain(signing_backend: FileBackend) -> SqlAuditChain:
    """Create an audit chain instance."""
    return SqlAuditChain(signing_backend)
