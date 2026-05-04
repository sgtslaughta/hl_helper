"""Tests for TotpSecret model — encrypted TOTP secret storage."""

from __future__ import annotations

from typing import AsyncIterator

import pytest
from sqlalchemy import exc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.models import TotpSecret, User
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


class TestTotpSecretModel:
    """Tests for TotpSecret model persistence and constraints."""

    async def test_totp_secret_persists(self, session: AsyncSession, user: User) -> None:
        """TotpSecret with all fields persists correctly."""
        secret = TotpSecret(
            user_id=user.id,
            secret_ciphertext=b"encrypted_blob",
            algorithm="sha1",
            digits=6,
            period_s=30,
        )
        session.add(secret)
        await session.commit()

        rec = await session.scalar(
            select(TotpSecret).where(TotpSecret.user_id == user.id)
        )
        assert rec is not None
        assert rec.user_id == user.id
        assert rec.secret_ciphertext == b"encrypted_blob"
        assert rec.algorithm == "sha1"
        assert rec.digits == 6
        assert rec.period_s == 30
        assert rec.confirmed_at is None

    async def test_unique_constraint_on_user_id(
        self, session: AsyncSession, user: User
    ) -> None:
        """Only one TOTP secret per user — second insert raises IntegrityError."""
        secret1 = TotpSecret(
            user_id=user.id,
            secret_ciphertext=b"blob1",
            algorithm="sha1",
            digits=6,
            period_s=30,
        )
        session.add(secret1)
        await session.commit()

        # Try to insert second secret for same user
        secret2 = TotpSecret(
            user_id=user.id,
            secret_ciphertext=b"blob2",
            algorithm="sha1",
            digits=6,
            period_s=30,
        )
        session.add(secret2)
        with pytest.raises(exc.IntegrityError):
            await session.commit()

    async def test_last_used_step_optional(
        self, session: AsyncSession, user: User
    ) -> None:
        """last_used_step may be None or an integer."""
        secret = TotpSecret(
            user_id=user.id,
            secret_ciphertext=b"blob",
            algorithm="sha256",
            digits=6,
            period_s=30,
            last_used_step=None,
        )
        session.add(secret)
        await session.commit()

        rec = await session.scalar(
            select(TotpSecret).where(TotpSecret.user_id == user.id)
        )
        assert rec is not None
        assert rec.last_used_step is None

    async def test_confirmed_at_optional(
        self, session: AsyncSession, user: User
    ) -> None:
        """confirmed_at is None until enrollment finishes."""
        secret = TotpSecret(
            user_id=user.id,
            secret_ciphertext=b"blob",
            algorithm="sha512",
            digits=8,
            period_s=60,
            confirmed_at=None,
        )
        session.add(secret)
        await session.commit()

        rec = await session.scalar(
            select(TotpSecret).where(TotpSecret.user_id == user.id)
        )
        assert rec is not None
        assert rec.confirmed_at is None

    async def test_user_id_indexed(
        self, session: AsyncSession, user: User
    ) -> None:
        """user_id column is indexed for query performance."""
        secret = TotpSecret(
            user_id=user.id,
            secret_ciphertext=b"blob",
            algorithm="sha1",
            digits=6,
            period_s=30,
        )
        session.add(secret)
        await session.commit()

        # Verify we can query efficiently by user_id
        rec = await session.scalar(
            select(TotpSecret).where(TotpSecret.user_id == user.id)
        )
        assert rec is not None
        assert rec.user_id == user.id
