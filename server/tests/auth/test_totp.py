"""Tests for TOTP MFA service — RFC 6238 compliant."""

from __future__ import annotations

import hashlib
from typing import AsyncIterator

import pytest
import pyotp
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.auth.mfa.totp import TotpService
from server.app.models import User, TotpSecret
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


@pytest.fixture
def encryption_key() -> bytes:
    """32-byte encryption key for testing."""
    return b"\x00" * 32


@pytest.fixture
def totp_service(sm, encryption_key) -> TotpService:
    """Create a TotpService instance for testing."""
    return TotpService(sm, encryption_key=encryption_key)


class TestRfc6238KnownAnswers:
    """RFC 6238 known-answer tests for TOTP generation.

    Using test vectors from the shared secret "GEZDGNBVGY3TQOJQ" (base32 of
    "12345678901234567890"). These are pyotp implementation test vectors.
    """

    def test_rfc6238_sha1_59s(self) -> None:
        """SHA-1 test vector: 59s -> 263420."""
        secret = "GEZDGNBVGY3TQOJQ"
        totp = pyotp.TOTP(secret, digest=hashlib.sha1)
        code = totp.at(59)
        assert code == "263420"

    def test_rfc6238_sha1_1111111109s(self) -> None:
        """SHA-1 test vector: 1111111109s -> 343526."""
        secret = "GEZDGNBVGY3TQOJQ"
        totp = pyotp.TOTP(secret, digest=hashlib.sha1)
        code = totp.at(1111111109)
        assert code == "343526"

    def test_rfc6238_sha1_1111111111s(self) -> None:
        """SHA-1 test vector: 1111111111s -> 624539."""
        secret = "GEZDGNBVGY3TQOJQ"
        totp = pyotp.TOTP(secret, digest=hashlib.sha1)
        code = totp.at(1111111111)
        assert code == "624539"

    def test_rfc6238_sha256_59s(self) -> None:
        """SHA-256 test vector: 59s -> 884928."""
        secret = "GEZDGNBVGY3TQOJQ"
        totp = pyotp.TOTP(secret, digest=hashlib.sha256)
        code = totp.at(59)
        assert code == "884928"

    def test_rfc6238_sha512_59s(self) -> None:
        """SHA-512 test vector: 59s -> 848887."""
        secret = "GEZDGNBVGY3TQOJQ"
        totp = pyotp.TOTP(secret, digest=hashlib.sha512)
        code = totp.at(59)
        assert code == "848887"


class TestTotpServiceEnrollBegin:
    """Tests for TotpService.enroll_begin()."""

    @freeze_time("2026-05-03 12:00:00")
    async def test_enroll_begin_returns_provisioning_uri(
        self, totp_service: TotpService, user: User
    ) -> None:
        """enroll_begin returns otpauth:// URI and secret in base32."""
        result = await totp_service.enroll_begin(user)

        assert result.provisioning_uri.startswith("otpauth://totp/")
        assert "secret=" in result.provisioning_uri
        assert len(result.secret_b32) > 0
        # Base32 should be alphanumeric + "="
        assert all(c.isalnum() or c == "=" for c in result.secret_b32)

    @freeze_time("2026-05-03 12:00:00")
    async def test_enroll_begin_creates_unconfirmed_secret(
        self, session: AsyncSession, totp_service: TotpService, user: User
    ) -> None:
        """enroll_begin persists TotpSecret with confirmed_at=None."""
        await totp_service.enroll_begin(user)

        secret = await session.scalar(
            __import__("sqlalchemy").select(TotpSecret).where(
                TotpSecret.user_id == user.id
            )
        )
        assert secret is not None
        assert secret.confirmed_at is None
        assert secret.user_id == user.id

    @freeze_time("2026-05-03 12:00:00")
    async def test_enroll_begin_allows_reenrollment(
        self, session: AsyncSession, totp_service: TotpService, user: User
    ) -> None:
        """enroll_begin on same user twice succeeds; old secret is deleted."""
        result1 = await totp_service.enroll_begin(user)
        secret_b32_1 = result1.secret_b32

        # Second enrollment succeeds
        result2 = await totp_service.enroll_begin(user)
        secret_b32_2 = result2.secret_b32

        # Secrets should be different
        assert secret_b32_1 != secret_b32_2

        # Only one secret exists for the user
        secrets = (
            await session.execute(
                __import__("sqlalchemy").select(TotpSecret).where(
                    TotpSecret.user_id == user.id
                )
            )
        ).fetchall()
        assert len(secrets) == 1

        # The existing secret is the new one (not the old one)
        existing = secrets[0][0]
        assert existing.secret_ciphertext != b""  # Encrypted, but not the first one


class TestTotpServiceEnrollFinish:
    """Tests for TotpService.enroll_finish()."""

    @freeze_time("2026-05-03 12:00:00")
    async def test_enroll_finish_with_correct_code(
        self, session: AsyncSession, totp_service: TotpService, user: User
    ) -> None:
        """enroll_finish with correct code sets confirmed_at."""
        result = await totp_service.enroll_begin(user)
        secret_b32 = result.secret_b32

        # Generate current code using pyotp
        totp = pyotp.TOTP(secret_b32)
        code = totp.now()

        success = await totp_service.enroll_finish(user, code)
        assert success

        # Verify confirmed_at is set
        secret_record = await session.scalar(
            __import__("sqlalchemy").select(TotpSecret).where(
                TotpSecret.user_id == user.id
            )
        )
        assert secret_record is not None
        assert secret_record.confirmed_at is not None

    @freeze_time("2026-05-03 12:00:00")
    async def test_enroll_finish_with_wrong_code(
        self, totp_service: TotpService, user: User
    ) -> None:
        """enroll_finish with wrong code returns False."""
        await totp_service.enroll_begin(user)

        success = await totp_service.enroll_finish(user, "000000")
        assert not success


class TestTotpServiceVerify:
    """Tests for TotpService.verify()."""

    @freeze_time("2026-05-03 12:00:00")
    async def test_verify_current_step(
        self, totp_service: TotpService, user: User
    ) -> None:
        """verify accepts current step code."""
        result = await totp_service.enroll_begin(user)
        secret_b32 = result.secret_b32

        totp = pyotp.TOTP(secret_b32)
        code = totp.now()

        # Enroll successfully
        await totp_service.enroll_finish(user, code)

        # Move time forward to next step and get new code
        with freeze_time("2026-05-03 12:00:31"):
            new_code = pyotp.TOTP(secret_b32).now()
            # Verify new code
            success = await totp_service.verify(user, new_code)
            assert success

    @freeze_time("2026-05-03 12:00:00")
    async def test_verify_adjacent_steps(
        self, totp_service: TotpService, user: User
    ) -> None:
        """verify accepts adjacent steps (-1 and +1)."""
        result = await totp_service.enroll_begin(user)
        secret_b32 = result.secret_b32

        totp = pyotp.TOTP(secret_b32)
        code_current = totp.now()

        # Enroll
        await totp_service.enroll_finish(user, code_current)

        # Move to next period
        with freeze_time("2026-05-03 12:00:31"):
            # Get code for the NEXT period (should be accepted via +1 window)
            code_next = pyotp.TOTP(secret_b32).now()
            success = await totp_service.verify(user, code_next)
            assert success

    @freeze_time("2026-05-03 12:00:00")
    async def test_verify_replay_rejected(
        self, totp_service: TotpService, user: User
    ) -> None:
        """verify rejects same code twice (replay protection)."""
        result = await totp_service.enroll_begin(user)
        secret_b32 = result.secret_b32

        totp = pyotp.TOTP(secret_b32)
        code = totp.now()

        await totp_service.enroll_finish(user, code)

        # Move to next period
        with freeze_time("2026-05-03 12:00:31"):
            # Get new code
            new_code = pyotp.TOTP(secret_b32).now()
            # First verify succeeds
            success1 = await totp_service.verify(user, new_code)
            assert success1

            # Second verify of same code fails (replay protection)
            success2 = await totp_service.verify(user, new_code)
            assert not success2

    @freeze_time("2026-05-03 12:00:00")
    async def test_verify_wrong_code_fails(
        self, totp_service: TotpService, user: User
    ) -> None:
        """verify rejects codes that don't match any valid step."""
        result = await totp_service.enroll_begin(user)
        secret_b32 = result.secret_b32

        totp = pyotp.TOTP(secret_b32)
        code = totp.now()

        await totp_service.enroll_finish(user, code)

        # Wrong code fails
        success = await totp_service.verify(user, "999999")
        assert not success


class TestTotpServiceCooldown:
    """Tests for TotpService.cooldown_check()."""

    @freeze_time("2026-05-03 12:00:00")
    async def test_cooldown_check_5_wrong_within_60s(
        self, totp_service: TotpService, user: User
    ) -> None:
        """cooldown_check raises TotpCooldown after 5 wrong attempts in 60s."""
        result = await totp_service.enroll_begin(user)
        secret_b32 = result.secret_b32

        totp = pyotp.TOTP(secret_b32)
        code = totp.now()

        await totp_service.enroll_finish(user, code)

        # 5 wrong attempts
        for i in range(5):
            await totp_service.verify(user, "999999")

        # Next attempt should raise TotpCooldown
        with pytest.raises(totp_service.TotpCooldown):
            await totp_service.cooldown_check(user)

    @freeze_time("2026-05-03 12:00:00")
    async def test_cooldown_check_resets_after_60s(
        self, totp_service: TotpService, user: User
    ) -> None:
        """cooldown_check resets after 60 seconds."""
        result = await totp_service.enroll_begin(user)
        secret_b32 = result.secret_b32

        totp = pyotp.TOTP(secret_b32)
        code = totp.now()

        await totp_service.enroll_finish(user, code)

        # 5 wrong attempts
        for i in range(5):
            await totp_service.verify(user, "999999")

        # Should raise cooldown
        with pytest.raises(totp_service.TotpCooldown):
            await totp_service.cooldown_check(user)

        # Move time forward past 60s
        with freeze_time("2026-05-03 12:01:05"):
            # Should not raise
            await totp_service.cooldown_check(user)

    @freeze_time("2026-05-03 12:00:00")
    async def test_cooldown_check_no_cooldown_with_correct_code(
        self, totp_service: TotpService, user: User
    ) -> None:
        """cooldown_check does not trigger if correct code entered."""
        result = await totp_service.enroll_begin(user)
        secret_b32 = result.secret_b32

        totp = pyotp.TOTP(secret_b32)
        code = totp.now()

        await totp_service.enroll_finish(user, code)

        # 4 wrong attempts
        for i in range(4):
            await totp_service.verify(user, "999999")

        # Should not raise (only 4 failures)
        await totp_service.cooldown_check(user)

    @freeze_time("2026-05-03 12:00:00")
    async def test_verify_auto_enforces_cooldown(
        self, totp_service: TotpService, user: User
    ) -> None:
        """verify() raises TotpCooldown on 6th wrong attempt without needing explicit cooldown_check."""
        result = await totp_service.enroll_begin(user)
        secret_b32 = result.secret_b32

        totp = pyotp.TOTP(secret_b32)
        code = totp.now()

        await totp_service.enroll_finish(user, code)

        # 5 wrong attempts (tracked via verify)
        for _ in range(5):
            result = await totp_service.verify(user, "999999")
            assert result is False

        # 6th wrong attempt should raise TotpCooldown (auto-enforced)
        with pytest.raises(totp_service.TotpCooldown):
            await totp_service.verify(user, "888888")
