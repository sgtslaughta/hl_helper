"""Tests for /v1/hosts/{host_id}/actions API endpoints."""

from __future__ import annotations

from unittest import mock

import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr

from server.app.api.app import create_app
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    """Set admin token in environment."""
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", "test-tok")


@pytest.fixture
def auth():
    """Return admin auth headers."""
    return {"Authorization": "Bearer test-tok"}


@pytest.fixture
def mock_settings():
    """Return mocked settings with admin token."""
    return FleetSettings(admin_token=SecretStr("test-tok"))


@pytest.mark.asyncio
async def test_reboot_endpoint_dispatches_and_returns_task_id(auth, sm, mock_settings):
    """POST /actions/reboot with valid host returns 200 with task_id."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        # Create a mock dispatcher
        mock_dispatcher = mock.AsyncMock()
        mock_dispatcher.dispatch.return_value = mock.Mock(
            task_id="task-123",
            dispatched=["host-1"],
            denied=[],
            pending_approval_ids=[],
        )
        app.state.app_state = mock.Mock(
            api_dispatcher=mock_dispatcher,
            sessionmaker=sm,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r = await c.post(
                "/v1/hosts/host-1/actions/reboot",
                json={"delay_s": 0, "reason": ""},
                headers=headers,
            )
            assert r.status_code == 200
            d = r.json()
            assert d["task_id"] == "task-123"
            assert d["dispatched"] == ["host-1"]
            assert d["denied"] == []
            assert d["pending_approval_ids"] == []


@pytest.mark.asyncio
async def test_shell_exec_endpoint_creates_pending_approval(auth, sm, mock_settings):
    """Shell exec dispatch returns pending_approval_ids when approval needed."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        # Create a mock dispatcher that returns pending approval
        mock_dispatcher = mock.AsyncMock()
        mock_dispatcher.dispatch.return_value = mock.Mock(
            task_id="",
            dispatched=[],
            denied=[],
            pending_approval_ids=["approval-1"],
        )
        app.state.app_state = mock.Mock(
            api_dispatcher=mock_dispatcher,
            sessionmaker=sm,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r = await c.post(
                "/v1/hosts/host-1/actions/shell-exec",
                json={"command": "echo test", "timeout_s": 60},
                headers=headers,
            )
            assert r.status_code == 200
            d = r.json()
            assert d["pending_approval_ids"] == ["approval-1"]
            assert d["dispatched"] == []


@pytest.mark.asyncio
async def test_action_missing_acting_principal_400(auth, sm, mock_settings):
    """POST /actions without X-Acting-Principal header returns 400."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        mock_dispatcher = mock.AsyncMock()
        app.state.app_state = mock.Mock(
            api_dispatcher=mock_dispatcher,
            sessionmaker=sm,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/hosts/host-1/actions/reboot",
                json={"delay_s": 0, "reason": ""},
                headers=auth,
            )
            assert r.status_code == 400
            assert "acting_principal_required" in r.json()["detail"]


@pytest.mark.asyncio
async def test_action_unknown_host_returns_dispatched_empty(auth, sm, mock_settings):
    """POST /actions with nonexistent host returns empty dispatched."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        # Dispatcher returns empty list for unknown host (resolve_targets found nothing)
        mock_dispatcher = mock.AsyncMock()
        mock_dispatcher.dispatch.return_value = mock.Mock(
            task_id="task-456",
            dispatched=[],
            denied=[],
            pending_approval_ids=[],
        )
        app.state.app_state = mock.Mock(
            api_dispatcher=mock_dispatcher,
            sessionmaker=sm,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r = await c.post(
                "/v1/hosts/nonexistent/actions/reboot",
                json={"delay_s": 0, "reason": ""},
                headers=headers,
            )
            assert r.status_code == 200
            d = r.json()
            assert d["dispatched"] == []


@pytest.mark.asyncio
async def test_idempotent_reboot_same_key_returns_same_task_id(auth, sm, mock_settings):
    """Two calls with same Idempotency-Key return same task_id."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        mock_dispatcher = mock.AsyncMock()
        mock_dispatcher.dispatch.return_value = mock.Mock(
            task_id="task-789",
            dispatched=["host-1"],
            denied=[],
            pending_approval_ids=[],
        )
        app.state.app_state = mock.Mock(
            api_dispatcher=mock_dispatcher,
            sessionmaker=sm,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {
                **auth,
                "X-Acting-Principal": "u-1",
                "Idempotency-Key": "idem-key-123",
            }
            r1 = await c.post(
                "/v1/hosts/host-1/actions/reboot",
                json={"delay_s": 0, "reason": ""},
                headers=headers,
            )
            r2 = await c.post(
                "/v1/hosts/host-1/actions/reboot",
                json={"delay_s": 0, "reason": ""},
                headers=headers,
            )
            assert r1.json()["task_id"] == r2.json()["task_id"]
            assert r1.json()["task_id"] == "task-789"


@pytest.mark.asyncio
async def test_pkg_update_endpoint(auth, sm, mock_settings):
    """POST /actions/pkg-update with classes list."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        mock_dispatcher = mock.AsyncMock()
        mock_dispatcher.dispatch.return_value = mock.Mock(
            task_id="task-pkg",
            dispatched=["host-1"],
            denied=[],
            pending_approval_ids=[],
        )
        app.state.app_state = mock.Mock(
            api_dispatcher=mock_dispatcher,
            sessionmaker=sm,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r = await c.post(
                "/v1/hosts/host-1/actions/pkg-update",
                json={"classes": ["security", "updates"]},
                headers=headers,
            )
            assert r.status_code == 200
            d = r.json()
            assert d["task_id"] == "task-pkg"
            assert d["dispatched"] == ["host-1"]
