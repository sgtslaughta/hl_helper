"""Tests for /v1/bindings endpoint."""

from __future__ import annotations

from typing import AsyncIterator
from unittest import mock

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.api.app import create_app
from server.app.models.role import Role
from server.app.settings.config import FleetSettings
from server.tests.models.conftest import sm  # noqa: F401


@pytest.fixture
async def client(sm: async_sessionmaker) -> AsyncIterator[httpx.AsyncClient]:  # noqa: F811
    """Create FastAPI test client with sessionmaker in app state."""
    app = create_app()

    # Set the sessionmaker in app state
    app.state.sessionmaker = sm

    # Mock settings with test admin token
    mock_settings = FleetSettings(admin_token=SecretStr("test-admin-token"))

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": "Bearer test-admin-token"},
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_list_bindings_admin_gated_401(sm: async_sessionmaker) -> None:  # noqa: F811
    """GET /v1/bindings without auth → 401."""
    app = create_app()
    app.state.sessionmaker = sm

    mock_settings = FleetSettings(admin_token=SecretStr("test-admin-token"))

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/v1/bindings")
            assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_global_binding_201(client: httpx.AsyncClient) -> None:
    """POST /v1/bindings with global scope → 201."""
    # Get a role ID from the seeded roles that were created in the fixture's app.state.sessionmaker
    session_maker = client._transport.app.state.sessionmaker
    async with session_maker() as session:
        role = await session.scalar(
            select(Role).where(Role.name == "viewer")
        )
        role_id = role.id

    resp = await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-1",
            "role_id": role_id,
            "scope_kind": "global",
            "scope_value": {},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["principal_type"] == "user"
    assert data["principal_id"] == "u-1"
    assert data["scope_kind"] == "global"
    assert data["scope_hash"] is not None


@pytest.mark.asyncio
async def test_create_group_binding_with_value_validates(client: httpx.AsyncClient) -> None:
    """POST /v1/bindings with group scope validates shape."""
    session_maker = client._transport.app.state.sessionmaker
    async with session_maker() as session:
        role = await session.scalar(
            select(Role).where(Role.name == "viewer")
        )
        role_id = role.id

    resp = await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-1",
            "role_id": role_id,
            "scope_kind": "group",
            "scope_value": {"group_id": "g-1"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["scope_kind"] == "group"


@pytest.mark.asyncio
async def test_create_invalid_scope_value_shape_422(client: httpx.AsyncClient) -> None:
    """POST /v1/bindings with invalid scope_value shape → 422."""
    session_maker = client._transport.app.state.sessionmaker
    async with session_maker() as session:
        role = await session.scalar(
            select(Role).where(Role.name == "viewer")
        )
        role_id = role.id

    resp = await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-1",
            "role_id": role_id,
            "scope_kind": "group",
            "scope_value": {},  # Missing group_id
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_unknown_scope_kind_422(client: httpx.AsyncClient) -> None:
    """POST /v1/bindings with invalid scope_kind → 422."""
    session_maker = client._transport.app.state.sessionmaker
    async with session_maker() as session:
        role = await session.scalar(
            select(Role).where(Role.name == "viewer")
        )
        role_id = role.id

    resp = await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-1",
            "role_id": role_id,
            "scope_kind": "bogus",
            "scope_value": {},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_binding_409(client: httpx.AsyncClient) -> None:
    """POST same binding twice → second is 409."""
    session_maker = client._transport.app.state.sessionmaker
    async with session_maker() as session:
        role = await session.scalar(
            select(Role).where(Role.name == "viewer")
        )
        role_id = role.id

    payload = {
        "principal_type": "user",
        "principal_id": "u-1",
        "role_id": role_id,
        "scope_kind": "global",
        "scope_value": {},
    }

    # First POST
    resp1 = await client.post("/v1/bindings", json=payload)
    assert resp1.status_code == 201

    # Second POST same tuple
    resp2 = await client.post("/v1/bindings", json=payload)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_filter_by_principal_id(client: httpx.AsyncClient) -> None:
    """GET /v1/bindings?principal_id=u-1 filters correctly."""
    session_maker = client._transport.app.state.sessionmaker
    async with session_maker() as session:
        role = await session.scalar(
            select(Role).where(Role.name == "viewer")
        )
        role_id = role.id

    # Create binding for u-1
    await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-1",
            "role_id": role_id,
            "scope_kind": "global",
            "scope_value": {},
        },
    )

    # Create binding for u-2
    await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-2",
            "role_id": role_id,
            "scope_kind": "global",
            "scope_value": {},
        },
    )

    # Filter by u-1
    resp = await client.get("/v1/bindings?principal_id=u-1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["principal_id"] == "u-1"


@pytest.mark.asyncio
async def test_delete_binding_204_then_404(client: httpx.AsyncClient) -> None:
    """DELETE /v1/bindings/{id} returns 204, then 404 on second attempt."""
    session_maker = client._transport.app.state.sessionmaker
    async with session_maker() as session:
        role = await session.scalar(
            select(Role).where(Role.name == "viewer")
        )
        role_id = role.id

    # Create binding
    create_resp = await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-1",
            "role_id": role_id,
            "scope_kind": "global",
            "scope_value": {},
        },
    )
    binding_id = create_resp.json()["id"]

    # Delete
    del_resp = await client.delete(f"/v1/bindings/{binding_id}")
    assert del_resp.status_code == 204

    # Get after delete
    get_resp = await client.get(f"/v1/bindings/{binding_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_create_with_unknown_role_id_422(client: httpx.AsyncClient) -> None:
    """POST /v1/bindings with unknown role_id → 422."""
    resp = await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-1",
            "role_id": "unknown-role-id",
            "scope_kind": "global",
            "scope_value": {},
        },
    )
    assert resp.status_code == 422
