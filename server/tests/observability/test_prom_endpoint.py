"""Tests for the Prometheus scrape endpoint at GET /v1/metrics.

@brief Validates authentication gating, response format, and metric
       content for the admin-only Prometheus exposition endpoint.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from server.app.api.app import create_app
from server.app.observability import metrics as metrics_mod
from server.app.observability.prom_endpoint import router as prom_router
from server.app.settings.config import FleetSettings

ADMIN_TOKEN = "test-prom-admin-token"


@pytest.fixture(autouse=True)
def _set_admin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief Inject admin token into environment for all tests."""
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", ADMIN_TOKEN)


@pytest.fixture(autouse=True)
def _reset_metrics() -> Generator[None, None, None]:
    """@brief Reset the metrics registry before and after each test."""
    metrics_mod.reset_registry()
    metrics_mod.init_metrics()
    yield
    metrics_mod.reset_registry()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """@brief Authorization headers with valid admin Bearer token."""
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _make_app() -> "FastAPI":  # noqa: F821
    """@brief Build a FastAPI app with the prom_endpoint router included."""
    app = create_app()
    app.include_router(prom_router)
    return app


def _mock_settings(**overrides):
    """@brief Build a mock FleetSettings suitable for admin auth."""
    defaults = {
        "admin_token": SecretStr(ADMIN_TOKEN),
        "metrics_enabled": True,
    }
    defaults.update(overrides)
    return FleetSettings(**defaults)


class TestPromEndpointAuth:
    """@brief Authentication enforcement tests for /v1/metrics."""

    async def test_returns_401_without_auth(self) -> None:
        """@brief GET /v1/metrics without Authorization header returns 401."""
        app = _make_app()
        with mock.patch(
            "server.app.api.middleware.admin_auth.load_settings",
            return_value=_mock_settings(),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://t"
            ) as client:
                resp = await client.get("/v1/metrics")
                assert resp.status_code == 401

    async def test_returns_401_with_bad_token(self) -> None:
        """@brief GET /v1/metrics with wrong Bearer token returns 401."""
        app = _make_app()
        with mock.patch(
            "server.app.api.middleware.admin_auth.load_settings",
            return_value=_mock_settings(),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://t"
            ) as client:
                resp = await client.get(
                    "/v1/metrics",
                    headers={"Authorization": "Bearer wrong-token"},
                )
                assert resp.status_code == 401


class TestPromEndpointContent:
    """@brief Response content and format tests for /v1/metrics."""

    async def test_returns_prometheus_format(self, auth_headers: dict[str, str]) -> None:
        """@brief GET /v1/metrics returns text/plain with Prometheus format."""
        app = _make_app()
        with mock.patch(
            "server.app.api.middleware.admin_auth.load_settings",
            return_value=_mock_settings(),
        ), mock.patch(
            "server.app.observability.prom_endpoint.load_settings",
            return_value=_mock_settings(),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://t"
            ) as client:
                resp = await client.get("/v1/metrics", headers=auth_headers)
                assert resp.status_code == 200
                ct = resp.headers["content-type"]
                assert "text/plain" in ct
                assert "0.0.4" in ct

    async def test_response_contains_expected_metrics(
        self, auth_headers: dict[str, str]
    ) -> None:
        """@brief Response body contains key metric names from the spec."""
        app = _make_app()
        metrics_mod.fleet_session_active.set(7)
        with mock.patch(
            "server.app.api.middleware.admin_auth.load_settings",
            return_value=_mock_settings(),
        ), mock.patch(
            "server.app.observability.prom_endpoint.load_settings",
            return_value=_mock_settings(),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://t"
            ) as client:
                resp = await client.get("/v1/metrics", headers=auth_headers)
                body = resp.text
                assert "fleet_session_active" in body
                assert "fleet_hosts_total" in body
                assert "fleet_command_latency_seconds" in body

    async def test_disabled_metrics_returns_404(
        self, auth_headers: dict[str, str]
    ) -> None:
        """@brief When metrics_enabled=False, endpoint returns 404."""
        app = _make_app()
        with mock.patch(
            "server.app.api.middleware.admin_auth.load_settings",
            return_value=_mock_settings(metrics_enabled=False),
        ), mock.patch(
            "server.app.observability.prom_endpoint.load_settings",
            return_value=_mock_settings(metrics_enabled=False),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://t"
            ) as client:
                resp = await client.get("/v1/metrics", headers=auth_headers)
                assert resp.status_code == 404
