"""Tests for /v1/users, /v1/user-groups, /v1/service-accounts API endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import httpx
import pytest
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
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def client(async_session_maker):
    """Create FastAPI test client with test database."""
    app = create_app()
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


@pytest.mark.asyncio
async def test_create_local_user_201(client: httpx.AsyncClient):
    """POST /v1/users with local kind returns 201."""
    response = await client.post(
        "/v1/users",
        json={
            "email": "local@example.com",
            "kind": "local",
            "display_name": "Local User",
            "password_hash": "argon2id$...",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "local@example.com"
    assert data["kind"] == "local"
    assert data["display_name"] == "Local User"
    assert data["disabled"] is False
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_oidc_user_201(client: httpx.AsyncClient):
    """POST /v1/users with OIDC kind returns 201."""
    response = await client.post(
        "/v1/users",
        json={
            "email": "oidc@example.com",
            "kind": "oidc",
            "oidc_subject": "subject-123",
            "oidc_issuer": "https://issuer.example.com",
            "display_name": "OIDC User",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "oidc@example.com"
    assert data["kind"] == "oidc"
    assert data["oidc_subject"] == "subject-123"
    assert data["oidc_issuer"] == "https://issuer.example.com"
    assert data["display_name"] == "OIDC User"


@pytest.mark.asyncio
async def test_email_conflict_409(client: httpx.AsyncClient):
    """POST /v1/users with duplicate email returns 409."""
    # Create first user
    response1 = await client.post(
        "/v1/users",
        json={
            "email": "conflict@example.com",
            "kind": "local",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response1.status_code == 201

    # Try to create second user with same email
    response2 = await client.post(
        "/v1/users",
        json={
            "email": "conflict@example.com",
            "kind": "oidc",
            "oidc_subject": "sub-2",
            "oidc_issuer": "https://issuer2.example.com",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response2.status_code == 409


@pytest.mark.asyncio
async def test_oidc_user_does_not_accept_password_hash(client: httpx.AsyncClient):
    """POST /v1/users with oidc kind and password_hash returns 422."""
    response = await client.post(
        "/v1/users",
        json={
            "email": "oidc@example.com",
            "kind": "oidc",
            "oidc_subject": "subject-123",
            "oidc_issuer": "https://issuer.example.com",
            "password_hash": "should-be-rejected",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_disable_user_via_patch(client: httpx.AsyncClient):
    """PATCH /v1/users/{id} with disabled=true returns 200."""
    # Create user
    response = await client.post(
        "/v1/users",
        json={"email": "user@example.com", "kind": "local"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    user_id = response.json()["id"]

    # Disable user
    response = await client.patch(
        f"/v1/users/{user_id}",
        json={"disabled": True},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["disabled"] is True


@pytest.mark.asyncio
async def test_delete_user_204(client: httpx.AsyncClient):
    """DELETE /v1/users/{id} returns 204."""
    # Create user
    response = await client.post(
        "/v1/users",
        json={"email": "delete@example.com", "kind": "local"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    user_id = response.json()["id"]

    # Delete user
    response = await client.delete(
        f"/v1/users/{user_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_list_users_admin_gated_401(client: httpx.AsyncClient):
    """GET /v1/users without admin bearer returns 401."""
    response = await client.get("/v1/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_200(client: httpx.AsyncClient):
    """GET /v1/users/{id} returns 200."""
    # Create user
    response = await client.post(
        "/v1/users",
        json={"email": "get@example.com", "kind": "local", "display_name": "Get User"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    user_id = response.json()["id"]

    # Get user
    response = await client.get(
        f"/v1/users/{user_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["email"] == "get@example.com"
    assert data["display_name"] == "Get User"


@pytest.mark.asyncio
async def test_user_group_create_and_add_member(client: httpx.AsyncClient):
    """POST /v1/user-groups and POST /v1/user-groups/{id}/members."""
    # Create user
    user_resp = await client.post(
        "/v1/users",
        json={"email": "member@example.com", "kind": "local"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    user_id = user_resp.json()["id"]

    # Create group
    group_resp = await client.post(
        "/v1/user-groups",
        json={"name": "developers", "description": "Dev team"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    # Add member
    member_resp = await client.post(
        f"/v1/user-groups/{group_id}/members",
        json={"user_id": user_id},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert member_resp.status_code == 201


@pytest.mark.asyncio
async def test_remove_user_group_member_204(client: httpx.AsyncClient):
    """DELETE /v1/user-groups/{id}/members/{user_id} returns 204."""
    # Create user and group
    user_resp = await client.post(
        "/v1/users",
        json={"email": "remove@example.com", "kind": "local"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    user_id = user_resp.json()["id"]

    group_resp = await client.post(
        "/v1/user-groups",
        json={"name": "admins"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = group_resp.json()["id"]

    # Add member
    await client.post(
        f"/v1/user-groups/{group_id}/members",
        json={"user_id": user_id},
        headers={"Authorization": "Bearer test-admin-token"},
    )

    # Remove member
    response = await client.delete(
        f"/v1/user-groups/{group_id}/members/{user_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_service_account_crud(client: httpx.AsyncClient):
    """POST /v1/service-accounts and DELETE."""
    # Create service account
    create_resp = await client.post(
        "/v1/service-accounts",
        json={"name": "ci-bot", "description": "CI automation"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert create_resp.status_code == 201
    sa_id = create_resp.json()["id"]
    assert create_resp.json()["name"] == "ci-bot"

    # List service accounts
    list_resp = await client.get(
        "/v1/service-accounts",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert list_resp.status_code == 200
    accounts = list_resp.json()
    assert any(a["id"] == sa_id for a in accounts)

    # Delete service account
    delete_resp = await client.delete(
        f"/v1/service-accounts/{sa_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_patch_user_404_when_missing(client: httpx.AsyncClient):
    """PATCH /v1/users/{id} with missing user returns 404."""
    response = await client.patch(
        "/v1/users/nonexistent",
        json={"display_name": "New Name"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_user_404_when_missing(client: httpx.AsyncClient):
    """DELETE /v1/users/{id} with missing user returns 404."""
    response = await client.delete(
        "/v1/users/nonexistent",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_service_account_404_when_missing(client: httpx.AsyncClient):
    """DELETE /v1/service-accounts/{id} with missing account returns 404."""
    response = await client.delete(
        "/v1/service-accounts/nonexistent",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remove_user_group_member_404_when_missing(client: httpx.AsyncClient):
    """DELETE /v1/user-groups/{id}/members/{user_id} with missing membership returns 404."""
    # Create a user and group
    user_resp = await client.post(
        "/v1/users",
        json={"email": "test404@example.com", "kind": "local"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    user_id = user_resp.json()["id"]

    group_resp = await client.post(
        "/v1/user-groups",
        json={"name": "test404group"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = group_resp.json()["id"]

    # Try to remove a non-existent membership
    response = await client.delete(
        f"/v1/user-groups/{group_id}/members/{user_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_includes_disabled_users(client: httpx.AsyncClient):
    """GET /v1/users includes disabled users."""
    # Create a disabled user
    response = await client.post(
        "/v1/users",
        json={"email": "disabled@example.com", "kind": "local"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    user_id = response.json()["id"]

    # Disable the user
    await client.patch(
        f"/v1/users/{user_id}",
        json={"disabled": True},
        headers={"Authorization": "Bearer test-admin-token"},
    )

    # List users and verify disabled user is present
    list_resp = await client.get(
        "/v1/users",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert list_resp.status_code == 200
    users = list_resp.json()
    disabled_user = next((u for u in users if u["id"] == user_id), None)
    assert disabled_user is not None
    assert disabled_user["disabled"] is True


@pytest.mark.asyncio
async def test_patch_display_name_only(client: httpx.AsyncClient):
    """PATCH /v1/users/{id} with only display_name keeps disabled unchanged."""
    # Create user
    response = await client.post(
        "/v1/users",
        json={"email": "patch@example.com", "kind": "local"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    user_id = response.json()["id"]

    # PATCH only display_name
    response = await client.patch(
        f"/v1/users/{user_id}",
        json={"display_name": "Updated Name"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Updated Name"
    assert data["disabled"] is False


@pytest.mark.asyncio
async def test_user_group_name_unique_409(client: httpx.AsyncClient):
    """POST /v1/user-groups with duplicate name returns 409."""
    # Create first group
    response1 = await client.post(
        "/v1/user-groups",
        json={"name": "unique-group"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response1.status_code == 201

    # Try to create second group with same name
    response2 = await client.post(
        "/v1/user-groups",
        json={"name": "unique-group"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response2.status_code == 409


@pytest.mark.asyncio
async def test_service_account_name_unique_409(client: httpx.AsyncClient):
    """POST /v1/service-accounts with duplicate name returns 409."""
    # Create first service account
    response1 = await client.post(
        "/v1/service-accounts",
        json={"name": "unique-sa"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response1.status_code == 201

    # Try to create second with same name
    response2 = await client.post(
        "/v1/service-accounts",
        json={"name": "unique-sa"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response2.status_code == 409


@pytest.mark.asyncio
async def test_service_account_patch_disabled(client: httpx.AsyncClient):
    """PATCH /v1/service-accounts/{id} updates disabled flag."""
    # Create service account
    create_resp = await client.post(
        "/v1/service-accounts",
        json={"name": "patch-sa", "description": "Original"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert create_resp.status_code == 201
    sa_id = create_resp.json()["id"]
    assert create_resp.json()["disabled"] is False

    # PATCH disabled flag
    patch_resp = await client.patch(
        f"/v1/service-accounts/{sa_id}",
        json={"disabled": True},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["disabled"] is True
    assert data["description"] == "Original"

    # PATCH description only
    patch_resp2 = await client.patch(
        f"/v1/service-accounts/{sa_id}",
        json={"description": "Updated"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert patch_resp2.status_code == 200
    data2 = patch_resp2.json()
    assert data2["disabled"] is True
    assert data2["description"] == "Updated"


@pytest.mark.asyncio
async def test_user_group_add_member_unknown_user_404(client: httpx.AsyncClient):
    """POST /v1/user-groups/{id}/members with unknown user_id returns 404."""
    # Create group
    group_resp = await client.post(
        "/v1/user-groups",
        json={"name": "testgroup"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = group_resp.json()["id"]

    # Try to add non-existent user
    response = await client.post(
        f"/v1/user-groups/{group_id}/members",
        json={"user_id": "nonexistent"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_email_invalid_format_422(client: httpx.AsyncClient):
    """POST /v1/users with invalid email format returns 422."""
    response = await client.post(
        "/v1/users",
        json={"email": "not-an-email", "kind": "local"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 422
