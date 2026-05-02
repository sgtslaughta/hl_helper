"""Built-in role permission sets, importable for in-process checks.

This is a *Python copy* of the role permission tuples seeded by migration
0005_roles. Tests verify the two stay in sync (test_roles.py).
"""
from __future__ import annotations

from server.app.rbac.catalog import CATALOG


def _all() -> set[str]:
    return {p.name for p in CATALOG}


VIEWER_PERMS: frozenset[str] = frozenset({p.name for p in CATALOG if p.name.endswith(":read")})

OPERATOR_PERMS: frozenset[str] = VIEWER_PERMS | frozenset({
    "host:exec", "host:terminal", "host:file_transfer",
    "task:create", "task:cancel", "update:trigger",
    "container:update", "events:subscribe", "audit:read",
})

ADMIN_PERMS: frozenset[str] = frozenset(_all() - {"user:impersonate"})

OWNER_PERMS: frozenset[str] = frozenset(_all())

BUILTIN_ROLES: dict[str, frozenset[str]] = {
    "viewer": VIEWER_PERMS,
    "operator": OPERATOR_PERMS,
    "admin": ADMIN_PERMS,
    "owner": OWNER_PERMS,
}
