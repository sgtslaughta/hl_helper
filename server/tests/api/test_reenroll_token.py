"""Tests for POST /v1/hosts/{id}/reenroll-token."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest import mock

from server.app.api.app import create_app
from server.app.models.base import Base
from server.app.models.enrollment_token import EnrollmentToken
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


@pytest.fixture
async def session_factory(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Create a sessionmaker for populating test data."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


HEADERS = {"Authorization": "Bearer test-admin-token"}


@pytest.mark.asyncio
async def test_mint_reenroll_token_for_host(api_client, session_factory):
    async with session_factory() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=b"\x00" * 32))
        await s.commit()

    r = await api_client.post("/v1/hosts/h-1/reenroll-token", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["token"].startswith("hlb_")
    assert "install_command" in body
    assert "h-1" in body["install_command"] or "hlb_" in body["install_command"]

    async with session_factory() as s:
        tok = (
            await s.execute(
                select(EnrollmentToken).where(
                    EnrollmentToken.bind_host_id == "h-1"
                )
            )
        ).scalar_one()
        assert tok.purpose == "reenroll"
        assert tok.bind_host_id == "h-1"
