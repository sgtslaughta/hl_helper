"""Tests for Group and GroupMembership models."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.models import Group, GroupMembership, Host


@pytest.mark.asyncio
async def test_create_group_hierarchy_and_membership(sm: async_sessionmaker) -> None:
    """Create hierarchical groups and add host membership to child group."""
    async with sm() as session:
        root = Group(name="prod")
        session.add(root)
        await session.flush()

        child = Group(name="prod.web", parent_id=root.id)
        session.add(child)
        await session.flush()

        host = Host(id="h-1", hostname="test", agent_pubkey=b"\x00" * 32)
        session.add(host)
        await session.flush()

        session.add(GroupMembership(host_id=host.id, group_id=child.id, kind="static"))
        await session.commit()

        fetched = await session.scalar(select(Host).where(Host.id == "h-1"))
        await session.refresh(fetched, ["memberships"])

        assert child.id in {m.group_id for m in fetched.memberships}
