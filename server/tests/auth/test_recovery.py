"""Tests for RecoveryService — generate, consume, regenerate, and view tracking."""

from __future__ import annotations

from typing import AsyncIterator

import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.auth.mfa.recovery import RecoveryService, RecoveryCooldown
from server.app.models import User
from server.app.models.base import Base as BaseModel
from server.app.models.recovery_code import RecoveryCode
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


@pytest.fixture
async def svc(sm: async_sessionmaker) -> RecoveryService:
    """Create a RecoveryService."""
    return RecoveryService(sessionmaker=sm)


class TestRecoveryService:
    """Tests for RecoveryService functionality."""

    async def test_generate_returns_10_codes(self, svc: RecoveryService, user: User) -> None:
        """generate() returns 10 plaintext codes."""
        codes = await svc.generate(user, count=10)
        assert len(codes) == 10
        assert all(isinstance(c, str) for c in codes)

    async def test_generate_codes_format(self, svc: RecoveryService, user: User) -> None:
        """generate() codes are 17 chars: 8 hex + dash + 8 hex."""
        codes = await svc.generate(user, count=10)
        for code in codes:
            assert len(code) == 17, f"Code {code} is not 17 chars"
            assert code[8] == "-", f"Code {code} missing dash at position 8"
            # Verify hex chars
            left, right = code.split("-")
            assert len(left) == 8 and len(right) == 8
            assert all(c in "0123456789abcdef" for c in left)
            assert all(c in "0123456789abcdef" for c in right)

    async def test_generate_codes_unique(self, svc: RecoveryService, user: User) -> None:
        """generate() returns unique codes."""
        codes = await svc.generate(user, count=10)
        assert len(codes) == len(set(codes))

    async def test_generate_persists_hashed(
        self, svc: RecoveryService, user: User, session: AsyncSession
    ) -> None:
        """generate() stores hashed codes, not plaintext."""
        codes = await svc.generate(user, count=10)

        # Check DB has 10 rows
        rows = await session.execute(
            select(RecoveryCode).where(RecoveryCode.user_id == user.id)
        )
        db_codes = rows.fetchall()
        assert len(db_codes) == 10

        # Plaintext should never be in DB
        import hashlib
        for code in codes:
            code_hash = hashlib.sha256(code.encode()).digest()
            rows = await session.execute(
                select(RecoveryCode).where(RecoveryCode.code_hash == code_hash)
            )
            # The hash should exist, but we verify plaintext never stored by checking
            # the code_hash is indeed the hash, not the plaintext
            found = rows.fetchone()
            assert found is not None, "Hash not found in DB"

    async def test_consume_single_use(self, svc: RecoveryService, user: User) -> None:
        """consume() accepts a generated code once, then rejects it."""
        codes = await svc.generate(user, count=10)
        code = codes[0]

        # First consume succeeds
        result = await svc.consume(user, code)
        assert result is True

        # Second consume fails
        result = await svc.consume(user, code)
        assert result is False

    async def test_consume_wrong_code(self, svc: RecoveryService, user: User) -> None:
        """consume() rejects wrong codes."""
        await svc.generate(user, count=10)
        wrong_code = "a1b2c3d4-e5f6a7b9"

        result = await svc.consume(user, wrong_code)
        assert result is False

    @freeze_time("2026-05-03 12:00:00")
    async def test_consume_3_wrong_in_60s_triggers_cooldown(
        self, svc: RecoveryService, user: User
    ) -> None:
        """consume() blocks on 3rd wrong code within 60s (not 4th)."""
        await svc.generate(user, count=10)

        # 1st wrong attempt succeeds (returns False, no raise)
        result = await svc.consume(user, "wrong0000-00000000")
        assert result is False

        # 2nd wrong attempt succeeds (returns False, no raise)
        result = await svc.consume(user, "wrong0001-00000001")
        assert result is False

        # 3rd wrong attempt should raise RecoveryCooldown
        with pytest.raises(RecoveryCooldown):
            await svc.consume(user, "wrong0002-00000002")

    @freeze_time("2026-05-03 12:00:00")
    async def test_consume_cooldown_expires_after_60s(
        self, svc: RecoveryService, user: User
    ) -> None:
        """consume() cooldown lasts 60 seconds."""
        await svc.generate(user, count=10)

        # 1st and 2nd attempts succeed (return False)
        await svc.consume(user, "wrong0000-00000000")
        await svc.consume(user, "wrong0001-00000001")

        # 3rd raises
        with pytest.raises(RecoveryCooldown):
            await svc.consume(user, "wrong0002-00000002")

        # After 60 seconds, cooldown expires
        with freeze_time("2026-05-03 12:01:00"):
            result = await svc.consume(user, "wrong0003-00000003")
            assert result is False  # Still wrong code, but no cooldown

    async def test_regenerate_invalidates_old_codes(
        self, svc: RecoveryService, user: User
    ) -> None:
        """regenerate() deletes old codes and creates new set."""
        old_codes = await svc.generate(user, count=10)
        old_code = old_codes[0]

        # Old code works
        result = await svc.consume(user, old_code)
        assert result is True

        # Regenerate
        new_codes = await svc.regenerate(user, count=10)

        # Old codes no longer work
        result = await svc.consume(user, old_codes[1])
        assert result is False

        # New codes work
        result = await svc.consume(user, new_codes[0])
        assert result is True

    async def test_mark_viewed_updates_timestamps(
        self, svc: RecoveryService, user: User, session: AsyncSession
    ) -> None:
        """mark_viewed() sets viewed_at on all unconsumed codes."""
        await svc.generate(user, count=10)

        # Check viewed_at is null
        rows = await session.execute(
            select(RecoveryCode).where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.consumed_at.is_(None),
            )
        )
        initial = rows.fetchall()
        assert all(row[0].viewed_at is None for row in initial)

        # Mark viewed
        await svc.mark_viewed(user)

        # Refresh session to get updated values
        async with svc._sessionmaker() as s:
            rows = await s.execute(
                select(RecoveryCode).where(
                    RecoveryCode.user_id == user.id,
                    RecoveryCode.consumed_at.is_(None),
                )
            )
            final = rows.fetchall()
            assert all(row[0].viewed_at is not None for row in final)

    async def test_list_status_counts(
        self, svc: RecoveryService, user: User
    ) -> None:
        """list_status() returns correct counts after consume + view."""
        codes = await svc.generate(user, count=10)

        # Consume 2 codes
        await svc.consume(user, codes[0])
        await svc.consume(user, codes[1])

        # Mark viewed
        await svc.mark_viewed(user)

        status = await svc.list_status(user)
        assert status.total == 10
        assert status.consumed == 2
        assert status.remaining == 8
        assert status.viewed is True

    async def test_list_status_not_viewed(
        self, svc: RecoveryService, user: User
    ) -> None:
        """list_status() viewed=False if codes never viewed."""
        await svc.generate(user, count=10)

        status = await svc.list_status(user)
        assert status.total == 10
        assert status.consumed == 0
        assert status.remaining == 10
        assert status.viewed is False
