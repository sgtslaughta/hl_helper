"""Effective-permissions inspector: flat (action, source_binding_id) rows for a principal+resource."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models import Binding, Role
from server.app.rbac.provider import Principal
from server.app.rbac.scope import Resource, Scope


@dataclass(frozen=True)
class EffectivePermissionRow:
    action: str
    source_binding_id: str
    role_name: str


class Inspector:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def effective(self, principal: Principal, resource: Resource) -> list[EffectivePermissionRow]:
        principal_filters = []
        if principal.user_id:
            principal_filters.append((Binding.principal_type == "user") & (Binding.principal_id == principal.user_id))
        if principal.service_account_id:
            principal_filters.append((Binding.principal_type == "service_account") & (Binding.principal_id == principal.service_account_id))
        for gid in principal.user_group_ids:
            principal_filters.append((Binding.principal_type == "user_group") & (Binding.principal_id == gid))
        if not principal_filters:
            return []

        rows = (await self._s.execute(
            select(Binding, Role).join(Role, Role.id == Binding.role_id).where(or_(*principal_filters))
        )).all()

        out: list[EffectivePermissionRow] = []
        for binding, role in rows:
            scope = Scope(kind=binding.scope_kind, value=binding.scope_value or {})
            # TODO: full group hierarchy traversal (deferred to T2.3)
            if not scope.covers(resource, descendants_of=lambda gid: frozenset({gid})):
                continue
            for action in (role.permissions or []):
                out.append(EffectivePermissionRow(
                    action=action, source_binding_id=binding.id, role_name=role.name,
                ))
        return out
