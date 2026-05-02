"""Tests for /v1/settings API endpoint."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from unittest import mock

from server.app.api.app import create_app
from server.app.models import Setting
from server.app.settings.config import FleetSettings
from pydantic import SecretStr


ADMIN_TOKEN = "test-admin-tok-xyz"


@pytest.fixture(autouse=True)
def _set_admin_env(monkeypatch):
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", ADMIN_TOKEN)
    yield


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.mark.asyncio
async def test_list_settings_unauthorized():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/settings")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_settings_returns_redacted_secrets(auth_headers, sm):
    """Seed a SECRET_FIELDS key, list, ensure value is REDACTED."""
    from server.app.settings.config import SECRET_FIELDS
    secret_key = next(iter(SECRET_FIELDS))  # any registered secret
    async with sm() as session:
        session.add(Setting(key=secret_key, value="real-secret",
                            source="env", scope="env-locked",
                            updated_at=datetime.now(timezone.utc)))
        await session.commit()

    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/settings", headers=auth_headers)
            assert r.status_code == 200
            rows = r.json()
            match = next(x for x in rows if x["key"] == secret_key)
            assert match["redacted"] is True
            assert match["value"] != "real-secret"


@pytest.mark.asyncio
async def test_patch_runtime_mutable_succeeds(auth_headers, sm):
    async with sm() as session:
        session.add(Setting(key="ui.theme", value="dark",
                            source="default", scope="runtime-mutable",
                            updated_at=datetime.now(timezone.utc)))
        await session.commit()
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.patch("/v1/settings", json={"key": "ui.theme", "value": "light"},
                              headers=auth_headers)
            assert r.status_code == 200, r.text
            assert r.json()["value"] == "light"
            assert r.json()["source"] == "runtime"


@pytest.mark.asyncio
async def test_patch_boot_only_rejected(auth_headers, sm):
    async with sm() as session:
        session.add(Setting(key="grpc.bind_address", value="0.0.0.0:443",
                            source="file", scope="boot-only",
                            updated_at=datetime.now(timezone.utc)))
        await session.commit()
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.patch("/v1/settings",
                              json={"key": "grpc.bind_address", "value": "0.0.0.0:444"},
                              headers=auth_headers)
            assert r.status_code == 403
            assert "boot_only" in r.text or "restart" in r.text


@pytest.mark.asyncio
async def test_patch_env_locked_rejected(auth_headers, sm):
    async with sm() as session:
        session.add(Setting(key="db.url", value="postgres://...",
                            source="env", scope="env-locked",
                            updated_at=datetime.now(timezone.utc)))
        await session.commit()
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.patch("/v1/settings",
                              json={"key": "db.url", "value": "x"},
                              headers=auth_headers)
            assert r.status_code == 403
            assert "env_locked" in r.text or "FLEET_" in r.text


@pytest.mark.asyncio
async def test_patch_unknown_key_404(auth_headers, sm):
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.patch("/v1/settings",
                              json={"key": "nope.unknown", "value": "x"},
                              headers=auth_headers)
            assert r.status_code == 404
