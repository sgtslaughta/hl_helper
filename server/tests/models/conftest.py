"""Fixtures for model tests."""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from server.app.db.session import make_engine, make_sessionmaker
from server.app.models import Base


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
