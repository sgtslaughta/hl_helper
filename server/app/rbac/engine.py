"""Built-in PolicyDecisionProvider implementation backed by Bindings + Roles."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models import Binding, Role
from server.app.rbac.provider import Principal, AuthContext, Decision
from server.app.rbac.scope import Resource, Scope


class BuiltinEngine:
    """In-process PDP: walk bindings, check role grants action, scope covers resource."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def is_authorized(
        self,
        principal: Principal,
        action: str,
        resource: Resource,
        ctx: AuthContext,
        /,
    ) -> Decision:
        # Collect candidate principal identities (user_id and user_group_ids).
        principal_filters = []
        if principal.user_id:
            principal_filters.append((Binding.principal_type == "user") & (Binding.principal_id == principal.user_id))
        if principal.service_account_id:
            principal_filters.append((Binding.principal_type == "service_account") & (Binding.principal_id == principal.service_account_id))
        for gid in principal.user_group_ids:
            principal_filters.append((Binding.principal_type == "user_group") & (Binding.principal_id == gid))
        if not principal_filters:
            return Decision(allow=False, reason="no_principal_identity")

        bindings_q = (
            select(Binding, Role)
            .join(Role, Role.id == Binding.role_id)
            .where(or_(*principal_filters))
        )
        rows = (await self._s.execute(bindings_q)).all()

        for binding, role in rows:
            perms = set(role.permissions or [])
            if action not in perms:
                continue
            scope = Scope(kind=binding.scope_kind, value=binding.scope_value or {})
            # TODO: full group hierarchy traversal (deferred to T2.3)
            if scope.covers(resource, descendants_of=lambda gid: frozenset({gid})):
                return Decision(allow=True, binding_id=binding.id, reason=f"role:{role.name}")

        return Decision(allow=False, reason="no_matching_binding")
