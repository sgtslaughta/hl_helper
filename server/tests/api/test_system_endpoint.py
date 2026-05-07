"""Tests for /v1/system/advertised-origins."""
from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator
from unittest import mock

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.models.base import Base
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture
async def async_session_maker(tmp_path: Path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def client(async_session_maker, tmp_path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    state = make_test_app_state(sessionmaker=async_session_maker, tmp_path=tmp_path)
    state.advertised_origins = [
        "https://localhost:8443",
        "https://10.0.0.5:8443",
    ]
    state.public_origin = "https://localhost:8443"
    app.state.app_state = state
    mock_settings = FleetSettings(admin_token=SecretStr("test-admin-token"))
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as c:
            yield c


@pytest.mark.asyncio
async def test_advertised_origins_requires_admin(client: httpx.AsyncClient):
    resp = await client.get("/v1/system/advertised-origins")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_advertised_origins_returns_list(client: httpx.AsyncClient):
    resp = await client.get(
        "/v1/system/advertised-origins",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "origins" in body
    assert "default" in body
    assert body["default"] == "https://localhost:8443"
    assert "https://10.0.0.5:8443" in body["origins"]
