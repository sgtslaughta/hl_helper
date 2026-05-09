"""Tests for GET /v1/hosts/{id}/cert endpoint."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest import mock

from server.app.api.app import create_app
from server.app.models.base import Base
from server.app.models.host import Host
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture
async def api_client(tmp_path: Path):  # type: ignore[no-untyped-def]
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


@pytest.fixture
async def session_factory(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Create a sessionmaker for populating test data."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_get_host_cert_returns_cert_state(api_client, session_factory):
    expires = datetime.now(timezone.utc) + timedelta(days=5)
    rotated = datetime.now(timezone.utc) - timedelta(days=2)
    async with session_factory() as s:
        s.add(
            Host(
                id="h-1",
                hostname="h1",
                agent_pubkey=b"\x00" * 32,
                cert_serial="ABCD1234",
                cert_expires_at=expires,
                cert_rotated_at=rotated,
                cert_rotation_count=3,
            )
        )
        await s.commit()

    r = await api_client.get("/v1/hosts/h-1/cert", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["serial"] == "ABCD1234"
    assert body["rotation_count"] == 3
    assert "expires_at" in body
    assert body["status"] in ("healthy", "rotating", "halted", "expired")


@pytest.mark.asyncio
async def test_get_host_cert_404_unknown(api_client):
    r = await api_client.get("/v1/hosts/nope/cert", headers=HEADERS)
    assert r.status_code == 404
