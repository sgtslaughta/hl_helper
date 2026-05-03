"""Tests for target selector resolution."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.dispatcher.targets import (
    GroupSelector,
    HostListSelector,
    MixedSelector,
    TagSelector,
    resolve_targets,
)
from server.app.models import Group, GroupMembership, Host


@pytest.mark.asyncio
async def test_host_list_selector_filters_to_existing(
    sm: async_sessionmaker,
) -> None:
    """Only known host_ids returned."""
    async with sm() as session:
        # Create two hosts
        h1 = Host(id="host-1", hostname="web1", agent_pubkey=b"key1")
        h2 = Host(id="host-2", hostname="web2", agent_pubkey=b"key2")
        session.add_all([h1, h2])
        await session.commit()

    async with sm() as session:
        # Request host-1, host-2, and non-existent host-3
        selector = HostListSelector(host_ids=["host-1", "host-2", "host-3"])
        result = await resolve_targets(session, selector)

        # Only existing hosts returned, sorted
        assert result == ["host-1", "host-2"]


@pytest.mark.asyncio
async def test_group_selector_with_subgroups(
    sm: async_sessionmaker,
) -> None:
    """A→B→C tree; selecting A returns hosts in A,B,C."""
    async with sm() as session:
        # Create hierarchy: A -> B -> C
        from uuid import uuid4

        a_id = uuid4()
        b_id = uuid4()
        c_id = uuid4()

        group_a = Group(id=a_id, name="group-a", parent_id=None)
        group_b = Group(id=b_id, name="group-b", parent_id=a_id)
        group_c = Group(id=c_id, name="group-c", parent_id=b_id)

        h1 = Host(id="host-1", hostname="web1", agent_pubkey=b"key1")
        h2 = Host(id="host-2", hostname="web2", agent_pubkey=b"key2")
        h3 = Host(id="host-3", hostname="web3", agent_pubkey=b"key3")

        session.add_all([group_a, group_b, group_c, h1, h2, h3])
        await session.flush()

        # Add memberships: h1 in A, h2 in B, h3 in C
        m1 = GroupMembership(host_id="host-1", group_id=a_id)
        m2 = GroupMembership(host_id="host-2", group_id=b_id)
        m3 = GroupMembership(host_id="host-3", group_id=c_id)
        session.add_all([m1, m2, m3])
        await session.commit()

    async with sm() as session:
        # Select group A with subgroups
        selector = GroupSelector(group_id=str(a_id), include_subgroups=True)
        result = await resolve_targets(session, selector)

        # Should get all three hosts
        assert sorted(result) == ["host-1", "host-2", "host-3"]


@pytest.mark.asyncio
async def test_group_selector_without_subgroups(
    sm: async_sessionmaker,
) -> None:
    """Only root group members returned."""
    async with sm() as session:
        from uuid import uuid4

        a_id = uuid4()
        b_id = uuid4()

        group_a = Group(id=a_id, name="group-a", parent_id=None)
        group_b = Group(id=b_id, name="group-b", parent_id=a_id)

        h1 = Host(id="host-1", hostname="web1", agent_pubkey=b"key1")
        h2 = Host(id="host-2", hostname="web2", agent_pubkey=b"key2")

        session.add_all([group_a, group_b, h1, h2])
        await session.flush()

        m1 = GroupMembership(host_id="host-1", group_id=a_id)
        m2 = GroupMembership(host_id="host-2", group_id=b_id)
        session.add_all([m1, m2])
        await session.commit()

    async with sm() as session:
        # Select group A WITHOUT subgroups
        selector = GroupSelector(group_id=str(a_id), include_subgroups=False)
        result = await resolve_targets(session, selector)

        # Only host-1 in group A
        assert result == ["host-1"]


@pytest.mark.asyncio
async def test_tag_selector(
    sm: async_sessionmaker,
) -> None:
    """Host with labels={"env": "prod"} matches."""
    async with sm() as session:
        h1 = Host(
            id="host-1",
            hostname="prod-web",
            agent_pubkey=b"key1",
            labels={"env": "prod"},
        )
        h2 = Host(
            id="host-2",
            hostname="dev-web",
            agent_pubkey=b"key2",
            labels={"env": "dev"},
        )
        h3 = Host(
            id="host-3",
            hostname="no-label",
            agent_pubkey=b"key3",
            labels={},
        )
        session.add_all([h1, h2, h3])
        await session.commit()

    async with sm() as session:
        selector = TagSelector(key="env", value="prod")
        result = await resolve_targets(session, selector)

        assert result == ["host-1"]


@pytest.mark.asyncio
async def test_mixed_selector_dedupes(
    sm: async_sessionmaker,
) -> None:
    """Overlapping selectors yield each host once."""
    async with sm() as session:
        from uuid import uuid4

        group_id = uuid4()
        group = Group(id=group_id, name="prod-group", parent_id=None)

        h1 = Host(
            id="host-1",
            hostname="prod-1",
            agent_pubkey=b"key1",
            labels={"env": "prod"},
        )
        h2 = Host(
            id="host-2",
            hostname="prod-2",
            agent_pubkey=b"key2",
            labels={"env": "prod"},
        )

        session.add_all([group, h1, h2])
        await session.flush()

        # Both hosts in group and both match tag
        m1 = GroupMembership(host_id="host-1", group_id=group_id)
        m2 = GroupMembership(host_id="host-2", group_id=group_id)
        session.add_all([m1, m2])
        await session.commit()

    async with sm() as session:
        # Mixed selector: both group AND tag (overlapping)
        selector = MixedSelector(
            selectors=[
                GroupSelector(group_id=str(group_id), include_subgroups=False),
                TagSelector(key="env", value="prod"),
            ]
        )
        result = await resolve_targets(session, selector)

        # Each host appears once, sorted
        assert result == ["host-1", "host-2"]


def test_unknown_selector_raises_typeerror() -> None:
    """Non-dataclass passed to resolve_targets raises TypeError."""
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from server.app.models.base import Base

    async def run_test() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with sm() as session:
            with pytest.raises(TypeError, match="unknown selector"):
                await resolve_targets(session, "not-a-selector")

        await engine.dispose()

    asyncio.run(run_test())


@pytest.mark.asyncio
async def test_nested_mixed_selector(
    sm: async_sessionmaker,
) -> None:
    """MixedSelector containing another MixedSelector resolves correctly."""
    async with sm() as session:
        h1 = Host(id="host-1", hostname="web1", agent_pubkey=b"key1")
        h2 = Host(id="host-2", hostname="web2", agent_pubkey=b"key2")
        h3 = Host(id="host-3", hostname="web3", agent_pubkey=b"key3")
        session.add_all([h1, h2, h3])
        await session.commit()

    async with sm() as session:
        # Nested structure: outer MixedSelector contains inner MixedSelector + HostListSelector
        inner = MixedSelector(
            selectors=[
                HostListSelector(host_ids=["host-1"]),
                HostListSelector(host_ids=["host-2"]),
            ]
        )
        outer = MixedSelector(
            selectors=[
                inner,
                HostListSelector(host_ids=["host-3"]),
            ]
        )
        result = await resolve_targets(session, outer)

        assert result == ["host-1", "host-2", "host-3"]


@pytest.mark.asyncio
async def test_group_diamond_hierarchy(
    sm: async_sessionmaker,
) -> None:
    """Diamond graph A→B,A→C,B→D,C→D; selecting A returns A,B,C,D (deduped)."""
    async with sm() as session:
        from uuid import uuid4

        a_id = uuid4()
        b_id = uuid4()
        c_id = uuid4()
        d_id = uuid4()

        group_a = Group(id=a_id, name="group-a", parent_id=None)
        group_b = Group(id=b_id, name="group-b", parent_id=a_id)
        group_c = Group(id=c_id, name="group-c", parent_id=a_id)
        group_d = Group(id=d_id, name="group-d", parent_id=None)

        h_a = Host(id="host-a", hostname="in-a", agent_pubkey=b"key-a")
        h_b = Host(id="host-b", hostname="in-b", agent_pubkey=b"key-b")
        h_c = Host(id="host-c", hostname="in-c", agent_pubkey=b"key-c")
        h_d = Host(id="host-d", hostname="in-d", agent_pubkey=b"key-d")

        session.add_all([group_a, group_b, group_c, group_d, h_a, h_b, h_c, h_d])
        await session.flush()

        # B and C both point to D (diamond)
        group_b.parent_id = a_id
        group_c.parent_id = a_id
        # Now manually add D as child to both B and C; use intermediate update
        b_to_d = Group(id=uuid4(), name="group-bd", parent_id=b_id)
        c_to_d = Group(id=uuid4(), name="group-cd", parent_id=c_id)
        session.add_all([b_to_d, c_to_d])
        await session.flush()

        # Memberships: h_a in A, h_b in B, h_c in C, h_d in both bd and cd
        m_a = GroupMembership(host_id="host-a", group_id=a_id)
        m_b = GroupMembership(host_id="host-b", group_id=b_id)
        m_c = GroupMembership(host_id="host-c", group_id=c_id)
        m_d1 = GroupMembership(host_id="host-d", group_id=b_to_d.id)
        m_d2 = GroupMembership(host_id="host-d", group_id=c_to_d.id)
        session.add_all([m_a, m_b, m_c, m_d1, m_d2])
        await session.commit()

    async with sm() as session:
        selector = GroupSelector(group_id=str(a_id), include_subgroups=True)
        result = await resolve_targets(session, selector)

        # Should return hosts a, b, c, d; deduped and sorted
        assert result == ["host-a", "host-b", "host-c", "host-d"]
