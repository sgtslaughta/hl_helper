"""Tests for /v1/update-policies and /v1/maintenance-windows API endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator
from unittest import mock

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.models.base import Base
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state
from pydantic import SecretStr


@pytest.fixture
async def async_session_maker(tmp_path: Path):
    """Create in-memory aiosqlite database with tables."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False},
        echo_pool=False,
    )
    async with engine.begin() as conn:
        # Enable foreign key constraints for SQLite
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def client(async_session_maker):
    """Create FastAPI test client with test database."""
    app = create_app()

    async def override_session_dep() -> AsyncIterator[AsyncSession]:
        async with async_session_maker() as session:
            yield session

    app.state.app_state = make_test_app_state(sessionmaker=async_session_maker)

    mock_settings = FleetSettings(admin_token=SecretStr("test-admin-token"))

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client


# UpdatePolicy Tests


@pytest.mark.asyncio
async def test_update_policy_crud(client: httpx.AsyncClient):
    """UpdatePolicy: POST → 201 → GET → 200 → PATCH → 200 → DELETE → 204 → GET → 404."""
    # POST create
    create_response = await client.post(
        "/v1/update-policies",
        json={
            "name": "test-policy",
            "description": "A test policy",
            "target_selector": {"env": "prod"},
            "auto_apply_classes": ["security", "bugfix"],
            "reboot_policy": "if_required",
            "breaking_change_policy": "approve",
            "approval_required": True,
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    policy_id = created["id"]
    assert created["name"] == "test-policy"
    assert created["description"] == "A test policy"
    assert created["approval_required"] is True

    # GET single
    get_response = await client.get(
        f"/v1/update-policies/{policy_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert get_response.status_code == 200
    fetched = get_response.json()
    assert fetched["id"] == policy_id
    assert fetched["name"] == "test-policy"

    # PATCH update
    patch_response = await client.patch(
        f"/v1/update-policies/{policy_id}",
        json={
            "description": "Updated description",
            "approval_required": False,
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["description"] == "Updated description"
    assert patched["approval_required"] is False

    # DELETE
    delete_response = await client.delete(
        f"/v1/update-policies/{policy_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert delete_response.status_code == 204

    # GET after delete → 404
    get_after_delete = await client.get(
        f"/v1/update-policies/{policy_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert get_after_delete.status_code == 404


@pytest.mark.asyncio
async def test_update_policy_list(client: httpx.AsyncClient):
    """GET /v1/update-policies without auth → 401."""
    response = await client.get("/v1/update-policies")
    assert response.status_code == 401

    # With auth
    create_response = await client.post(
        "/v1/update-policies",
        json={
            "name": "policy-1",
            "target_selector": {"env": "dev"},
            "auto_apply_classes": ["security"],
            "reboot_policy": "never",
            "breaking_change_policy": "block",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert create_response.status_code == 201

    list_response = await client.get(
        "/v1/update-policies",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert list_response.status_code == 200
    items = list_response.json()
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["name"] == "policy-1"


@pytest.mark.asyncio
async def test_update_policy_auth_required_post(client: httpx.AsyncClient):
    """POST /v1/update-policies without auth → 401."""
    response = await client.post(
        "/v1/update-policies",
        json={
            "name": "test",
            "target_selector": {},
            "auto_apply_classes": [],
            "reboot_policy": "never",
            "breaking_change_policy": "block",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_policy_get_single_requires_auth_401(client: httpx.AsyncClient):
    """GET /v1/update-policies/{policy_id} without auth → 401."""
    response = await client.get("/v1/update-policies/some-id")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_policy_patch_requires_auth_401(client: httpx.AsyncClient):
    """PATCH /v1/update-policies/{policy_id} without auth → 401."""
    response = await client.patch(
        "/v1/update-policies/some-id",
        json={"description": "updated"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_policy_delete_requires_auth_401(client: httpx.AsyncClient):
    """DELETE /v1/update-policies/{policy_id} without auth → 401."""
    response = await client.delete("/v1/update-policies/some-id")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_policy_patch_404(client: httpx.AsyncClient):
    """PATCH /v1/update-policies/{nonexistent} → 404."""
    response = await client.patch(
        "/v1/update-policies/nonexistent-id",
        json={"description": "updated"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_policy_delete_404(client: httpx.AsyncClient):
    """DELETE /v1/update-policies/{nonexistent} → 404."""
    response = await client.delete(
        "/v1/update-policies/nonexistent-id",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404


# MaintenanceWindow Tests


@pytest.mark.asyncio
async def test_maintenance_window_crud(client: httpx.AsyncClient):
    """MaintenanceWindow: POST → 201 → GET → 200 → PATCH → 200 → DELETE → 204 → GET → 404."""
    # POST create
    create_response = await client.post(
        "/v1/maintenance-windows",
        json={
            "name": "test-window",
            "description": "A test window",
            "start_cron": "0 2 * * 0",
            "duration_minutes": 60,
            "timezone": "US/Eastern",
            "target_selector": {"env": "prod"},
            "kind": "allow",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    window_id = created["id"]
    assert created["name"] == "test-window"
    assert created["duration_minutes"] == 60
    assert created["kind"] == "allow"

    # GET single
    get_response = await client.get(
        f"/v1/maintenance-windows/{window_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert get_response.status_code == 200
    fetched = get_response.json()
    assert fetched["id"] == window_id
    assert fetched["name"] == "test-window"

    # PATCH update
    patch_response = await client.patch(
        f"/v1/maintenance-windows/{window_id}",
        json={
            "description": "Updated window",
            "kind": "blackout",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["description"] == "Updated window"
    assert patched["kind"] == "blackout"

    # DELETE
    delete_response = await client.delete(
        f"/v1/maintenance-windows/{window_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert delete_response.status_code == 204

    # GET after delete → 404
    get_after_delete = await client.get(
        f"/v1/maintenance-windows/{window_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert get_after_delete.status_code == 404


@pytest.mark.asyncio
async def test_maintenance_window_zero_duration_422(client: httpx.AsyncClient):
    """Pydantic validation: duration_minutes <= 0 → 422."""
    response = await client.post(
        "/v1/maintenance-windows",
        json={
            "name": "bad-window",
            "start_cron": "0 2 * * 0",
            "duration_minutes": 0,
            "target_selector": {"env": "prod"},
            "kind": "allow",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_maintenance_window_invalid_cron_422(client: httpx.AsyncClient):
    """Cron validation: 3 fields instead of 5 → 422."""
    response = await client.post(
        "/v1/maintenance-windows",
        json={
            "name": "bad-cron",
            "start_cron": "0 2 *",  # Only 3 fields
            "duration_minutes": 60,
            "target_selector": {"env": "prod"},
            "kind": "allow",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_maintenance_window_kind_validated(client: httpx.AsyncClient):
    """Kind validation: invalid kind → 422."""
    response = await client.post(
        "/v1/maintenance-windows",
        json={
            "name": "bad-kind",
            "start_cron": "0 2 * * 0",
            "duration_minutes": 60,
            "target_selector": {"env": "prod"},
            "kind": "bogus",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_maintenance_window_list(client: httpx.AsyncClient):
    """GET /v1/maintenance-windows → list (requires auth)."""
    # Create one
    create_response = await client.post(
        "/v1/maintenance-windows",
        json={
            "name": "window-1",
            "start_cron": "0 2 * * 0",
            "duration_minutes": 120,
            "target_selector": {"env": "staging"},
            "kind": "blackout",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert create_response.status_code == 201

    # List
    list_response = await client.get(
        "/v1/maintenance-windows",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert list_response.status_code == 200
    items = list_response.json()
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["name"] == "window-1"


@pytest.mark.asyncio
async def test_maintenance_window_list_requires_auth_401(client: httpx.AsyncClient):
    """GET /v1/maintenance-windows without auth → 401."""
    response = await client.get("/v1/maintenance-windows")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_maintenance_window_create_requires_auth_401(client: httpx.AsyncClient):
    """POST /v1/maintenance-windows without auth → 401."""
    response = await client.post(
        "/v1/maintenance-windows",
        json={
            "name": "window",
            "start_cron": "0 2 * * 0",
            "duration_minutes": 60,
            "target_selector": {"env": "prod"},
            "kind": "allow",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_maintenance_window_patch_404(client: httpx.AsyncClient):
    """PATCH /v1/maintenance-windows/{nonexistent} → 404."""
    response = await client.patch(
        "/v1/maintenance-windows/nonexistent-id",
        json={"description": "updated"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_maintenance_window_delete_404(client: httpx.AsyncClient):
    """DELETE /v1/maintenance-windows/{nonexistent} → 404."""
    response = await client.delete(
        "/v1/maintenance-windows/nonexistent-id",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404
