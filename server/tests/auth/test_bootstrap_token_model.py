"""Tests for BootstrapToken model."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from server.app.db.session import make_engine, make_sessionmaker
from server.app.models import Base, BootstrapToken


@pytest.mark.asyncio
async def test_bootstrap_token_persists():
    """Test that BootstrapToken model persists to database."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)

    # Create and persist a token
    token_hash = hashlib.sha256(b"test_token").digest()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=1)

    token = BootstrapToken(
        token_hash=token_hash,
        expires_at=expires_at,
    )

    async with sm() as session:
        session.add(token)
        await session.commit()
        token_id = token.id

    # Retrieve and verify
    async with sm() as session:
        retrieved = await session.get(BootstrapToken, token_id)
        assert retrieved is not None
        assert retrieved.token_hash == token_hash
        assert retrieved.consumed_at is None
        # SQLite returns naive datetimes; compare without timezone
        assert retrieved.expires_at.replace(tzinfo=None) == expires_at.replace(tzinfo=None)

    await engine.dispose()


@pytest.mark.asyncio
async def test_bootstrap_token_unique_constraint():
    """Test that token_hash has unique constraint."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)

    token_hash = hashlib.sha256(b"unique_test").digest()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=1)

    # Insert first token
    async with sm() as session:
        token1 = BootstrapToken(token_hash=token_hash, expires_at=expires_at)
        session.add(token1)
        await session.commit()

    # Try to insert duplicate
    async with sm() as session:
        token2 = BootstrapToken(token_hash=token_hash, expires_at=expires_at)
        session.add(token2)
        with pytest.raises(IntegrityError):
            await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_bootstrap_token_expires_at_required():
    """Test that expires_at is required."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)

    token_hash = hashlib.sha256(b"test").digest()

    # expires_at is required, should fail without it
    async with sm() as session:
        token = BootstrapToken(token_hash=token_hash)
        session.add(token)
        with pytest.raises(Exception):  # SQLAlchemy constraint violation
            await session.commit()

    await engine.dispose()


def test_bootstrap_token_ttl_minutes():
    """Test that TTL minutes constant is 60."""
    assert BootstrapToken.ttl_minutes() == 60
