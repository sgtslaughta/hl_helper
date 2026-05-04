"""Tests for token transport extraction and CSRF validation."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.auth.sessions import SessionService
from server.app.events.bus import Bus
from server.app.models.base import Base
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


@pytest.mark.asyncio
async def test_bearer_skips_csrf(client: httpx.AsyncClient):
    """Bearer token path should not require CSRF token."""
    # Test with POST (state-changing)
    response = await client.post(
        "/v1/auth/login",
        json={"username": "user", "password": "pass"},
        headers={"Authorization": "Bearer hls_invalid"},
    )
    # Should not fail with 403 CSRF mismatch; will fail with auth (401) instead
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_cookie_post_without_csrf(client: httpx.AsyncClient):
    """Cookie-based POST without CSRF token should return 403."""
    response = await client.post(
        "/v1/auth/logout",
        cookies={"hls_session": "hls_invalid"},
    )
    # Should fail with 403 CSRF mismatch
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cookie_post_with_mismatching_csrf(client: httpx.AsyncClient):
    """Cookie-based POST with mismatched CSRF token should return 403."""
    response = await client.post(
        "/v1/auth/logout",
        cookies={"hls_session": "hls_invalid", "hls_csrf": "csrf_token"},
        headers={"X-CSRF-Token": "different_csrf"},
    )
    # Should fail with 403 CSRF mismatch
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cookie_post_with_matching_csrf(client: httpx.AsyncClient):
    """Cookie-based POST with matching CSRF token should pass CSRF check."""
    # This test verifies CSRF check passes; auth will still fail due to invalid session
    csrf_token = "matching_csrf_token"
    response = await client.post(
        "/v1/auth/logout",
        cookies={"hls_session": "hls_invalid", "hls_csrf": csrf_token},
        headers={"X-CSRF-Token": csrf_token},
    )
    # Should not fail with 403 CSRF mismatch; will fail with auth (401) instead
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_cookie_get_without_csrf(client: httpx.AsyncClient):
    """Cookie-based GET should not require CSRF token."""
    response = await client.get(
        "/v1/auth/whoami",
        cookies={"hls_session": "hls_invalid"},
    )
    # Should not fail with 403 CSRF mismatch; will fail with auth (401) instead
    assert response.status_code != 403
