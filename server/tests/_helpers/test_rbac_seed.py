"""Tests for RBAC seeding helpers."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from server.app.models import Binding, Role, User
from server.app.models.binding import PrincipalType, ScopeKind
from server.app.models.user import UserKind
from server.app.rbac.engine import BuiltinEngine
from server.app.rbac.provider import Principal, AuthContext
from server.app.rbac.scope import Resource
from server.tests._helpers.rbac_seed import (
    grant_admin,
    grant_role_on_group,
    grant_role_on_host_list,
)


@pytest.mark.asyncio
async def test_grant_admin_creates_binding(sm) -> None:
    """grant_admin creates user + admin role binding with global scope."""
    async with sm() as session:
        binding_id = await grant_admin(session, user_id="test-user-1")

        # Verify binding exists with correct properties
        binding = await session.scalar(select(Binding).where(Binding.id == binding_id))
        assert binding is not None
        assert binding.principal_type == PrincipalType.USER
        assert binding.principal_id == "test-user-1"
        assert binding.scope_kind == ScopeKind.GLOBAL
        assert binding.scope_value == {}

        # Verify role is admin
        role = await session.scalar(select(Role).where(Role.id == binding.role_id))
        assert role is not None
        assert role.name == "admin"

        # Verify user was created
        user = await session.scalar(select(User).where(User.id == "test-user-1"))
        assert user is not None
        assert user.kind == UserKind.LOCAL


@pytest.mark.asyncio
async def test_grant_role_on_group_then_real_provider_authorizes(sm) -> None:
    """Seed binding for user + operator role on group; engine authorizes correctly."""
    async with sm() as session:
        group_id = "test-group-1"
        user_id = "test-user-2"

        # Grant operator role on group
        await grant_role_on_group(session, user_id=user_id, role_name="operator", group_id=group_id)

        # Verify binding exists
        binding = await session.scalar(
            select(Binding).where(
                (Binding.principal_id == user_id) & (Binding.scope_kind == ScopeKind.GROUP)
            )
        )
        assert binding is not None
        assert binding.scope_value == {"group_id": group_id}

        # Create engine and test authorization
        engine = BuiltinEngine(session)
        principal = Principal(user_id=user_id)
        ctx = AuthContext()

        # Test action that operator can perform on a resource in the group
        resource = Resource(id="host-1", group_ids=frozenset({group_id}))
        decision = await engine.is_authorized(principal, "host:exec", resource, ctx)
        assert decision.allow, f"Expected allow, got: {decision.reason}"
        assert decision.binding_id == binding.id


@pytest.mark.asyncio
async def test_grant_role_on_host_list_then_real_provider_authorizes(sm) -> None:
    """Seed binding for user + operator role on host_list; engine authorizes correctly."""
    async with sm() as session:
        host_ids = ["host-1", "host-2"]
        user_id = "test-user-3"

        # Grant operator role on host list
        binding_id = await grant_role_on_host_list(
            session, user_id=user_id, role_name="operator", host_ids=host_ids
        )

        # Verify binding exists
        binding = await session.scalar(select(Binding).where(Binding.id == binding_id))
        assert binding is not None
        assert binding.scope_kind == ScopeKind.HOST_LIST
        assert binding.scope_value == {"host_ids": host_ids}

        # Create engine and test authorization
        engine = BuiltinEngine(session)
        principal = Principal(user_id=user_id)
        ctx = AuthContext()

        # Test action on a host in the list
        resource = Resource(id="host-1")
        decision = await engine.is_authorized(principal, "host:exec", resource, ctx)
        assert decision.allow, f"Expected allow, got: {decision.reason}"

        # Test action on a host NOT in the list
        resource_outside = Resource(id="host-999")
        decision_outside = await engine.is_authorized(principal, "host:exec", resource_outside, ctx)
        assert not decision_outside.allow


@pytest.mark.asyncio
async def test_grant_missing_role_raises(sm) -> None:
    """Granting nonexistent role raises ValueError."""
    async with sm() as session:
        with pytest.raises(ValueError, match="Role.*not found"):
            await grant_role_on_group(
                session, user_id="test-user-4", role_name="nonexistent", group_id="g-1"
            )


@pytest.mark.asyncio
async def test_grant_idempotent(sm) -> None:
    """Granting same binding twice returns same id (no duplicates)."""
    async with sm() as session:
        user_id = "test-user-5"
        group_id = "group-1"

        # Grant once
        id_1 = await grant_role_on_group(
            session, user_id=user_id, role_name="viewer", group_id=group_id
        )

        # Grant again (should return same id)
        id_2 = await grant_role_on_group(
            session, user_id=user_id, role_name="viewer", group_id=group_id
        )

        assert id_1 == id_2

        # Verify only one binding exists
        bindings = (
            await session.execute(
                select(Binding).where(Binding.principal_id == user_id)
            )
        ).scalars().all()
        assert len(bindings) == 1
