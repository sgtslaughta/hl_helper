"""Tests for acting_principal dependency and X-Acting-Principal header validation."""

from __future__ import annotations

from unittest import mock

import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr

from server.app.api.app import create_app
from server.app.deps import current_principal
from server.app.models.user import User, UserKind
from server.app.models.binding import Binding
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
async def test_acting_principal_header_absent_uses_authenticated(sm, auth, mock_settings):
    """If X-Acting-Principal header absent, use authenticated principal."""
    # Create an authenticated user
    async with sm() as session:
        user = User(
            id="user-auth",
            email="auth@example.com",
            kind=UserKind.LOCAL,
        )
        session.add(user)
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="user-auth")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create an approval without X-Acting-Principal header
            # It should use the authenticated principal
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-1",
                    "policy": "single",
                },
                headers=auth,
            )
            assert r.status_code == 201
            assert r.json()["requester_id"] == "user-auth"


@pytest.mark.asyncio
async def test_acting_principal_header_matches_user_id_ok(sm, auth, mock_settings):
    """If X-Acting-Principal == current.user_id, return current principal."""
    async with sm() as session:
        user = User(
            id="user-auth",
            email="auth@example.com",
            kind=UserKind.LOCAL,
        )
        session.add(user)
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="user-auth")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-1",
                    "policy": "single",
                },
                headers={**auth, "X-Acting-Principal": "user-auth"},
            )
            assert r.status_code == 201
            assert r.json()["requester_id"] == "user-auth"


@pytest.mark.asyncio
async def test_acting_principal_header_different_no_permission_403(
    sm, auth, mock_settings
):
    """If X-Acting-Principal != user_id and no impersonate perm, 403."""
    async with sm() as session:
        user1 = User(
            id="user-auth",
            email="auth@example.com",
            kind=UserKind.LOCAL,
        )
        user2 = User(
            id="user-other",
            email="other@example.com",
            kind=UserKind.LOCAL,
        )
        session.add_all([user1, user2])
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="user-auth")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-1",
                    "policy": "single",
                },
                headers={**auth, "X-Acting-Principal": "user-other"},
            )
            assert r.status_code == 403
            assert "forbidden" in r.json()["detail"]


@pytest.mark.asyncio
async def test_acting_principal_header_different_with_impersonate_ok(
    sm, auth, mock_settings
):
    """If X-Acting-Principal != user_id but has impersonate perm, return spoofed principal."""
    async with sm() as session:
        # Create two users
        user1 = User(
            id="user-auth",
            email="auth@example.com",
            kind=UserKind.LOCAL,
        )
        user2 = User(
            id="user-other",
            email="other@example.com",
            kind=UserKind.LOCAL,
        )
        session.add_all([user1, user2])

        # Create a role with impersonate permission
        role = Role(
            name="impersonator",
            built_in=False,
            permissions=["user:impersonate"],
        )
        session.add(role)
        await session.commit()

        # Create a global binding for user1 to this role
        binding = Binding(
            principal_type="user",
            principal_id="user-auth",
            role_id=role.id,
            scope_kind="global",
            scope_value={},
            scope_hash="global-scope-hash",
        )
        session.add(binding)
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="user-auth")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-1",
                    "policy": "single",
                },
                headers={**auth, "X-Acting-Principal": "user-other"},
            )
            assert r.status_code == 201
            assert r.json()["requester_id"] == "user-other"


@pytest.mark.asyncio
async def test_acting_principal_header_nonexistent_user_404(
    sm, auth, mock_settings
):
    """If X-Acting-Principal points to non-existent user and has impersonate perm, 404."""
    async with sm() as session:
        user1 = User(
            id="user-auth",
            email="auth@example.com",
            kind=UserKind.LOCAL,
        )
        session.add(user1)

        # Create a role with impersonate permission
        role = Role(
            name="impersonator",
            built_in=False,
            permissions=["user:impersonate"],
        )
        session.add(role)
        await session.commit()

        # Create a global binding for user1 to this role
        binding = Binding(
            principal_type="user",
            principal_id="user-auth",
            role_id=role.id,
            scope_kind="global",
            scope_value={},
            scope_hash="global-scope-hash",
        )
        session.add(binding)
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="user-auth")

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-1",
                    "policy": "single",
                },
                headers={**auth, "X-Acting-Principal": "user-nonexistent"},
            )
            assert r.status_code == 404
