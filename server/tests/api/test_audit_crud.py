"""Tests for audit logging on CRUD mutations."""

from __future__ import annotations

from unittest import mock

import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr
from sqlalchemy import select

from server.app.api.app import create_app
from server.app.deps import current_principal
from server.app.models.audit import AuditEntry
from server.app.models.role import Role
from server.app.rbac.provider import Principal
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
async def test_audit_logged_on_role_create(sm, auth, mock_settings):
    """POST /v1/roles creates audit entry with action=role.created."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="actor-1")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/roles",
                json={
                    "name": "test-role",
                    "permissions": ["host:read"],
                },
                headers=auth,
            )
            assert r.status_code == 201

    # Check audit entry was created
    async with sm() as session:
        entries = (
            await session.execute(
                select(AuditEntry).where(AuditEntry.action == "role.created")
            )
        ).scalars().all()
        assert len(entries) > 0
        entry = entries[-1]
        assert entry.actor == "admin"  # admin_required returns "admin" as actor
        assert entry.action == "role.created"
        assert "test-role" in str(entry.payload)


@pytest.mark.asyncio
async def test_audit_logged_on_role_update(sm, auth, mock_settings):
    """PATCH /v1/roles/{id} creates audit entry with action=role.updated."""
    async with sm() as session:
        role = Role(
            name="test-role-upd",
            built_in=False,
            permissions=["host:read"],
        )
        session.add(role)
        await session.commit()
        role_id = role.id

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="actor-2")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.patch(
                f"/v1/roles/{role_id}",
                json={"permissions": ["host:read", "host:write"]},
                headers=auth,
            )
            assert r.status_code == 200

    # Check audit entry was created
    async with sm() as session:
        entries = (
            await session.execute(
                select(AuditEntry).where(AuditEntry.action == "role.updated")
            )
        ).scalars().all()
        assert len(entries) > 0


@pytest.mark.asyncio
async def test_audit_logged_on_role_delete(sm, auth, mock_settings):
    """DELETE /v1/roles/{id} creates audit entry with action=role.deleted."""
    async with sm() as session:
        role = Role(
            name="test-role-del",
            built_in=False,
            permissions=["host:read"],
        )
        session.add(role)
        await session.commit()
        role_id = role.id

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="actor-3")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.delete(f"/v1/roles/{role_id}", headers=auth)
            assert r.status_code == 204

    # Check audit entry was created
    async with sm() as session:
        entries = (
            await session.execute(
                select(AuditEntry).where(AuditEntry.action == "role.deleted")
            )
        ).scalars().all()
        assert len(entries) > 0


@pytest.mark.asyncio
async def test_audit_logged_on_user_create(sm, auth, mock_settings):
    """POST /v1/users creates audit entry with action=user.created."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="actor-4")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/users",
                json={
                    "email": "test@example.com",
                    "kind": "local",
                },
                headers=auth,
            )
            assert r.status_code == 201

    # Check audit entry was created
    async with sm() as session:
        entries = (
            await session.execute(
                select(AuditEntry).where(AuditEntry.action == "user.created")
            )
        ).scalars().all()
        assert len(entries) > 0


@pytest.mark.asyncio
async def test_audit_logged_on_group_create(sm, auth, mock_settings):
    """POST /v1/groups creates audit entry with action=group.created."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="actor-5")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/groups",
                json={"name": "test-group"},
                headers=auth,
            )
            assert r.status_code == 201

    # Check audit entry was created
    async with sm() as session:
        entries = (
            await session.execute(
                select(AuditEntry).where(AuditEntry.action == "group.created")
            )
        ).scalars().all()
        assert len(entries) > 0


@pytest.mark.asyncio
async def test_audit_logged_on_binding_create(sm, auth, mock_settings):
    """POST /v1/bindings creates audit entry with action=binding.created."""
    async with sm() as session:
        role = Role(name="test-role", built_in=False, permissions=[])
        session.add(role)
        await session.commit()
        role_id = role.id

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="actor-6")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/bindings",
                json={
                    "principal_type": "user",
                    "principal_id": "user-1",
                    "role_id": role_id,
                    "scope_kind": "global",
                    "scope_value": {},
                },
                headers=auth,
            )
            assert r.status_code == 201

    # Check audit entry was created
    async with sm() as session:
        entries = (
            await session.execute(
                select(AuditEntry).where(AuditEntry.action == "binding.created")
            )
        ).scalars().all()
        assert len(entries) > 0
