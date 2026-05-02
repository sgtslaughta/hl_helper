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


@pytest.mark.asyncio
async def test_patch_emits_audit_entry(auth_headers, sm, signing_backend):
    """Verify PATCH emits audit entry with old + new values."""
    from server.app.audit.sql_chain import SqlAuditChain
    from server.app.models import AuditEntry
    from sqlalchemy import select

    async with sm() as session:
        session.add(Setting(key="ui.theme", value="dark",
                            source="default", scope="runtime-mutable",
                            updated_at=datetime.now(timezone.utc)))
        await session.commit()

    audit = SqlAuditChain(signing_backend)
    app = create_app()
    app.state.sessionmaker = sm
    app.state.audit_chain = audit

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.patch("/v1/settings", json={"key": "ui.theme", "value": "light"},
                              headers=auth_headers)
            assert r.status_code == 200

    async with sm() as session:
        rows = (await session.execute(select(AuditEntry))).scalars().all()
        write_rows = [r for r in rows if r.action == "setting.write"]
        assert write_rows, "expected setting.write audit entry"
        payload = write_rows[0].payload
        assert payload.get("old") == "dark"
        assert payload.get("new") == "light"
        assert payload.get("source") == "runtime"


@pytest.mark.asyncio
async def test_patch_response_redacts_secrets(auth_headers, sm):
    """Verify PATCH response redacts secret values."""
    from server.app.settings.config import SECRET_FIELDS
    secret_key = next(iter(SECRET_FIELDS))
    async with sm() as session:
        session.add(Setting(key=secret_key, value="old-value",
                            source="env", scope="runtime-mutable",
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
                              json={"key": secret_key, "value": "new-secret-value"},
                              headers=auth_headers)
            assert r.status_code == 200
            body = r.json()
            assert body["redacted"] is True
            assert body["value"] != "new-secret-value"
            assert body["value"] == "***REDACTED***"


@pytest.mark.asyncio
async def test_patch_audit_redacts_secrets(auth_headers, sm, signing_backend):
    """For SECRET_FIELDS, audit log must NOT contain plaintext old/new values."""
    from server.app.audit.sql_chain import SqlAuditChain
    from server.app.models import AuditEntry
    from server.app.settings.config import SECRET_FIELDS
    from sqlalchemy import select
    secret_key = next(iter(SECRET_FIELDS))
    async with sm() as session:
        session.add(Setting(key=secret_key, value="old-secret",
                            source="env", scope="runtime-mutable",
                            updated_at=datetime.now(timezone.utc)))
        await session.commit()
    audit = SqlAuditChain(signing_backend)
    app = create_app()
    app.state.sessionmaker = sm
    app.state.audit_chain = audit
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.patch("/v1/settings",
                              json={"key": secret_key, "value": "new-secret"},
                              headers=auth_headers)
            assert r.status_code == 200
    async with sm() as session:
        rows = (await session.execute(select(AuditEntry))).scalars().all()
        for row in rows:
            payload_str = str(row.payload)
            assert "old-secret" not in payload_str
            assert "new-secret" not in payload_str
