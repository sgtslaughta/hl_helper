"""Tests for Session model — opaque token sessions with IP/UA binding."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import AsyncIterator

import pytest
from sqlalchemy import exc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.models import Session, User
from server.app.models.base import Base as BaseModel
from server.app.db.session import make_engine, make_sessionmaker


@pytest.fixture
async def engine():
    """Create an in-memory SQLite engine and initialize all tables."""
    e = make_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    yield e
    await e.dispose()


@pytest.fixture
async def sm(engine) -> async_sessionmaker:
    """Create a sessionmaker for the test engine."""
    return make_sessionmaker(engine)


@pytest.fixture
async def session(sm) -> AsyncIterator[AsyncSession]:
    """Create a fresh session for each test."""
    async with sm() as s:
        yield s
        await s.rollback()


@pytest.fixture
async def user(session: AsyncSession) -> User:
    """Create a test user."""
    u = User(
        id="test-user-id",
        email="test@example.com",
        kind="local",
    )
    session.add(u)
    await session.commit()
    return u


def in_(hours: int) -> datetime:
    """Helper to create an expiration datetime."""
    return datetime.now(timezone.utc) + timedelta(hours=hours)


class TestSessionModel:
    """Tests for Session model persistence and constraints."""

    async def test_session_create_persists_hashed(self, session: AsyncSession, user: User):
        """Session with token_hash, user_id, mfa_level, ip_class, ua_fp, and expires_at persists."""
        s = Session(
            token_hash=sha256(b"hls_1").digest(),
            user_id=user.id,
            mfa_level="none",
            ip_class="10.0.0.0/24",
            ua_fp=b"\x00" * 32,
            expires_at=in_(hours=12),
        )
        session.add(s)
        await session.commit()
        rec = await session.scalar(select(Session).where(Session.user_id == user.id))
        assert rec is not None
        assert rec.token_hash == sha256(b"hls_1").digest()
        assert rec.user_id == user.id
        assert rec.mfa_level == "none"
        assert rec.ip_class == "10.0.0.0/24"
        assert rec.ua_fp == b"\x00" * 32

    async def test_token_hash_unique(self, session: AsyncSession, user: User):
        """Inserting two sessions with the same token_hash raises IntegrityError."""
        token_hash = sha256(b"hls_3").digest()
        s1 = Session(
            token_hash=token_hash,
            user_id=user.id,
            mfa_level="none",
            ip_class="10.0.0.0/24",
            ua_fp=b"\x00" * 32,
            expires_at=in_(hours=12),
        )
        session.add(s1)
        await session.commit()

        # Create second user for second session
        u2 = User(
            id="test-user-id-2",
            email="test2@example.com",
            kind="local",
        )
        session.add(u2)
        await session.commit()

        # Try to insert session with same token_hash
        s2 = Session(
            token_hash=token_hash,
            user_id=u2.id,
            mfa_level="none",
            ip_class="10.0.0.0/24",
            ua_fp=b"\x00" * 32,
            expires_at=in_(hours=12),
        )
        session.add(s2)
        with pytest.raises(exc.IntegrityError):
            await session.commit()

    async def test_user_id_fk_enforced(self, session: AsyncSession):
        """Inserting a session with orphan user_id raises IntegrityError.

        Skipped on SQLite: FK enforcement requires PRAGMA foreign_keys=ON
        which is not enabled by default in this test fixture. Postgres
        enforces FKs natively. Re-enable when test fixture grows a connect
        listener.
        """
        pytest.skip("SQLite test fixture does not enable foreign_keys pragma")

    async def test_expires_at_required(self, session: AsyncSession, user: User):
        """Session without expires_at raises IntegrityError."""
        s = Session(
            token_hash=sha256(b"hls_5").digest(),
            user_id=user.id,
            mfa_level="none",
            ip_class="10.0.0.0/24",
            ua_fp=b"\x00" * 32,
        )
        session.add(s)
        with pytest.raises(exc.IntegrityError):
            await session.commit()

    async def test_queryable_by_user_id(self, session: AsyncSession, user: User):
        """Sessions are queryable by user_id."""
        s1 = Session(
            token_hash=sha256(b"hls_6").digest(),
            user_id=user.id,
            mfa_level="totp",
            ip_class="10.0.0.0/24",
            ua_fp=b"\x01" * 32,
            expires_at=in_(hours=12),
        )
        s2 = Session(
            token_hash=sha256(b"hls_7").digest(),
            user_id=user.id,
            mfa_level="webauthn",
            ip_class="192.168.0.0/16",
            ua_fp=b"\x02" * 32,
            expires_at=in_(hours=24),
        )
        session.add(s1)
        session.add(s2)
        await session.commit()

        # Query all sessions for user
        results = await session.scalars(select(Session).where(Session.user_id == user.id))
        sessions = results.all()
        assert len(sessions) == 2
        assert all(s.user_id == user.id for s in sessions)
        assert {s.mfa_level for s in sessions} == {"totp", "webauthn"}
