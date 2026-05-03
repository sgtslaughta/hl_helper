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
from server.tests._helpers.app_state import make_test_app_state
from server.tests.models.conftest import sm  # noqa: F401


@pytest.fixture
async def client(sm: async_sessionmaker) -> AsyncIterator[httpx.AsyncClient]:  # noqa: F811
    """Create FastAPI test client with sessionmaker in app state."""
    app = create_app()

    # Set the sessionmaker in app state
    app.state.app_state = make_test_app_state(sessionmaker=sm)

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
    app.state.app_state = make_test_app_state(sessionmaker=sm)

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
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
async def test_scope_hash_deterministic_for_value_key_order(client: httpx.AsyncClient) -> None:
    """POST two bindings with same scope_value but different key order → 409."""
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
    async with session_maker() as session:
        role = await session.scalar(
            select(Role).where(Role.name == "viewer")
        )
        role_id = role.id

    # First POST with one key order
    resp1 = await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-hash-test",
            "role_id": role_id,
            "scope_kind": "tag",
            "scope_value": {"key": "env", "value": "prod"},
        },
    )
    assert resp1.status_code == 201

    # Second POST with different key order (value before key)
    resp2 = await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-hash-test",
            "role_id": role_id,
            "scope_kind": "tag",
            "scope_value": {"value": "prod", "key": "env"},
        },
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_host_list_with_non_string_element_422(client: httpx.AsyncClient) -> None:
    """POST with host_ids containing non-string → 422."""
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
            "scope_kind": "host_list",
            "scope_value": {"host_ids": [1, 2]},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_host_list_with_empty_string_element_422(client: httpx.AsyncClient) -> None:
    """POST with host_ids containing empty string → 422."""
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
            "scope_kind": "host_list",
            "scope_value": {"host_ids": [""]},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_self_with_empty_principal_id_422(client: httpx.AsyncClient) -> None:
    """POST with self scope and empty principal_id → 422."""
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
            "scope_kind": "self",
            "scope_value": {"principal_id": ""},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tag_with_empty_key_or_value_422(client: httpx.AsyncClient) -> None:
    """POST with tag scope and empty key/value → 422."""
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
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
            "scope_kind": "tag",
            "scope_value": {"key": "", "value": "prod"},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_filter_combined_principal_and_role(client: httpx.AsyncClient) -> None:
    """GET /v1/bindings with both principal_id and role_id filters."""
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
    async with session_maker() as session:
        role = await session.scalar(
            select(Role).where(Role.name == "viewer")
        )
        role_id = role.id

    # Create two bindings: different principals, same role
    await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-combined-1",
            "role_id": role_id,
            "scope_kind": "global",
            "scope_value": {},
        },
    )

    await client.post(
        "/v1/bindings",
        json={
            "principal_type": "user",
            "principal_id": "u-combined-2",
            "role_id": role_id,
            "scope_kind": "global",
            "scope_value": {},
        },
    )

    # Filter by both principal_id and role_id
    resp = await client.get(
        f"/v1/bindings?principal_id=u-combined-1&role_id={role_id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["principal_id"] == "u-combined-1"
    assert data[0]["role_id"] == role_id


@pytest.mark.asyncio
async def test_delete_then_recreate_succeeds(client: httpx.AsyncClient) -> None:
    """DELETE a binding then POST same tuple → 201 (no ghost duplicate)."""
    app = client._transport.app
    session_maker = app.state.app_state.sessionmaker
    async with session_maker() as session:
        role = await session.scalar(
            select(Role).where(Role.name == "viewer")
        )
        role_id = role.id

    payload = {
        "principal_type": "user",
        "principal_id": "u-recreate",
        "role_id": role_id,
        "scope_kind": "global",
        "scope_value": {},
    }

    # Create binding
    create_resp = await client.post("/v1/bindings", json=payload)
    assert create_resp.status_code == 201
    binding_id = create_resp.json()["id"]

    # Delete binding
    del_resp = await client.delete(f"/v1/bindings/{binding_id}")
    assert del_resp.status_code == 204

    # Recreate same binding → should succeed with 201
    recreate_resp = await client.post("/v1/bindings", json=payload)
    assert recreate_resp.status_code == 201


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
