"""Tests for Role and Binding models."""

from __future__ import annotations

import hashlib
import json
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.models import Role, Binding


@pytest.mark.asyncio
async def test_builtin_roles_seeded(sm: async_sessionmaker) -> None:
    """Verify that the four built-in roles are present."""
    async with sm() as session:
        rows = (await session.execute(select(Role).where(Role.built_in.is_(True)))).scalars().all()
        names = {r.name for r in rows}
        assert names == {"viewer", "operator", "admin", "owner"}


@pytest.mark.asyncio
async def test_role_hierarchy_subset(sm: async_sessionmaker) -> None:
    """Verify permission hierarchy: viewer ⊆ operator ⊆ admin ⊆ owner."""
    async with sm() as session:
        roles = {
            r.name: set(r.permissions)
            for r in (await session.execute(select(Role))).scalars().all()
            if r.built_in
        }
        assert roles["viewer"] <= roles["operator"]
        assert roles["operator"] <= roles["admin"]
        assert roles["admin"] <= roles["owner"]
        assert "user:impersonate" in roles["owner"]
        assert "user:impersonate" not in roles["admin"]


@pytest.mark.asyncio
async def test_binding_scope_hash_unique(sm: async_sessionmaker) -> None:
    """Verify unique constraint on (principal_type, principal_id, role_id, scope_hash)."""
    async with sm() as session:
        role = (await session.execute(select(Role).where(Role.name == "operator"))).scalar_one()
        scope_value = {"group_id": "g-1"}
        canon = json.dumps({"kind": "group", "value": scope_value}, sort_keys=True)
        h = hashlib.sha256(canon.encode()).hexdigest()
        b1 = Binding(
            id="b-1",
            principal_type="user",
            principal_id="u-1",
            role_id=role.id,
            scope_kind="group",
            scope_value=scope_value,
            scope_hash=h,
        )
        session.add(b1)
        await session.commit()
        # Same tuple → integrity error
        b2 = Binding(
            id="b-2",
            principal_type="user",
            principal_id="u-1",
            role_id=role.id,
            scope_kind="group",
            scope_value=scope_value,
            scope_hash=h,
        )
        session.add(b2)
        with pytest.raises(Exception):  # IntegrityError
            await session.commit()


@pytest.mark.asyncio
async def test_binding_global_scope(sm: async_sessionmaker) -> None:
    """Verify binding with global scope."""
    async with sm() as session:
        role = (await session.execute(select(Role).where(Role.name == "viewer"))).scalar_one()
        canon = json.dumps({"kind": "global", "value": {}}, sort_keys=True)
        h = hashlib.sha256(canon.encode()).hexdigest()
        b = Binding(
            id="b-3",
            principal_type="service_account",
            principal_id="sa-1",
            role_id=role.id,
            scope_kind="global",
            scope_value={},
            scope_hash=h,
        )
        session.add(b)
        await session.commit()
        got = await session.scalar(select(Binding).where(Binding.id == "b-3"))
        assert got.scope_kind == "global"
