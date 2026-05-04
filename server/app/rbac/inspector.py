"""Effective-permissions inspector: flat (action, source_binding_id) rows for a principal+resource."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models import Binding, Role
from server.app.rbac.provider import Principal
from server.app.rbac.scope import Resource, Scope
from server.app.rbac.engine import _principal_filters


@dataclass(frozen=True)
class EffectivePermissionRow:
    action: str
    source_binding_id: str
    role_name: str
    scope_kind: str
    scope_value: dict[str, object]


class Inspector:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._group_hierarchy: dict[str, frozenset[str]] | None = None

    async def _build_group_hierarchy(self) -> dict[str, frozenset[str]]:
        """Load full group hierarchy into memory for efficient lookup.

        Returns a dict mapping group_id (as string) to set of all descendants
        (including self).
        """
        from server.app.models import Group

        # Fetch all groups
        result = await self._s.execute(select(Group))
        all_groups = {str(g.id): g for g in result.scalars().all()}

        # Build reverse index: parent -> children
        children_map: dict[str, list[str]] = {}
        for gid, group in all_groups.items():
            if group.parent_id is not None:
                parent_id = str(group.parent_id)
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(gid)

        # Build descendants map via DFS from each group
        descendants_map: dict[str, frozenset[str]] = {}

        def dfs(gid: str) -> frozenset[str]:
            """DFS to compute all descendants (including self) of a group."""
            if gid in descendants_map:
                return descendants_map[gid]

            # Start with self
            result_set = {gid}

            # Add all children and their descendants
            for child_id in children_map.get(gid, []):
                result_set.update(dfs(child_id))

            descendants_map[gid] = frozenset(result_set)
            return descendants_map[gid]

        # Compute descendants for all groups
        for gid in all_groups:
            dfs(gid)

        return descendants_map

    async def effective(self, principal: Principal, resource: Resource) -> list[EffectivePermissionRow]:
        principal_filters = _principal_filters(principal)
        if not principal_filters:
            return []

        # Load group hierarchy once per call
        if self._group_hierarchy is None:
            self._group_hierarchy = await self._build_group_hierarchy()

        rows = (await self._s.execute(
            select(Binding, Role).join(Role, Role.id == Binding.role_id).where(or_(*principal_filters))
        )).all()

        out: list[EffectivePermissionRow] = []
        for binding, role in rows:
            scope = Scope(kind=binding.scope_kind, value=binding.scope_value or {})
            # Use pre-loaded hierarchy for efficient descendant lookup
            def descendants_fn(gid: str) -> frozenset[str]:
                return self._group_hierarchy.get(gid, frozenset({gid}))  # type: ignore
            if not scope.covers(resource, descendants_of=descendants_fn):
                continue
            for action in (role.permissions or []):
                out.append(EffectivePermissionRow(
                    action=action,
                    source_binding_id=binding.id,
                    role_name=role.name,
                    scope_kind=binding.scope_kind,
                    scope_value=binding.scope_value or {},
                ))
        return out
