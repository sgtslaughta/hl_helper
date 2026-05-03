"""Tests for SessionService — issue, lookup, revoke, and event-based invalidation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import pytest
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.events.bus import Bus
from server.app.models import User
from server.app.models.base import Base as BaseModel
from server.app.auth.sessions import SessionService, RequestMeta, make_request_meta
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
def eventbus() -> Bus:
    """Create a fresh event bus."""
    return Bus()


@pytest.fixture
async def svc(sm: async_sessionmaker, eventbus: Bus) -> SessionService:
    """Create a SessionService and start it."""
    service = SessionService(sessionmaker=sm, bus=eventbus)
    await service.start()
    yield service
    await service.stop()


def meta(ip: str = "10.0.0.5", ua: str = "Firefox") -> RequestMeta:
    """Helper to create RequestMeta."""
    return make_request_meta(ip, ua)




class TestSessionService:
    """Tests for SessionService functionality."""

    @freeze_time("2026-05-03 12:00:00")
    async def test_issue_returns_raw_token_only_once(self, svc: SessionService, user: User):
        """issue() returns SessionIssue with raw token starting with 'hls_'."""
        out = await svc.issue(user, mfa_level="totp", request_meta=meta())
        assert out.raw.startswith("hls_")
        assert out.session_id is not None
        assert out.expires_at is not None
        assert (await svc.lookup(out.raw)).user_id == user.id

    @freeze_time("2026-05-03 12:00:00")
    async def test_idle_ttl_extends_on_use(self, svc: SessionService, user: User):
        """lookup() extends idle TTL of 30min on each use; absolute 12h cap."""
        out = await svc.issue(user, "totp", meta())
        with freeze_time("2026-05-03 12:20:00"):  # 20 min later
            assert await svc.lookup(out.raw)
        with freeze_time("2026-05-03 12:40:00"):  # 40 cumulative; >30 idle if not refreshed
            # last_used updated -> still valid
            assert await svc.lookup(out.raw)
        with freeze_time("2026-05-03 13:11:00"):  # idle without use
            assert await svc.lookup(out.raw) is None

    @freeze_time("2026-05-03 12:00:00")
    async def test_absolute_ttl_caps(self, svc: SessionService, user: User):
        """lookup() respects absolute 12h TTL even if idle TTL would allow."""
        out = await svc.issue(user, "totp", meta())
        base = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
        step = timedelta(minutes=25)
        for i in range(1, 29):  # 28 * 25min = 11h40m, refreshes idle TTL each step
            with freeze_time(base + step * i):
                res = await svc.lookup(out.raw)
                assert res is not None, f"step {i}"
        with freeze_time(base + timedelta(hours=12, minutes=5)):  # past 12h absolute
            assert await svc.lookup(out.raw) is None

    @freeze_time("2026-05-03 12:00:00")
    async def test_revoke_immediate(self, svc: SessionService, user: User):
        """revoke() immediately invalidates a session."""
        out = await svc.issue(user, "totp", meta())
        await svc.revoke(out.session_id, reason="test")
        assert await svc.lookup(out.raw) is None

    async def test_role_write_revokes_all_user_sessions(
        self, svc: SessionService, user: User, eventbus: Bus
    ) -> None:
        """Subscribing to rbac.binding_changed revokes all sessions for user_id."""
        o1 = await svc.issue(user, "totp", meta())
        o2 = await svc.issue(user, "totp", meta())
        await eventbus.publish("rbac.binding_changed", {"user_id": user.id})
        for _ in range(50):
            await asyncio.sleep(0.01)
            if (await svc.lookup(o1.raw)) is None:
                break
        assert await svc.lookup(o1.raw) is None
        assert await svc.lookup(o2.raw) is None

    async def test_subscription_survives_bad_payload(
        self, svc: SessionService, user: User, eventbus: Bus
    ) -> None:
        """Subscriber continues after receiving event with missing user_id."""
        o1 = await svc.issue(user, "totp", meta())
        # Publish event with no user_id (bad payload)
        await eventbus.publish("rbac.binding_changed", {})
        await asyncio.sleep(0.01)
        # Session still exists because user_id was missing
        assert await svc.lookup(o1.raw) is not None
        # Now publish good event
        await eventbus.publish("rbac.binding_changed", {"user_id": user.id})
        for _ in range(50):
            await asyncio.sleep(0.01)
            if (await svc.lookup(o1.raw)) is None:
                break
        # Session should be revoked
        assert await svc.lookup(o1.raw) is None

    @freeze_time("2026-05-03 12:00:00")
    async def test_ua_or_ip_class_mismatch_invalidates(self, svc: SessionService, user: User):
        """lookup() validates IP class (/24 CIDR) and UA fingerprint."""
        out = await svc.issue(user, "totp", meta(ip="10.0.0.5", ua="Firefox"))
        # /24 same CIDR should be ok (10.0.0.0/24)
        assert await svc.lookup(out.raw, meta(ip="10.0.0.99", ua="Firefox")) is not None
        # /24 different CIDR should fail
        assert await svc.lookup(out.raw, meta(ip="10.0.1.1", ua="Firefox")) is None
        # UA different should fail
        assert await svc.lookup(out.raw, meta(ip="10.0.0.5", ua="Chrome")) is None
