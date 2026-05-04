"""Tests for secrets API endpoints."""

from __future__ import annotations

import base64
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient

from server.app.api.app import create_app
from server.app.secrets.broker import SecretsBroker
from server.app.secrets.handle import HandleStore
from server.app.secrets.cache import BrokerCache
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture
def auth() -> dict[str, str]:
    """Return auth header for admin."""
    return {"Authorization": "Bearer test-admin-token"}


@pytest.fixture
def mock_admin_token():  # type: ignore[no-untyped-def]
    """Mock the admin token in settings."""
    with mock.patch("server.app.api.middleware.admin_auth.load_settings") as mock_load:
        from pydantic import SecretStr

        settings = mock.MagicMock()
        settings.admin_token = SecretStr("test-admin-token")
        mock_load.return_value = settings
        yield mock_load


@pytest.mark.asyncio
async def test_list_refs_requires_auth(sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """GET /v1/secrets requires admin auth."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/secrets")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_put_secret_requires_auth(sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """POST /v1/secrets requires admin auth."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    body = {
        "ref": "secret://local/foo",
        "value": base64.b64encode(b"plaintext").decode(),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/secrets", json=body)
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_rotate_secret_requires_auth(sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """POST /v1/secrets/actions/rotate requires admin auth."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    body = {"ref": "secret://local/foo"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/secrets/actions/rotate", json=body)
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_reveal_requires_mfa_proof(auth, sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """POST /v1/secrets/actions/reveal without X-MFA-Proof returns 403."""
    # Create broker with mock backend and mfa_recency_check that passes
    mock_backend = mock.AsyncMock()
    mock_backend.get = mock.AsyncMock(return_value=b"secret-value")
    backends = {"local": mock_backend}

    app = create_app()
    app_state = make_test_app_state(sessionmaker=sm)
    app_state.secrets_broker = SecretsBroker(
        backends=backends,
        cache=BrokerCache(),
        handle_store=HandleStore(),
        mfa_recency_check=lambda r: True,
    )
    app.state.app_state = app_state

    body = {"ref": "secret://local/foo"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # Without X-MFA-Proof
        r = await c.post("/v1/secrets/actions/reveal", json=body, headers=auth)
        assert r.status_code == 403
        assert "mfa_required" in r.json()["detail"]


@pytest.mark.asyncio
async def test_migrate_requires_auth(sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """POST /v1/secrets/actions/migrate requires admin auth."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    body = {
        "src_ref": "secret://local/src",
        "dst_ref": "secret://local/dst",
        "dry_run": True,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/secrets/actions/migrate", json=body)
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_no_broker_returns_503(auth, sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """When secrets_broker is None, endpoints return 503."""
    app = create_app()
    app_state = make_test_app_state(sessionmaker=sm)
    app_state.secrets_broker = None
    app.state.app_state = app_state

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/secrets", headers=auth)
        assert r.status_code == 503
        assert "secrets backend not configured" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_reveal_roundtrip(auth, sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Happy-path: put secret, then reveal with valid X-MFA-Proof."""
    # Create broker with mock backend and mfa_recency_check
    mock_backend = mock.AsyncMock()
    mock_backend.put = mock.AsyncMock(return_value=1)
    mock_backend.get = mock.AsyncMock(return_value=b"secret-value")
    backends = {"local": mock_backend}

    app = create_app()
    app_state = make_test_app_state(sessionmaker=sm)
    app_state.secrets_broker = SecretsBroker(
        backends=backends,
        cache=BrokerCache(),
        handle_store=HandleStore(),
        mfa_recency_check=lambda r: True,
    )
    app.state.app_state = app_state

    # Put secret
    put_body = {
        "ref": "secret://local/test-secret",
        "value": base64.b64encode(b"my-secret-value").decode(),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        put_response = await c.post("/v1/secrets", json=put_body, headers=auth)
        assert put_response.status_code == 201
        assert put_response.json()["version"] == 1

        # Reveal with valid X-MFA-Proof
        reveal_body = {"ref": "secret://local/test-secret"}
        reveal_response = await c.post(
            "/v1/secrets/actions/reveal",
            json=reveal_body,
            headers={
                "X-MFA-Proof": "valid-mfa-proof",
                **auth,
            },
        )
        assert reveal_response.status_code == 200
        revealed_value = reveal_response.json()["value"]
        assert base64.b64decode(revealed_value) == b"secret-value"


@pytest.mark.asyncio
async def test_put_malformed_base64(auth, sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """PUT with malformed base64 value returns 400."""
    app = create_app()
    app_state = make_test_app_state(sessionmaker=sm)
    mock_backend = mock.AsyncMock()
    app_state.secrets_broker = SecretsBroker(
        backends={"local": mock_backend},
        cache=BrokerCache(),
        handle_store=HandleStore(),
        mfa_recency_check=lambda r: True,
    )
    app.state.app_state = app_state

    put_body = {
        "ref": "secret://local/test",
        "value": "not-valid-base64!!!",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/secrets", json=put_body, headers=auth)
        assert r.status_code == 400
        assert "Invalid base64" in r.json()["detail"]
