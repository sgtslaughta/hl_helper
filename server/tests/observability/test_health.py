"""Tests for the GET /v1/observability/health endpoint.

@brief Verifies authentication, response shape, and component-level health
       status transitions (healthy / degraded / unhealthy).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.api.app import create_app
from server.app.observability.health import router as health_router
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state

ADMIN_TOKEN = "test-admin-tok"


def _auth_headers() -> dict[str, str]:
    """Return Authorization header with a valid admin Bearer token."""
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _patch_admin_auth() -> mock._patch[mock.MagicMock]:
    """Return a context-manager patch for ``admin_required`` settings loader."""
    return mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    )


def _build_app(sm: async_sessionmaker, **state_kw):  # type: ignore[no-untyped-def]
    """@brief Create a test FastAPI app with the health router included.

    @param sm  async_sessionmaker for database access
    @param state_kw  Extra keyword arguments forwarded to ``make_test_app_state``
    @return  FastAPI app instance ready for ``AsyncClient``
    """
    app = create_app()
    app.include_router(health_router)
    app.state.app_state = make_test_app_state(sessionmaker=sm, **state_kw)
    return app


# ----------------------------------------------------------------------- #
# Auth
# ----------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_health_returns_401_without_auth(sm: async_sessionmaker) -> None:
    """@brief Requests without a valid Bearer token receive 401."""
    with _patch_admin_auth():
        app = _build_app(sm)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/v1/observability/health")
    assert r.status_code == 401


# ----------------------------------------------------------------------- #
# Healthy path
# ----------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_health_healthy_path(sm: async_sessionmaker) -> None:
    """@brief All configured components ok -> overall status 'healthy'."""
    with _patch_admin_auth():
        app = _build_app(sm)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/v1/observability/health", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert isinstance(body["components"], list)
    db_comp = next(c for c in body["components"] if c["name"] == "db")
    assert db_comp["status"] == "ok"
    assert db_comp["latency_ms"] is not None


# ----------------------------------------------------------------------- #
# Degraded path — DB failure
# ----------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_health_degraded_when_db_fails(sm: async_sessionmaker) -> None:
    """@brief A failing DB query should degrade the DB component and overall status."""
    with _patch_admin_auth():
        app = _build_app(sm)

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db gone"))
        session_ctx.__aexit__ = AsyncMock(return_value=False)
        failing_sm = MagicMock(return_value=session_ctx)

        app.state.app_state.sessionmaker = failing_sm

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/v1/observability/health", headers=_auth_headers())

    body = r.json()
    db_comp = next(c for c in body["components"] if c["name"] == "db")
    assert db_comp["status"] == "degraded"
    assert "db gone" in (db_comp.get("message") or "")
    assert body["status"] in ("degraded", "unhealthy")


# ----------------------------------------------------------------------- #
# Vault — sealed
# ----------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_health_vault_sealed(sm: async_sessionmaker) -> None:
    """@brief Vault reporting sealed -> component 'degraded', overall 'degraded'."""
    vault_mock = AsyncMock()
    vault_mock.health_check = AsyncMock(return_value={"sealed": True})

    broker = SimpleNamespace(backends={"vault": vault_mock})

    with _patch_admin_auth():
        app = _build_app(sm, secrets_broker=broker)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/v1/observability/health", headers=_auth_headers())

    body = r.json()
    vault_comp = next(c for c in body["components"] if c["name"] == "vault")
    assert vault_comp["status"] == "degraded"
    assert body["status"] == "degraded"


# ----------------------------------------------------------------------- #
# Vault — unreachable
# ----------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_health_vault_unreachable(sm: async_sessionmaker) -> None:
    """@brief Vault health_check raising -> component 'unreachable', overall 'unhealthy'."""
    vault_mock = AsyncMock()
    vault_mock.health_check = AsyncMock(side_effect=ConnectionError("refused"))

    broker = SimpleNamespace(backends={"vault": vault_mock})

    with _patch_admin_auth():
        app = _build_app(sm, secrets_broker=broker)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/v1/observability/health", headers=_auth_headers())

    body = r.json()
    vault_comp = next(c for c in body["components"] if c["name"] == "vault")
    assert vault_comp["status"] == "unreachable"
    assert body["status"] == "unhealthy"


# ----------------------------------------------------------------------- #
# Response shape — expected component names
# ----------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_health_response_shape(sm: async_sessionmaker) -> None:
    """@brief Response must contain all expected component names."""
    with _patch_admin_auth():
        app = _build_app(sm)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/v1/observability/health", headers=_auth_headers())

    body = r.json()
    names = {c["name"] for c in body["components"]}
    assert names == {"db", "meilisearch", "vault", "plugin_runtime", "egress_proxy"}

    for comp in body["components"]:
        assert "status" in comp
        assert comp["status"] in ("ok", "degraded", "unreachable", "not_configured")
