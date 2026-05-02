"""Database session management for async operations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def make_engine(db_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create AsyncEngine. For SQLite ensures `aiosqlite` driver."""
    return create_async_engine(db_url, echo=echo)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a sessionmaker for the given engine."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope(sm: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Yield a session; commit on clean exit, rollback on exception."""
    session = sm()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
