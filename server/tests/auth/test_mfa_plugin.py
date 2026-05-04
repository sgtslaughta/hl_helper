"""Tests for the MFA plugin slot — registry + /v1/mfa/challenge integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.auth.mfa.plugin import MfaPluginRegistry, _registry
from server.app.auth.password import PasswordHasher
from server.app.auth.sessions import SessionService
from server.app.events.bus import Bus
from server.app.models.base import Base
from server.app.models.user import User, UserKind
from server.tests._helpers.app_state import make_test_app_state


# --------------------------------------------------------------------------- #
# Stub plugins
# --------------------------------------------------------------------------- #


class _DummyOk:
    """Plugin that always returns True on verify."""

    name = "dummy"

    async def begin(self, user: Any, ctx: dict[str, Any]) -> dict[str, Any]:
        return {"challenge": "x"}

    async def verify(self, user: Any, proof: dict[str, Any]) -> bool:
        return True

    async def list_methods(self) -> list[str]:
        return [self.name]


class _DummyFail:
    """Plugin that always returns False on verify."""

    name = "fail"

    async def begin(self, user: Any, ctx: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def verify(self, user: Any, proof: dict[str, Any]) -> bool:
        return False

    async def list_methods(self) -> list[str]:
        return [self.name]


class _DummyRaises:
    """Plugin that raises on verify."""

    name = "boom"

    async def begin(self, user: Any, ctx: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def verify(self, user: Any, proof: dict[str, Any]) -> bool:
        raise RuntimeError("plugin crashed")

    async def list_methods(self) -> list[str]:
        return [self.name]


# --------------------------------------------------------------------------- #
# Registry unit tests
# --------------------------------------------------------------------------- #


def test_registry_register_and_get():
    reg = MfaPluginRegistry()
    p = _DummyOk()
    reg.register(p)
    assert reg.get("dummy") is p
    assert reg.get("missing") is None


def test_registry_methods_aggregates_names():
    reg = MfaPluginRegistry()
    reg.register(_DummyOk())
    reg.register(_DummyFail())
    methods = reg.methods()
    assert "dummy" in methods
    assert "fail" in methods


@pytest.mark.asyncio
async def test_registry_get_routes_to_verify():
    reg = MfaPluginRegistry()
    reg.register(_DummyOk())
    p = reg.get("dummy")
    assert p is not None
    assert await p.verify(object(), {"x": 1}) is True


# --------------------------------------------------------------------------- #
# /v1/mfa/challenge integration tests
# --------------------------------------------------------------------------- #


@pytest.fixture
async def async_session_maker(tmp_path: Path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def client(async_session_maker, tmp_path: Path):
    app = create_app()
    bus = Bus()
    session_service = SessionService(sessionmaker=async_session_maker, bus=bus)
    await session_service.start()

    app.state.app_state = make_test_app_state(
        sessionmaker=async_session_maker,
        session_service=session_service,
        bus=bus,
        create_session_service=False,
        tmp_path=tmp_path,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c

    await session_service.stop()


@pytest.fixture(autouse=True)
def _reset_global_registry():
    """Ensure the module-level registry is clean per test."""
    _registry._plugins.clear()  # type: ignore[attr-defined]
    yield
    _registry._plugins.clear()  # type: ignore[attr-defined]


@pytest.fixture
async def test_user(async_session_maker):
    hasher = PasswordHasher()
    password = "ValidPass123!"
    user = User(
        email="plugin@example.com",
        kind=UserKind.LOCAL,
        password_hash=hasher.hash(password),
    )
    async with async_session_maker() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, password


async def _login(client: httpx.AsyncClient, user: User, password: str) -> tuple[str, str]:
    resp = await client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    csrf = resp.cookies.get("hls_csrf")
    return body["session_token"], csrf


@pytest.mark.asyncio
async def test_challenge_unknown_method_returns_401(
    client: httpx.AsyncClient, test_user
):
    """Unknown method returns 401 (same as failed verification) to prevent enumeration."""
    user, password = test_user
    token, csrf = await _login(client, user, password)

    resp = await client.post(
        "/v1/mfa/challenge",
        json={"method": "doesnotexist", "proof": {"x": 1}},
        cookies={"hls_session": token, "hls_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_challenge_dummy_plugin_succeeds(client: httpx.AsyncClient, test_user):
    user, password = test_user
    token, csrf = await _login(client, user, password)

    _registry.register(_DummyOk())
    assert "dummy" in _registry.methods()

    resp = await client.post(
        "/v1/mfa/challenge",
        json={"method": "dummy", "proof": {"any": "value"}},
        cookies={"hls_session": token, "hls_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["verified"] is True


@pytest.mark.asyncio
async def test_challenge_failing_plugin_returns_401(
    client: httpx.AsyncClient, test_user
):
    user, password = test_user
    token, csrf = await _login(client, user, password)

    _registry.register(_DummyFail())

    resp = await client.post(
        "/v1/mfa/challenge",
        json={"method": "fail", "proof": {"any": "value"}},
        cookies={"hls_session": token, "hls_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_challenge_plugin_exception_returns_502(
    client: httpx.AsyncClient, test_user
):
    """T1: plugin.verify() raises -> 502 with structured audit."""
    user, password = test_user
    token, csrf = await _login(client, user, password)
    _registry.register(_DummyRaises())

    resp = await client.post(
        "/v1/mfa/challenge",
        json={"method": "boom", "proof": {"x": 1}},
        cookies={"hls_session": token, "hls_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "mfa_plugin_error"


@pytest.mark.asyncio
async def test_challenge_unauthenticated_returns_401(client: httpx.AsyncClient):
    """T2: Unauthenticated challenge -> 401."""
    resp = await client.post(
        "/v1/mfa/challenge",
        json={"method": "totp", "proof": "123456"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_challenge_plugin_updates_last_mfa_at(
    client: httpx.AsyncClient, test_user, async_session_maker
):
    """T3: last_mfa_at persisted after successful plugin challenge."""
    user, password = test_user
    token, csrf = await _login(client, user, password)
    _registry.register(_DummyOk())

    resp = await client.post(
        "/v1/mfa/challenge",
        json={"method": "dummy", "proof": {"any": "value"}},
        cookies={"hls_session": token, "hls_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200

    from sqlalchemy import select as sa_select
    from server.app.models import User as UserModel

    async with async_session_maker() as session:
        u = await session.scalar(sa_select(UserModel).where(UserModel.id == user.id))
        assert u is not None
        assert u.last_mfa_at is not None


@pytest.mark.asyncio
async def test_challenge_plugin_non_dict_proof_rejected(
    client: httpx.AsyncClient, test_user
):
    """T10: Plugin proof must be dict — non-dict rejected with 400."""
    user, password = test_user
    token, csrf = await _login(client, user, password)
    _registry.register(_DummyOk())

    resp = await client.post(
        "/v1/mfa/challenge",
        json={"method": "dummy", "proof": "string_not_dict"},
        cookies={"hls_session": token, "hls_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "proof_must_be_object"


@pytest.mark.asyncio
async def test_challenge_unknown_method_returns_401_not_400(
    client: httpx.AsyncClient, test_user
):
    """Unknown method returns same status as verification failure to prevent enumeration."""
    user, password = test_user
    token, csrf = await _login(client, user, password)

    resp = await client.post(
        "/v1/mfa/challenge",
        json={"method": "doesnotexist", "proof": {"x": 1}},
        cookies={"hls_session": token, "hls_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "mfa_verification_failed"
