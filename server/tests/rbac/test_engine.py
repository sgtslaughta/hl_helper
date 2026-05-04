"""Tests for BuiltinEngine PolicyDecisionProvider."""
from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import pytest

from server.app.models import Binding, Role
from server.app.rbac.engine import BuiltinEngine
from server.app.rbac.provider import Principal, AuthContext
from server.app.rbac.scope import Resource


def compute_scope_hash(scope_kind: str, scope_value: dict) -> str:
    """Compute scope_hash for a binding."""
    data = {"kind": scope_kind, "value": scope_value}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


@pytest.mark.asyncio
async def test_engine_denies_default(sm) -> None:
    """No bindings -> deny."""
    async with sm() as session:
        engine = BuiltinEngine(session)
        principal = Principal(user_id="u-1")
        resource = Resource()
        ctx = AuthContext()

        decision = await engine.is_authorized(principal, "host:read", resource, ctx)
        assert not decision.allow
        assert decision.reason == "no_matching_binding"


@pytest.mark.asyncio
async def test_engine_grants_via_user_binding_global_scope(sm) -> None:
    """User with viewer role + global scope -> host:read allowed."""
    async with sm() as session:
        # Get viewer role from DB
        from sqlalchemy import select
        viewer_role = (await session.execute(
            select(Role).where(Role.name == "viewer")
        )).scalar_one()

        # Create binding
        binding = Binding(
            id=str(uuid4()),
            principal_type="user",
            principal_id="u-1",
            role_id=viewer_role.id,
            scope_kind="global",
            scope_value={},
            scope_hash=compute_scope_hash("global", {}),
        )
        session.add(binding)
        await session.commit()

        # Test authorization
        engine = BuiltinEngine(session)
        principal = Principal(user_id="u-1")
        resource = Resource()
        ctx = AuthContext()

        decision = await engine.is_authorized(principal, "host:read", resource, ctx)
        assert decision.allow
        assert decision.binding_id == binding.id
        assert "viewer" in (decision.reason or "")


@pytest.mark.asyncio
async def test_engine_denies_action_outside_role_perms(sm) -> None:
    """Viewer role does NOT grant host:exec."""
    async with sm() as session:
        from sqlalchemy import select
        viewer_role = (await session.execute(
            select(Role).where(Role.name == "viewer")
        )).scalar_one()

        binding = Binding(
            id=str(uuid4()),
            principal_type="user",
            principal_id="u-1",
            role_id=viewer_role.id,
            scope_kind="global",
            scope_value={},
            scope_hash=compute_scope_hash("global", {}),
        )
        session.add(binding)
        await session.commit()

        engine = BuiltinEngine(session)
        principal = Principal(user_id="u-1")
        resource = Resource()
        ctx = AuthContext()

        decision = await engine.is_authorized(principal, "host:exec", resource, ctx)
        assert not decision.allow
        assert decision.reason == "no_matching_binding"


@pytest.mark.asyncio
async def test_engine_denies_when_scope_excludes(sm) -> None:
    """host_list scope ["h-1"] does not cover resource id="h-2"."""
    async with sm() as session:
        from sqlalchemy import select
        viewer_role = (await session.execute(
            select(Role).where(Role.name == "viewer")
        )).scalar_one()

        scope_value = {"host_ids": ["h-1"]}
        binding = Binding(
            id=str(uuid4()),
            principal_type="user",
            principal_id="u-1",
            role_id=viewer_role.id,
            scope_kind="host_list",
            scope_value=scope_value,
            scope_hash=compute_scope_hash("host_list", scope_value),
        )
        session.add(binding)
        await session.commit()

        engine = BuiltinEngine(session)
        principal = Principal(user_id="u-1")
        resource = Resource(id="h-2")
        ctx = AuthContext()

        decision = await engine.is_authorized(principal, "host:read", resource, ctx)
        assert not decision.allow
        assert decision.reason == "no_matching_binding"


@pytest.mark.asyncio
async def test_engine_grants_via_user_group_binding(sm) -> None:
    """User has user_group_ids={ug-1}, binding on user_group ug-1 -> allowed."""
    async with sm() as session:
        from sqlalchemy import select
        operator_role = (await session.execute(
            select(Role).where(Role.name == "operator")
        )).scalar_one()

        binding = Binding(
            id=str(uuid4()),
            principal_type="user_group",
            principal_id="ug-1",
            role_id=operator_role.id,
            scope_kind="global",
            scope_value={},
            scope_hash=compute_scope_hash("global", {}),
        )
        session.add(binding)
        await session.commit()

        engine = BuiltinEngine(session)
        principal = Principal(user_id="u-1", user_group_ids=frozenset({"ug-1"}))
        resource = Resource()
        ctx = AuthContext()

        decision = await engine.is_authorized(principal, "task:create", resource, ctx)
        assert decision.allow
        assert decision.binding_id == binding.id


@pytest.mark.asyncio
async def test_engine_decision_includes_binding_id_and_reason_role_name(sm) -> None:
    """Decision includes binding_id and reason with role name."""
    async with sm() as session:
        from sqlalchemy import select
        admin_role = (await session.execute(
            select(Role).where(Role.name == "admin")
        )).scalar_one()

        binding = Binding(
            id=str(uuid4()),
            principal_type="user",
            principal_id="u-1",
            role_id=admin_role.id,
            scope_kind="global",
            scope_value={},
            scope_hash=compute_scope_hash("global", {}),
        )
        session.add(binding)
        await session.commit()

        engine = BuiltinEngine(session)
        principal = Principal(user_id="u-1")
        resource = Resource()
        ctx = AuthContext()

        decision = await engine.is_authorized(principal, "role:write", resource, ctx)
        assert decision.allow
        assert decision.binding_id == binding.id
        assert decision.reason == "role:admin"


@pytest.mark.asyncio
async def test_engine_grants_via_tag_scope(sm) -> None:
    """Binding scope_kind=tag covers resource with matching tag."""
    async with sm() as session:
        from sqlalchemy import select
        viewer_role = (await session.execute(
            select(Role).where(Role.name == "viewer")
        )).scalar_one()

        scope_value = {"key": "env", "value": "prod"}
        binding = Binding(
            id=str(uuid4()),
            principal_type="user",
            principal_id="u-1",
            role_id=viewer_role.id,
            scope_kind="tag",
            scope_value=scope_value,
            scope_hash=compute_scope_hash("tag", scope_value),
        )
        session.add(binding)
        await session.commit()

        engine = BuiltinEngine(session)
        principal = Principal(user_id="u-1")
        resource = Resource(tags=frozenset({("env", "prod")}))
        ctx = AuthContext()

        decision = await engine.is_authorized(principal, "host:read", resource, ctx)
        assert decision.allow
        assert decision.binding_id == binding.id


@pytest.mark.asyncio
async def test_engine_grants_via_group_scope(sm) -> None:
    """Binding scope_kind=group covers resource in that group."""
    async with sm() as session:
        from sqlalchemy import select
        operator_role = (await session.execute(
            select(Role).where(Role.name == "operator")
        )).scalar_one()

        scope_value = {"group_id": "g-1"}
        binding = Binding(
            id=str(uuid4()),
            principal_type="user",
            principal_id="u-1",
            role_id=operator_role.id,
            scope_kind="group",
            scope_value=scope_value,
            scope_hash=compute_scope_hash("group", scope_value),
        )
        session.add(binding)
        await session.commit()

        engine = BuiltinEngine(session)
        principal = Principal(user_id="u-1")
        resource = Resource(group_ids=frozenset({"g-1"}))
        ctx = AuthContext()

        decision = await engine.is_authorized(principal, "task:create", resource, ctx)
        assert decision.allow
        assert decision.binding_id == binding.id


@pytest.mark.asyncio
async def test_engine_grants_via_self_scope(sm) -> None:
    """Binding scope_kind=self covers resource owned by principal."""
    async with sm() as session:
        from sqlalchemy import select
        viewer_role = (await session.execute(
            select(Role).where(Role.name == "viewer")
        )).scalar_one()

        scope_value = {"principal_id": "u-1"}
        binding = Binding(
            id=str(uuid4()),
            principal_type="user",
            principal_id="u-1",
            role_id=viewer_role.id,
            scope_kind="self",
            scope_value=scope_value,
            scope_hash=compute_scope_hash("self", scope_value),
        )
        session.add(binding)
        await session.commit()

        engine = BuiltinEngine(session)
        principal = Principal(user_id="u-1")
        resource = Resource(owner_user_id="u-1")
        ctx = AuthContext()

        decision = await engine.is_authorized(principal, "host:read", resource, ctx)
        assert decision.allow
        assert decision.binding_id == binding.id

        # Different owner should be denied
        resource_other = Resource(owner_user_id="u-2")
        decision_other = await engine.is_authorized(principal, "host:read", resource_other, ctx)
        assert not decision_other.allow


@pytest.mark.asyncio
async def test_engine_grants_via_group_scope_with_nested_hierarchy(sm) -> None:
    """Binding on parent group covers resource in nested child group (3 levels)."""
    from sqlalchemy import select
    from server.app.models import Group
    from uuid import uuid4 as new_uuid

    async with sm() as session:
        # Create 3-level group hierarchy: parent -> child -> grandchild
        parent_id = new_uuid()
        child_id = new_uuid()
        grandchild_id = new_uuid()

        parent = Group(id=parent_id, name="parent", parent_id=None)
        child = Group(id=child_id, name="child", parent_id=parent_id)
        grandchild = Group(id=grandchild_id, name="grandchild", parent_id=child_id)

        session.add(parent)
        session.add(child)
        session.add(grandchild)
        await session.commit()

        # Get operator role
        operator_role = (await session.execute(
            select(Role).where(Role.name == "operator")
        )).scalar_one()

        # Create binding on parent group
        scope_value = {"group_id": str(parent_id)}
        binding = Binding(
            id=str(new_uuid()),
            principal_type="user",
            principal_id="u-1",
            role_id=operator_role.id,
            scope_kind="group",
            scope_value=scope_value,
            scope_hash=compute_scope_hash("group", scope_value),
        )
        session.add(binding)
        await session.commit()

        # Test: resource in grandchild group should be covered by parent binding
        engine = BuiltinEngine(session)
        principal = Principal(user_id="u-1")
        # Resource in grandchild group (3 levels down)
        resource = Resource(group_ids=frozenset({str(grandchild_id)}))
        ctx = AuthContext()

        decision = await engine.is_authorized(principal, "task:create", resource, ctx)
        assert decision.allow, "Binding on parent should grant access to grandchild"
        assert decision.binding_id == binding.id
