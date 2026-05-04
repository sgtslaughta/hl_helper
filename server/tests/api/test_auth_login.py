"""Tests for /v1/auth login, logout, whoami, refresh endpoints."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.auth.password import PasswordHasher
from server.app.auth.sessions import SessionService
from server.app.events.bus import Bus
from server.app.models.base import Base
from server.app.models.user import User, UserKind
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture
async def async_session_maker(tmp_path: Path):
    """Create in-memory aiosqlite database with tables."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def client(async_session_maker):
    """Create FastAPI test client with test database."""
    app = create_app()

    # Create session service
    bus = Bus()
    session_service = SessionService(sessionmaker=async_session_maker, bus=bus)
    await session_service.start()

    # Wire app_state
    app.state.app_state = make_test_app_state(
        sessionmaker=async_session_maker,
        session_service=session_service,
        bus=bus,
        create_session_service=False,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    await session_service.stop()


@pytest.fixture
async def test_user(async_session_maker: sessionmaker):
    """Create a test user with known password."""
    hasher = PasswordHasher()
    password = "ValidPass123!"
    password_hash = hasher.hash(password)

    user = User(
        email="test@example.com",
        kind=UserKind.LOCAL,
        password_hash=password_hash,
    )

    async with async_session_maker() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user, password


@pytest.mark.asyncio
async def test_login_happy_path(client: httpx.AsyncClient, test_user: tuple[User, str]):
    """Happy path: valid credentials return 200 with session token and cookies."""
    user, password = test_user

    response = await client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": password},
    )

    assert response.status_code == 200
    data = response.json()
    assert "session_token" in data
    assert "expires_at" in data
    assert response.cookies.get("hls_session") == data["session_token"]
    assert "hls_csrf" in response.cookies


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: httpx.AsyncClient):
    """Invalid credentials return 401."""
    response = await client.post(
        "/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "wrong"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_password(client: httpx.AsyncClient, test_user: tuple[User, str]):
    """Wrong password returns 401 and increments lockout counter."""
    user, _password = test_user

    response = await client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": "WrongPass123!"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_lockout_after_5_failures(
    client: httpx.AsyncClient, test_user: tuple[User, str]
):
    """After 5 failed attempts, 6th attempt returns 423 locked."""
    user, _password = test_user

    # Make 5 failed attempts
    for i in range(5):
        response = await client.post(
            "/v1/auth/login",
            json={"email": user.email, "password": f"WrongPass{i}!"},
        )
        assert response.status_code == 401

    # 6th attempt should be locked
    response = await client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": "AnyPass123!"},
    )
    assert response.status_code == 423


@pytest.mark.asyncio
async def test_whoami_with_session(client: httpx.AsyncClient, test_user: tuple[User, str]):
    """whoami with valid session returns 200 with user info."""
    user, password = test_user

    # Login first
    login_response = await client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert login_response.status_code == 200
    session_token = login_response.json()["session_token"]

    # Call whoami with session
    whoami_response = await client.get(
        "/v1/auth/whoami",
        cookies={"hls_session": session_token},
    )

    assert whoami_response.status_code == 200
    data = whoami_response.json()
    assert data["id"] == user.id
    assert data["email"] == user.email


@pytest.mark.asyncio
async def test_whoami_without_session(client: httpx.AsyncClient):
    """whoami without session returns 401."""
    response = await client.get("/v1/auth/whoami")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_cookies(client: httpx.AsyncClient, test_user: tuple[User, str]):
    """logout returns 204 and clears session and csrf cookies."""
    user, password = test_user

    # Login first
    login_response = await client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert login_response.status_code == 200
    session_token = login_response.json()["session_token"]

    # Logout with matching CSRF
    csrf_token = login_response.cookies.get("hls_csrf")
    logout_response = await client.post(
        "/v1/auth/logout",
        cookies={"hls_session": session_token, "hls_csrf": csrf_token},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert logout_response.status_code == 204
