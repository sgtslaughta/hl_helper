"""RBAC permission catalog.

Source of truth for the canonical permission list used by built-in roles,
the decision engine, and the inspector.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    name: str
    category: str
    high_risk: bool = False
    description: str = ""


CATALOG: tuple[Permission, ...] = (
    Permission("host:read", "host", description="View host metadata"),
    Permission("host:write", "host", description="Edit tags, group, notes"),
    Permission("host:exec", "host", high_risk=True, description="Run shell commands on host"),
    Permission("host:reboot", "power", high_risk=True),
    Permission("host:shutdown", "power", high_risk=True),
    Permission("host:enroll", "host"),
    Permission("host:revoke", "host", high_risk=True),
    Permission("host:terminal", "host", high_risk=True),
    Permission("host:file_transfer", "host"),
    Permission("group:read", "group"),
    Permission("group:write", "group"),
    Permission("group:assign", "group"),
    Permission("task:read", "task"),
    Permission("task:create", "task"),
    Permission("task:cancel", "task"),
    Permission("task:approve", "task", high_risk=True),
    Permission("update:read", "update"),
    Permission("update:trigger", "update"),
    Permission("update:approve", "update", high_risk=True),
    Permission("update:policy_write", "update"),
    Permission("container:read", "container"),
    Permission("container:update", "container"),
    Permission("container:exec", "container", high_risk=True),
    Permission("container:policy_write", "container"),
    Permission("container:registry_write", "container"),
    Permission("secret:read", "secret"),
    Permission("secret:write", "secret", high_risk=True),
    Permission("secret:rotate", "secret", high_risk=True),
    Permission("plugin:read", "plugin"),
    Permission("plugin:install", "plugin", high_risk=True),
    Permission("plugin:configure", "plugin"),
    Permission("plugin:invoke", "plugin"),
    Permission("user:read", "user"),
    Permission("user:write", "user"),
    Permission("user:impersonate", "user", high_risk=True),
    Permission("role:read", "role"),
    Permission("role:write", "role", high_risk=True),
    Permission("audit:read", "audit"),
    Permission("audit:export", "audit"),
    Permission("audit:verify", "audit"),
    Permission("setting:read", "setting"),
    Permission("setting:write", "setting", high_risk=True),
    Permission("notification:read", "notification"),
    Permission("notification:write", "notification"),
    Permission("notification:test", "notification"),
    Permission("webhook:read", "webhook"),
    Permission("webhook:write", "webhook"),
    Permission("webhook:trigger", "webhook"),
    Permission("power:wol", "power"),
    Permission("power:event_subscribe", "power"),
    Permission("session:read", "session"),
    Permission("session:terminate", "session", high_risk=True),
    Permission("session:record_view", "session"),
    Permission("integration:read", "integration"),
    Permission("integration:write", "integration"),
    Permission("events:subscribe", "events"),
)


class Catalog:
    """Canonical view of CATALOG with lookup helpers."""

    VERSION = 1

    def __init__(self, perms: tuple[Permission, ...] = CATALOG) -> None:
        self._by_name: dict[str, Permission] = {p.name: p for p in perms}

    @classmethod
    def load(cls) -> "Catalog":
        return cls()

    def category(self, perm: str) -> str:
        return self._by_name[perm].category

    def is_high_risk(self, perm: str) -> bool:
        return self._by_name[perm].high_risk

    @property
    def permissions(self) -> set[str]:
        return set(self._by_name.keys())
