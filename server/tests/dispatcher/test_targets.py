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
