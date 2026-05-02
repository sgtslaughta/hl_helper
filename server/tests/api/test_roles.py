"""Tests for /v1/roles API endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from unittest import mock

from server.app.api.app import create_app
from server.app.models import Role, Binding
from server.app.models.binding import PrincipalType, ScopeKind
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
async def test_list_roles_includes_builtin_4(sm):
    """Verify GET /v1/roles returns all 4 built-in roles with built_in flag."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/roles", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
            assert r.status_code == 200, r.text
            roles = r.json()
            assert len(roles) == 4
            names = {role["name"] for role in roles}
            assert names == {"viewer", "operator", "admin", "owner"}
            for role in roles:
                assert role["built_in"] is True


@pytest.mark.asyncio
async def test_create_custom_role_201(sm):
    """Verify POST /v1/roles with valid perms returns 201."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            body = {
                "name": "custom_role",
                "description": "Custom role",
                "permissions": ["host:read", "group:read"],
            }
            r = await c.post("/v1/roles", json=body, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
            assert r.status_code == 201, r.text
            data = r.json()
            assert data["name"] == "custom_role"
            assert data["built_in"] is False
            assert data["permissions"] == ["host:read", "group:read"]


@pytest.mark.asyncio
async def test_create_role_invalid_permission_422(sm):
    """Verify POST with bogus perm returns 422 with detail."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            body = {
                "name": "bad_role",
                "permissions": ["bogus:perm", "host:read"],
            }
            r = await c.post("/v1/roles", json=body, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
            assert r.status_code == 422, r.text
            detail = r.text
            assert "bogus:perm" in detail


@pytest.mark.asyncio
async def test_update_builtin_role_403(sm):
    """Verify PATCH on built-in role returns 403."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            # Get viewer role ID
            r = await c.get("/v1/roles", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
            roles = r.json()
            viewer = next(r for r in roles if r["name"] == "viewer")
            viewer_id = viewer["id"]

            # Try to update it
            r = await c.patch(
                f"/v1/roles/{viewer_id}",
                json={"description": "Updated"},
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
            )
            assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_delete_builtin_role_403(sm):
    """Verify DELETE on built-in role returns 403."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            # Get viewer role ID
            r = await c.get("/v1/roles", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
            roles = r.json()
            viewer = next(r for r in roles if r["name"] == "viewer")
            viewer_id = viewer["id"]

            # Try to delete it
            r = await c.delete(
                f"/v1/roles/{viewer_id}",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
            )
            assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_delete_role_with_bindings_409(sm):
    """Verify DELETE role with bindings returns 409."""
    app = create_app()
    app.state.sessionmaker = sm

    # Create custom role and binding
    async with sm() as session:
        role = Role(
            id="role-with-binding",
            name="custom_with_binding",
            description="Has a binding",
            built_in=False,
            permissions=["host:read"],
        )
        session.add(role)
        await session.flush()

        binding = Binding(
            id="binding-1",
            principal_type=PrincipalType.USER,
            principal_id="user-1",
            role_id=role.id,
            scope_kind=ScopeKind.GLOBAL,
            scope_value={},
            scope_hash="hash",
        )
        session.add(binding)
        await session.commit()

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.delete(
                "/v1/roles/role-with-binding",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
            )
            assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_update_custom_role_200(sm):
    """Verify PATCH custom role's permissions returns 200 and updates."""
    app = create_app()
    app.state.sessionmaker = sm

    # Create custom role
    async with sm() as session:
        role = Role(
            id="custom-role-id",
            name="custom_updateable",
            description="Original",
            built_in=False,
            permissions=["host:read"],
        )
        session.add(role)
        await session.commit()

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.patch(
                "/v1/roles/custom-role-id",
                json={"permissions": ["host:read", "host:write", "group:read"]},
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert set(data["permissions"]) == {"host:read", "host:write", "group:read"}

            # Verify GET also shows new perms
            r = await c.get(
                "/v1/roles/custom-role-id",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
            )
            assert r.status_code == 200
            data = r.json()
            assert set(data["permissions"]) == {"host:read", "host:write", "group:read"}


@pytest.mark.asyncio
async def test_delete_custom_role_204(sm):
    """Verify DELETE custom role with no bindings returns 204."""
    app = create_app()
    app.state.sessionmaker = sm

    # Create custom role
    async with sm() as session:
        role = Role(
            id="deletable-role-id",
            name="custom_deletable",
            description="To be deleted",
            built_in=False,
            permissions=["host:read"],
        )
        session.add(role)
        await session.commit()

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.delete(
                "/v1/roles/deletable-role-id",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
            )
            assert r.status_code == 204, r.text


@pytest.mark.asyncio
async def test_list_roles_admin_gated_401(sm):
    """Verify GET /v1/roles without token returns 401."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/roles")
            assert r.status_code == 401, r.text
