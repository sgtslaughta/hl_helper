"""Resolve a target selector to a concrete list of host IDs."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models import Group, GroupMembership, Host


@dataclass(frozen=True)
class GroupSelector:
    group_id: str | UUID
    include_subgroups: bool = True


@dataclass(frozen=True)
class TagSelector:
    key: str
    value: str


@dataclass(frozen=True)
class HostListSelector:
    host_ids: list[str]


@dataclass(frozen=True)
class MixedSelector:
    selectors: list["GroupSelector | TagSelector | HostListSelector"]


Selector = GroupSelector | TagSelector | HostListSelector | MixedSelector


async def resolve_targets(session: AsyncSession, sel: Selector) -> list[str]:
    """Return the unique sorted list of host_ids matching the selector."""
    if isinstance(sel, HostListSelector):
        rows = (
            await session.execute(
                select(Host.id).where(Host.id.in_(sel.host_ids))
            )
        ).scalars().all()
        return sorted(set(rows))
    if isinstance(sel, GroupSelector):
        group_id = (
            UUID(sel.group_id)
            if isinstance(sel.group_id, str)
            else sel.group_id
        )
        group_ids = await _expand_group(
            session, group_id, sel.include_subgroups
        )
        rows = (
            await session.execute(
                select(GroupMembership.host_id).where(
                    GroupMembership.group_id.in_(group_ids)
                )
            )
        ).scalars().all()
        return sorted(set(rows))
    if isinstance(sel, TagSelector):
        # Host.labels is JSON dict; SQLite/Postgres JSON-extract differs. For now,
        # naive: load all hosts, filter in Python. Document as N+1 / scan.
        # TODO(perf): use JSON1 extension on SQLite + jsonb path on Postgres for
        # an indexed expression.
        hosts = (await session.execute(select(Host))).scalars().all()
        return sorted(
            {
                h.id
                for h in hosts
                if isinstance(h.labels, dict) and h.labels.get(sel.key) == sel.value
            }
        )
    if isinstance(sel, MixedSelector):
        out: set[str] = set()
        for child in sel.selectors:
            out.update(await resolve_targets(session, child))
        return sorted(out)
    raise TypeError(f"unknown selector: {type(sel).__name__}")


async def _expand_group(
    session: AsyncSession, group_id: UUID, include_subgroups: bool
) -> set[UUID]:
    """Expand a group to include all subgroups if include_subgroups is True."""
    if not include_subgroups:
        return {group_id}
    # BFS over Group.parent_id pointing UP from children. Children of group_id
    # are rows where Group.parent_id == group_id.
    out: set[UUID] = {group_id}
    frontier: set[UUID] = {group_id}
    while frontier:
        rows = (
            await session.execute(
                select(Group.id).where(Group.parent_id.in_(frontier))
            )
        ).scalars().all()
        new = set(rows) - out
        if not new:
            break
        out |= new
        frontier = new
    return out
