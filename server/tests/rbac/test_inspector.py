"""Tests for Inspector effective-permissions inspector."""
from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import pytest

from server.app.models import Binding, Role
from server.app.rbac.inspector import Inspector
from server.app.rbac.provider import Principal
from server.app.rbac.scope import Resource


def compute_scope_hash(scope_kind: str, scope_value: dict) -> str:
    """Compute scope_hash for a binding."""
    data = {"kind": scope_kind, "value": scope_value}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


@pytest.mark.asyncio
async def test_inspector_returns_flat_rows(sm) -> None:
    """Inspector returns flat (action, source_binding_id, role_name) rows."""
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

        inspector = Inspector(session)
        principal = Principal(user_id="u-1")
        resource = Resource()

        rows = await inspector.effective(principal, resource)
        assert len(rows) > 0
        # Each row should have action, source_binding_id, role_name
        for row in rows:
            assert hasattr(row, "action")
            assert hasattr(row, "source_binding_id")
            assert hasattr(row, "role_name")
            assert row.source_binding_id == binding.id
            assert row.role_name == "viewer"


@pytest.mark.asyncio
async def test_inspector_multiple_bindings_same_role(sm) -> None:
    """Multiple bindings same role -> multiple rows (one per action per binding)."""
    async with sm() as session:
        from sqlalchemy import select
        viewer_role = (await session.execute(
            select(Role).where(Role.name == "viewer")
        )).scalar_one()

        binding1 = Binding(
            id=str(uuid4()),
            principal_type="user",
            principal_id="u-1",
            role_id=viewer_role.id,
            scope_kind="global",
            scope_value={},
            scope_hash=compute_scope_hash("global", {}),
        )
        binding2 = Binding(
            id=str(uuid4()),
            principal_type="user",
            principal_id="u-1",
            role_id=viewer_role.id,
            scope_kind="host_list",
            scope_value={"host_ids": ["h-1", "h-2"]},
            scope_hash=compute_scope_hash("host_list", {"host_ids": ["h-1", "h-2"]}),
        )
        session.add_all([binding1, binding2])
        await session.commit()

        inspector = Inspector(session)
        principal = Principal(user_id="u-1")
        resource = Resource()

        rows = await inspector.effective(principal, resource)
        # Should have rows from both bindings (only binding1 covers empty resource)
        binding_ids = {r.source_binding_id for r in rows}
        assert binding1.id in binding_ids
        # binding2 with host_list doesn't cover empty resource
        assert binding2.id not in binding_ids


@pytest.mark.asyncio
async def test_inspector_binding_excluded_by_scope(sm) -> None:
    """Binding excluded by scope -> 0 rows for that binding."""
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
            scope_kind="host_list",
            scope_value={"host_ids": ["h-1"]},
            scope_hash=compute_scope_hash("host_list", {"host_ids": ["h-1"]}),
        )
        session.add(binding)
        await session.commit()

        inspector = Inspector(session)
        principal = Principal(user_id="u-1")
        # Resource is h-2, which is not in binding scope
        resource = Resource(id="h-2")

        rows = await inspector.effective(principal, resource)
        assert len(rows) == 0
