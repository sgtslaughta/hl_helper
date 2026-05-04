"""PolicyDecisionProvider Protocol + supporting types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from server.app.rbac.scope import Resource


@dataclass(frozen=True)
class Principal:
    user_id: str | None = None
    service_account_id: str | None = None
    user_group_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AuthContext:
    """Per-request context that informs authorization (mfa, ip, time).

    enforce_mfa: when True, engine MUST deny high_risk perms unless mfa_satisfied.
    Defaults False so internal callers (dispatcher, system tasks) preserve
    current behavior; API trust boundaries set True.
    """
    mfa_satisfied: bool = False
    source_ip: str | None = None
    enforce_mfa: bool = False

    @classmethod
    def empty(cls) -> "AuthContext":
        return cls()


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str | None = None
    binding_id: str | None = None  # which binding granted (for audit)


@dataclass(frozen=True)
class GlobalResource:
    """Sentinel resource for collection-level checks (only `global` scope covers it)."""

    @property
    def as_resource(self) -> Resource:
        return Resource()


class PolicyDecisionProvider(Protocol):
    async def is_authorized(
        self,
        principal: Principal,
        action: str,
        resource: Resource,
        ctx: AuthContext,
        /,
    ) -> Decision: ...
