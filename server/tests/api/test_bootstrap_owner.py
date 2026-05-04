"""Tests for /v1/bootstrap/owner endpoint."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.auth.sessions import SessionService
from server.app.events.bus import Bus
from server.app.models.base import Base
from server.app.models.bootstrap_token import BootstrapToken
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
async def valid_bootstrap_token(async_session_maker: sessionmaker) -> str:
    """Create a valid unconsumed bootstrap token and return the raw token."""
    raw_token = f"hls_{uuid4().hex[:32]}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()

    bootstrap_token = BootstrapToken(
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    async with async_session_maker() as session:
        session.add(bootstrap_token)
        await session.commit()

    return raw_token


@pytest.mark.asyncio
async def test_bootstrap_owner_valid_flow(client: httpx.AsyncClient, valid_bootstrap_token: str):
    """Valid flow: creates owner user, marks token consumed, returns session."""
    response = await client.post(
        "/v1/bootstrap/owner",
        json={
            "token": valid_bootstrap_token,
            "email": "admin@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "session_token" in data
    assert "expires_at" in data
    assert response.cookies.get("hls_session") == data["session_token"]
    assert "hls_csrf" in response.cookies


@pytest.mark.asyncio
async def test_bootstrap_owner_replay_token(
    client: httpx.AsyncClient, valid_bootstrap_token: str
):
    """Second call with same token returns 410."""
    # First call succeeds
    response1 = await client.post(
        "/v1/bootstrap/owner",
        json={
            "token": valid_bootstrap_token,
            "email": "admin@example.com",
            "password": "SecurePass123!",
        },
    )
    assert response1.status_code == 200

    # Second call with same token returns 410
    response2 = await client.post(
        "/v1/bootstrap/owner",
        json={
            "token": valid_bootstrap_token,
            "email": "admin2@example.com",
            "password": "SecurePass123!",
        },
    )
    assert response2.status_code == 410


@pytest.mark.asyncio
async def test_bootstrap_owner_expired_token(async_session_maker: sessionmaker, client: httpx.AsyncClient):
    """Expired token returns 410."""
    raw_token = f"hls_{uuid4().hex[:32]}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()

    expired_token = BootstrapToken(
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    async with async_session_maker() as session:
        session.add(expired_token)
        await session.commit()

    response = await client.post(
        "/v1/bootstrap/owner",
        json={
            "token": raw_token,
            "email": "admin@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 410


@pytest.mark.asyncio
async def test_bootstrap_owner_weak_password(client: httpx.AsyncClient, valid_bootstrap_token: str):
    """Weak password returns 400."""
    response = await client.post(
        "/v1/bootstrap/owner",
        json={
            "token": valid_bootstrap_token,
            "email": "admin@example.com",
            "password": "weak",
        },
    )

    assert response.status_code == 400
    assert "too_short" in response.json()["detail"] or "low_complexity" in response.json()["detail"]


@pytest.mark.asyncio
async def test_bootstrap_owner_already_consumed_token(
    async_session_maker: sessionmaker, client: httpx.AsyncClient
):
    """Already consumed token returns 410."""
    raw_token = f"hls_{uuid4().hex[:32]}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()

    consumed_token = BootstrapToken(
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        consumed_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    async with async_session_maker() as session:
        session.add(consumed_token)
        await session.commit()

    response = await client.post(
        "/v1/bootstrap/owner",
        json={
            "token": raw_token,
            "email": "admin@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 410


@pytest.mark.asyncio
async def test_bootstrap_password_is_email_rejected(
    client: httpx.AsyncClient, valid_bootstrap_token: str
):
    """Password matching email is rejected (validate_password user_context catches it)."""
    response = await client.post(
        "/v1/bootstrap/owner",
        json={
            "token": valid_bootstrap_token,
            "email": "admin@example.com",
            "password": "admin@example.com",
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "contains_user_info" in detail.lower()
