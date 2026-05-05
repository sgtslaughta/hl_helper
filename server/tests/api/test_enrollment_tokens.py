"""Tests for /v1/enrollment-tokens admin API."""
from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator
from unittest import mock

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.crypto.ca import InternalCA
from server.app.enrollment.service import EnrollmentService
from server.app.models.base import Base
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state

# Reuse signing backend fixture for FileBackend
from server.tests.grpc.conftest import signing_backend  # noqa: F401


@pytest.fixture
async def async_session_maker(tmp_path: Path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def ca(tmp_path: Path) -> InternalCA:
    return InternalCA.bootstrap(tmp_path / "ca")


@pytest.fixture
def enrollment_service(ca, signing_backend) -> EnrollmentService:
    return EnrollmentService(ca=ca, signing_backend=signing_backend, grpc_endpoint="grpc://test:5443")


@pytest.fixture
async def client(async_session_maker, enrollment_service) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.state.app_state = make_test_app_state(
        sessionmaker=async_session_maker,
        enrollment_service=enrollment_service,
    )
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


ADMIN_HEADERS = {"Authorization": "Bearer test-admin-token"}


@pytest.mark.asyncio
async def test_mint_requires_admin(client: httpx.AsyncClient):
    resp = await client.post(
        "/v1/enrollment-tokens",
        json={"label": "lab-router-01", "ttl_seconds": 900},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_mint_returns_plaintext_once(client: httpx.AsyncClient):
    resp = await client.post(
        "/v1/enrollment-tokens",
        headers=ADMIN_HEADERS,
        json={"label": "lab-router-01", "ttl_seconds": 900},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["plaintext_token"]
    assert len(body["plaintext_token"]) >= 20
    assert body["token_id"]
    assert body["expires_at"]
    assert "install_command" in body
    assert body["plaintext_token"] in body["install_command"]


@pytest.mark.asyncio
async def test_mint_ttl_below_min_returns_400(client: httpx.AsyncClient):
    resp = await client.post(
        "/v1/enrollment-tokens",
        headers=ADMIN_HEADERS,
        json={"label": "x", "ttl_seconds": 10},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_pending_returns_minted(client: httpx.AsyncClient):
    minted = await client.post(
        "/v1/enrollment-tokens",
        headers=ADMIN_HEADERS,
        json={"label": "host-a", "ttl_seconds": 900},
    )
    assert minted.status_code == 201
    listed = await client.get("/v1/enrollment-tokens", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    rows = listed.json()
    assert any(r["id"] == minted.json()["token_id"] for r in rows)
    found = next(r for r in rows if r["id"] == minted.json()["token_id"])
    assert "plaintext_token" not in found
    assert found["label"] == "host-a"
    assert len(found["last_4"]) == 4


@pytest.mark.asyncio
async def test_list_requires_admin(client: httpx.AsyncClient):
    resp = await client.get("/v1/enrollment-tokens")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_revoke_pending_returns_204(client: httpx.AsyncClient):
    minted = await client.post(
        "/v1/enrollment-tokens",
        headers=ADMIN_HEADERS,
        json={"label": "x", "ttl_seconds": 900},
    )
    tid = minted.json()["token_id"]
    resp = await client.delete(f"/v1/enrollment-tokens/{tid}", headers=ADMIN_HEADERS)
    assert resp.status_code == 204
    listed = (await client.get("/v1/enrollment-tokens", headers=ADMIN_HEADERS)).json()
    assert all(r["id"] != tid for r in listed)


@pytest.mark.asyncio
async def test_revoke_unknown_returns_404(client: httpx.AsyncClient):
    resp = await client.delete("/v1/enrollment-tokens/et_unknown", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_e2e_mint_then_redeem_disappears(client: httpx.AsyncClient):
    import base64
    from server.tests.enrollment.test_service import make_csr

    minted = (await client.post(
        "/v1/enrollment-tokens",
        headers=ADMIN_HEADERS,
        json={"label": "lab-router", "ttl_seconds": 900},
    )).json()
    assert "token_id" in minted

    csr_pem_bytes, agent_pubkey = make_csr()
    redeem_resp = await client.post(
        "/v1/enroll",
        json={
            "token": minted["plaintext_token"],
            "hostname": "lab-router",
            "csr_pem": csr_pem_bytes.decode("utf-8"),
            "agent_pubkey_b64": base64.b64encode(agent_pubkey).decode("ascii"),
        },
    )
    assert redeem_resp.status_code == 200, redeem_resp.text

    listed = (await client.get("/v1/enrollment-tokens", headers=ADMIN_HEADERS)).json()
    assert all(r["id"] != minted["token_id"] for r in listed)
