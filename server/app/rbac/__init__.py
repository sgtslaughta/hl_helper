"""RBAC subsystem: catalog, scope evaluator, decision provider, approvals."""
from server.app.rbac.catalog import Catalog, CATALOG, Permission
from server.app.rbac.scope import Scope, Resource, ScopeKind
from server.app.rbac.provider import (
    Principal, AuthContext, Decision, GlobalResource, PolicyDecisionProvider,
)
from server.app.rbac.engine import BuiltinEngine
from server.app.rbac.inspector import Inspector, EffectivePermissionRow
from server.app.rbac.approvals import ApprovalEngine, DecisionResult
from server.app.rbac.roles import (
    BUILTIN_ROLES, VIEWER_PERMS, OPERATOR_PERMS, ADMIN_PERMS, OWNER_PERMS,
)

__all__ = [
    "Catalog", "CATALOG", "Permission",
    "Scope", "Resource", "ScopeKind",
    "Principal", "AuthContext", "Decision", "GlobalResource", "PolicyDecisionProvider",
    "BuiltinEngine",
    "Inspector", "EffectivePermissionRow",
    "ApprovalEngine", "DecisionResult",
    "BUILTIN_ROLES", "VIEWER_PERMS", "OPERATOR_PERMS", "ADMIN_PERMS", "OWNER_PERMS",
]
