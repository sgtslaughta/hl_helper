"""Built-in PolicyDecisionProvider implementation backed by Bindings + Roles."""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models import Binding, Role
from server.app.rbac.provider import Principal, AuthContext, Decision
from server.app.rbac.scope import Resource, Scope


def _principal_filters(principal: Principal) -> list[Any]:
    """Build list of SQLAlchemy filters for the given principal's identities."""
    out: list[Any] = []
    if principal.user_id:
        out.append(and_(Binding.principal_type == "user", Binding.principal_id == principal.user_id))
    if principal.service_account_id:
        out.append(and_(Binding.principal_type == "service_account", Binding.principal_id == principal.service_account_id))
    for gid in principal.user_group_ids:
        out.append(and_(Binding.principal_type == "user_group", Binding.principal_id == gid))
    return out


class BuiltinEngine:
    """In-process PDP: walk bindings, check role grants action, scope covers resource."""

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

    async def is_authorized(
        self,
        principal: Principal,
        action: str,
        resource: Resource,
        ctx: AuthContext,
        /,
    ) -> Decision:
        # Collect candidate principal identities (user_id and user_group_ids).
        principal_filters = _principal_filters(principal)
        if not principal_filters:
            return Decision(allow=False, reason="no_principal_identity")

        # Load group hierarchy once per authorization check
        if self._group_hierarchy is None:
            self._group_hierarchy = await self._build_group_hierarchy()

        bindings_q = (
            select(Binding, Role)
            .join(Role, Role.id == Binding.role_id)
            .where(or_(*principal_filters))
        )
        rows = (await self._s.execute(bindings_q)).all()

        # TODO: check ctx.mfa_satisfied for step-up enforcement on high-risk actions (Phase 6)
        for binding, role in rows:
            perms = set(role.permissions or [])
            if action not in perms:
                continue
            scope = Scope(kind=binding.scope_kind, value=binding.scope_value or {})
            # Use pre-loaded hierarchy for efficient descendant lookup
            def descendants_fn(gid: str) -> frozenset[str]:
                return self._group_hierarchy.get(gid, frozenset({gid}))  # type: ignore
            if scope.covers(resource, descendants_of=descendants_fn):
                return Decision(allow=True, binding_id=binding.id, reason=f"role:{role.name}")

        return Decision(allow=False, reason="no_matching_binding")
