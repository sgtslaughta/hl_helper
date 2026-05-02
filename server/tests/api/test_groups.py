"""Tests for /v1/groups API endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator
from unittest import mock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.models.base import Base
from server.app.models.group_membership import GroupMembership
from server.app.settings.config import FleetSettings
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

    app.state.sessionmaker = async_session_maker

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
async def test_create_group_201(client: httpx.AsyncClient):
    """POST /v1/groups with admin bearer returns 201 with created group."""
    response = await client.post(
        "/v1/groups",
        json={
            "name": "test-group",
            "description": "A test group",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "test-group"
    assert data["description"] == "A test group"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_list_groups_admin_gated(client: httpx.AsyncClient):
    """GET /v1/groups without bearer returns 401; with bearer returns 200."""
    # Without bearer
    response = await client.get("/v1/groups")
    assert response.status_code == 401

    # Create a group first
    await client.post(
        "/v1/groups",
        json={"name": "group1"},
        headers={"Authorization": "Bearer test-admin-token"},
    )

    # With bearer
    response = await client.get(
        "/v1/groups",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_group_404_when_missing(client: httpx.AsyncClient):
    """GET /v1/groups/{id} with nonexistent id returns 404."""
    fake_id = str(uuid4())
    response = await client.get(
        f"/v1/groups/{fake_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_group_patches_name(client: httpx.AsyncClient):
    """PATCH /v1/groups/{id} updates name; GET shows new name."""
    # Create group
    create_resp = await client.post(
        "/v1/groups",
        json={"name": "original-name"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = create_resp.json()["id"]

    # Update name
    patch_resp = await client.patch(
        f"/v1/groups/{group_id}",
        json={"name": "updated-name"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "updated-name"

    # Verify via GET
    get_resp = await client.get(
        f"/v1/groups/{group_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "updated-name"


@pytest.mark.asyncio
async def test_delete_group_204_then_404(client: httpx.AsyncClient):
    """DELETE /v1/groups/{id} removes group; subsequent GET returns 404."""
    # Create group
    create_resp = await client.post(
        "/v1/groups",
        json={"name": "to-delete"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = create_resp.json()["id"]

    # Delete
    delete_resp = await client.delete(
        f"/v1/groups/{group_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert delete_resp.status_code == 204

    # Verify gone
    get_resp = await client.get(
        f"/v1/groups/{group_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_unique_name_conflict_409(client: httpx.AsyncClient):
    """POST with duplicate name returns 409."""
    # Create first group
    await client.post(
        "/v1/groups",
        json={"name": "unique-name"},
        headers={"Authorization": "Bearer test-admin-token"},
    )

    # Try to create with same name
    response = await client.post(
        "/v1/groups",
        json={"name": "unique-name"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_add_member_then_remove(client: httpx.AsyncClient, async_session_maker):
    """POST member adds row; DELETE removes it."""
    # Create a host first (required for FK constraint)
    from server.app.models.host import Host
    async with async_session_maker() as session:
        host = Host(
            id="host-123",
            hostname="test-host",
            agent_pubkey=b"x" * 32,
        )
        session.add(host)
        await session.commit()

    # Create group
    create_resp = await client.post(
        "/v1/groups",
        json={"name": "member-test-group"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = create_resp.json()["id"]

    # Add member
    add_resp = await client.post(
        f"/v1/groups/{group_id}/members",
        json={"host_id": "host-123", "kind": "static"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert add_resp.status_code == 201

    # Verify in DB
    async with async_session_maker() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(GroupMembership).where(GroupMembership.host_id == "host-123")
        )
        membership = result.scalars().first()
        assert membership is not None
        assert membership.group_id == UUID(group_id)

    # Remove member
    del_resp = await client.delete(
        f"/v1/groups/{group_id}/members/host-123",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert del_resp.status_code == 204

    # Verify removed
    async with async_session_maker() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(GroupMembership).where(GroupMembership.host_id == "host-123")
        )
        membership = result.scalars().first()
        assert membership is None


@pytest.mark.asyncio
async def test_create_with_invalid_parent_returns_404(
    client: httpx.AsyncClient,
):
    """POST with nonexistent parent_id returns 404."""
    response = await client.post(
        "/v1/groups",
        json={
            "name": "child-group",
            "parent_id": str(uuid4()),
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_uuid_returns_400(client: httpx.AsyncClient):
    """GET /v1/groups/{invalid_uuid} returns 400."""
    response = await client.get(
        "/v1/groups/not-a-uuid",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 400
    assert "invalid_uuid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_patch_clear_parent_id_to_null(client: httpx.AsyncClient):
    """PATCH with parent_id=null clears parent."""
    # Create parent
    parent_resp = await client.post(
        "/v1/groups",
        json={"name": "parent-group"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    parent_id = parent_resp.json()["id"]

    # Create child
    child_resp = await client.post(
        "/v1/groups",
        json={"name": "child-group", "parent_id": parent_id},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    child_id = child_resp.json()["id"]
    assert child_resp.json()["parent_id"] == parent_id

    # Clear parent_id
    patch_resp = await client.patch(
        f"/v1/groups/{child_id}",
        json={"parent_id": None},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["parent_id"] is None

    # Verify via GET
    get_resp = await client.get(
        f"/v1/groups/{child_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert get_resp.json()["parent_id"] is None


@pytest.mark.asyncio
async def test_patch_clear_description(client: httpx.AsyncClient):
    """PATCH with description=null clears description."""
    # Create with description
    create_resp = await client.post(
        "/v1/groups",
        json={"name": "desc-group", "description": "original"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = create_resp.json()["id"]
    assert create_resp.json()["description"] == "original"

    # Clear description
    patch_resp = await client.patch(
        f"/v1/groups/{group_id}",
        json={"description": None},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["description"] is None


@pytest.mark.asyncio
async def test_add_duplicate_member_409(client: httpx.AsyncClient, async_session_maker):
    """POST member twice returns 409."""
    # Create a host first (required for FK constraint)
    from server.app.models.host import Host
    async with async_session_maker() as session:
        host = Host(
            id="host-x",
            hostname="test-host-x",
            agent_pubkey=b"x" * 32,
        )
        session.add(host)
        await session.commit()

    # Create group
    create_resp = await client.post(
        "/v1/groups",
        json={"name": "dup-test"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = create_resp.json()["id"]

    # Add member first time
    resp1 = await client.post(
        f"/v1/groups/{group_id}/members",
        json={"host_id": "host-x", "kind": "static"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert resp1.status_code == 201

    # Add same member again
    resp2 = await client.post(
        f"/v1/groups/{group_id}/members",
        json={"host_id": "host-x", "kind": "static"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert resp2.status_code == 409
    assert "already_member" in resp2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_add_member_with_unknown_host_404(client: httpx.AsyncClient):
    """POST member with nonexistent host_id returns 404."""
    # Create group
    create_resp = await client.post(
        "/v1/groups",
        json={"name": "unknown-host-test"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = create_resp.json()["id"]

    # Try to add nonexistent host (FK constraint violation)
    response = await client.post(
        f"/v1/groups/{group_id}/members",
        json={"host_id": "nonexistent-host-999", "kind": "static"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404
    assert "host_not_found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remove_nonexistent_member_404(client: httpx.AsyncClient):
    """DELETE nonexistent member returns 404."""
    # Create group
    create_resp = await client.post(
        "/v1/groups",
        json={"name": "remove-test"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = create_resp.json()["id"]

    # Try to remove nonexistent member
    response = await client.delete(
        f"/v1/groups/{group_id}/members/nonexistent-host",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404
    assert "membership_not_found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_kind_422(client: httpx.AsyncClient):
    """POST member with invalid kind returns 422."""
    # Create group
    create_resp = await client.post(
        "/v1/groups",
        json={"name": "kind-test"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    group_id = create_resp.json()["id"]

    response = await client.post(
        f"/v1/groups/{group_id}/members",
        json={"host_id": "some-host", "kind": "invalid_kind"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_circular_parent_ref_rejected_400(client: httpx.AsyncClient):
    """PATCH A.parent_id=B then B.parent_id=A returns 400."""
    # Create A
    a_resp = await client.post(
        "/v1/groups",
        json={"name": "group-a"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    a_id = a_resp.json()["id"]

    # Create B with parent A
    b_resp = await client.post(
        "/v1/groups",
        json={"name": "group-b", "parent_id": a_id},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    b_id = b_resp.json()["id"]

    # Try to set A.parent_id = B (creates cycle A -> B -> A)
    response = await client.patch(
        f"/v1/groups/{a_id}",
        json={"parent_id": b_id},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 400
    assert "circular" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_self_parent_ref_rejected_400(client: httpx.AsyncClient):
    """PATCH A.parent_id=A returns 400."""
    # Create A
    create_resp = await client.post(
        "/v1/groups",
        json={"name": "self-parent"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    a_id = create_resp.json()["id"]

    # Try to set parent to self
    response = await client.patch(
        f"/v1/groups/{a_id}",
        json={"parent_id": a_id},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 400
    assert "circular" in response.json()["detail"].lower()
