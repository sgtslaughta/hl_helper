"""Smoke tests for the terminal API surface (C9)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest import mock

from server.app.api.app import create_app
from server.app.models.base import Base
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture
async def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Create an httpx ASGI client with admin-auth + sessionmaker patched in."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    settings = FleetSettings(admin_token=SecretStr("test-admin-token"))
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as c:
            yield c


HEADERS = {"Authorization": "Bearer test-admin-token"}


@pytest.mark.asyncio
async def test_list_sessions_requires_admin(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/terminal/sessions")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_sessions_empty(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/terminal/sessions", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_recording_404(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/terminal/recordings/missing-id", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_kill_204(client: httpx.AsyncClient) -> None:
    r = await client.delete("/v1/terminal/sessions/abc", headers=HEADERS)
    assert r.status_code == 204
