---
title: Role-Based Access Control (RBAC)
status: stable
---

# Role-Based Access Control (RBAC)

RBAC in hl_helper enforces "who can do what" via role assignments, permission scopes, and optional approval gates. The model is flexible, audit-logged, and integrable with external policy engines via a Cedar plugin hook.

---

## Permission Model

### Permission Format

Permissions are `category:action` strings. Examples:
- `host:read` — view host metadata
- `host:exec` — run shell commands on host (high-risk)
- `secret:write` — write/store secrets

The canonical catalog is in `server/app/rbac/catalog.py` as a tuple of `Permission` dataclasses.

### Categories

Extracted from the catalog (see [Code Reference](#code-reference)):

| Category | Permissions | Notes |
|---|---|---|
| `host` | read, write, exec, enroll, revoke, terminal, file_transfer | Execution is high-risk |
| `power` | reboot, shutdown, wol, event_subscribe | Destructive operations |
| `group` | read, write, assign | Host grouping and labels |
| `task` | read, create, cancel, approve | Task execution and approval |
| `update` | read, trigger, approve, policy_write | Package/config updates |
| `container` | read, update, exec, policy_write, registry_write | Container lifecycle |
| `secret` | read, write, rotate | Secrets broker access |
| `plugin` | read, install, enable, manage, configure, invoke | Plugin marketplace and lifecycle |
| `user` | read, write, impersonate | User management |
| `role` | read, write | Custom role creation |
| `audit` | read, export, verify | Audit log access |
| `setting` | read, write | Server configuration |
| `notification` | read, write, test | Notification channels |
| `webhook` | read, write, trigger | Webhook management |
| `session` | read, terminate, record_view | Session/login audit |
| `integration` | read, write | Third-party integrations |
| `events` | subscribe | Event stream access |
| `docs` | read | Embedded wiki access |

### High-Risk Permissions

Permissions marked `high_risk=True` in the catalog are:

`host:exec`, `host:reboot`, `host:shutdown`, `host:revoke`, `host:terminal`, `task:approve`, `update:approve`, `container:exec`, `plugin:install`, `plugin:enable`, `plugin:manage`, `secret:write`, `secret:rotate`, `user:impersonate`, `role:write`, `session:terminate`, `setting:write`

High-risk operations trigger:
- **MFA step-up** (user must authenticate ≤ 5 minutes before operation).
- **Approval gates** (optional per-role; if enabled, operation is queued for approval by `role:write` admin).
- **Audit with extra detail** (include actor, IP, device fingerprint, outcome).

---

## Built-In Roles

### Roles

| Role | Permissions | Use Case |
|---|---|---|
| `viewer` | All `:read` permissions | Read-only access; suitable for monitoring/compliance teams |
| `operator` | `viewer` + exec, task:create, task:cancel, update:trigger, container:update, events:subscribe, audit:read | Day-to-day operations; can run commands and trigger updates |
| `admin` | All permissions except `user:impersonate` | Administrative access; cannot impersonate other users (super-admin gate) |
| `owner` | All permissions including `user:impersonate` | Founder/owner-level access; dangerous operations require extra confirmation |

### Automatic `:read` Inclusion

Granting any `X:action` permission automatically includes `X:read`. For example, `host:write` implies `host:read`. This avoids redundant grants in custom roles.

---

## Custom Roles

### Creation & Validation

Admins can create custom roles via `POST /v1/rbac/roles` with:

```json
{
  "name": "backup-operator",
  "description": "Can read hosts, trigger backups, view audit",
  "permissions": [
    "host:read",
    "update:trigger",
    "audit:read"
  ]
}
```

**Validation**:
1. All permissions must exist in the canonical catalog.
2. Name must be unique (built-in role names reserved).
3. Description required (for audit clarity).
4. Permissions deduplicated (`:read` auto-inclusion not re-submitted).

### Persistence

Custom roles are stored in the `roles` table (seeded by migration, editable at runtime). Each role assignment references this table:

```
CREATE TABLE roles (
  id TEXT PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  description TEXT,
  permissions JSONB NOT NULL,  -- array of permission strings
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE user_role_assignments (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  role_id TEXT NOT NULL,
  scope TEXT,                  -- optional: "fleet-wide" or resource ID
  granted_by TEXT NOT NULL,
  granted_at TIMESTAMPTZ NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (role_id) REFERENCES roles(id),
  FOREIGN KEY (granted_by) REFERENCES users(id),
  UNIQUE (user_id, role_id, scope)
);
```

---

## Capability Tokens (Biscuit)

Biscuit tokens encode RBAC decisions and bind them to resources and time windows. The agent receives biscuits from the server; the biscuit verifies without server callback.

### Token Structure

A biscuit token for a host operation encodes:

```
issuer: server signing key
holder: agent public key
validity: now ≤ T ≤ now + 5 min (operation window)
claims:
  - actor: user_id
  - action: host:exec | host:reboot | etc.
  - resource: host_id (or "*" for all)
  - scope: "execute" | "read" | etc.
```

### Issuance

When an operator requests to run a command on a host:

1. Server checks RBAC: does user have `host:exec` + other needed perms?
2. Server generates biscuit with signed claims (issuer key).
3. Biscuit is returned in the command envelope (gRPC `CommandEnvelope`).
4. Agent verifies biscuit signature (pinned server public key).
5. Agent checks claims match request (action, resource, scope).
6. Agent executes if all checks pass.

### Verification Path

Agent-side (no server callback):
1. Extract biscuit from `CommandEnvelope`.
2. Verify signature with pinned server public key.
3. Check `validity` field: now() within window.
4. Check `action` matches command type.
5. Check `resource` matches target host_id (or is "*").
6. If all pass, execute; else reject with `PermissionDenied` error.

Server-side (audit):
1. Log successful biscuit verification in audit trail (low detail).
2. Log execution result (command output, side effects).

---

## Cedar Plugin Hook (Planned/Optional)

A future extension allows plugging in [Cedar](https://www.cedarpolicy.com/) for advanced attribute-based access control (ABAC). This is **optional** and **post-v1.0**.

### Hook Definition

```python
class CedarPolicyEngine(Protocol):
    async def is_authorized(
        self,
        principal: Principal,        # user_id + roles + context
        action: str,                 # category:action
        resource: Resource,          # host_id, group_id, etc.
        context: RequestContext,     # IP, time, device fingerprint, etc.
    ) -> AuthDecision:
        ...
```

### Usage

When enabled, RBAC check flow becomes:

1. Fast-path: Check if user has permission in canonical RBAC table.
2. If granted → allow.
3. If denied but Cedar enabled → call Cedar policy engine.
4. Cedar policy can grant/deny based on attributes (e.g., "allow host:exec only if host.label['env'] == 'staging'").
5. Final decision: fast-path OR Cedar grant = allow.

### Configuration

Disabled by default. Enable via `FLEET_CEDAR_POLICY_URL` pointing to a Cedar policy service. Policy written in Cedar language; server validates policy syntax at startup.

---

## Decision Engine

### RBACEngine

```python
class RBACEngine:
    def __init__(self, catalog: Catalog, roles_repo: RolesRepository):
        self.catalog = catalog
        self.roles_repo = roles_repo

    async def check(
        self,
        user_id: str,
        action: str,            # "host:exec"
        resource_id: str = None # "host_abc123"
    ) -> AuthDecision:
        """
        Returns: AuthDecision(allowed: bool, reason?: str, requires_mfa?: bool)
        """
```

**Flow**:
1. Load user's roles (via `user_role_assignments` table).
2. Compute effective permissions (union of all assigned roles).
3. Check if `action` in effective permissions.
4. If action is high-risk + MFA not recent → return `requires_mfa=True`.
5. Check approval gate policy (optional per role).
6. Return final decision.

---

## Scope (Multi-Tenancy & Resource Limits)

Roles can be scoped to specific resources. Example:

- User has `host:read` role scoped to `group:staging` → can read hosts in staging group only.
- User has `role:write` role scoped `fleet-wide` → can modify any role.

**Scope column** in `user_role_assignments` table:

```
scope: "fleet-wide" | "group:<group_id>" | "host:<host_id>" | "<resource_type>:<id>"
```

If scope is `fleet-wide`, permission applies globally. Otherwise, operations are filtered by scope at the API layer.

---

## Audit & Logging

Every permission check (allow or deny) is logged:

| Event | Payload | Detail |
|---|---|---|
| `rbac.check_allow` | `user_id`, `action`, `resource_id`, `scope`, `decided_by` (cache/cedar/role) | info |
| `rbac.check_deny` | `user_id`, `action`, `resource_id`, `reason`, `peer_ip` | warning |
| `rbac.check_requires_mfa` | `user_id`, `action`, `mfa_last_at` | info |
| `rbac.approval_required` | `user_id`, `action`, `resource_id`, `approval_policy_id` | info |
| `role.created` | `role_id`, `name`, `permissions`, `created_by` | info |
| `role.updated` | `role_id`, `permissions_before`, `permissions_after`, `updated_by` | info |
| `role.deleted` | `role_id`, `deleted_by` | info |
| `user.role_assigned` | `user_id`, `role_id`, `scope`, `granted_by` | info |
| `user.role_revoked` | `user_id`, `role_id`, `scope`, `revoked_by` | info |

---

## RBAC Matrix (Example)

Abbreviated matrix; full list in catalog:

|  | Viewer | Operator | Admin | Owner |
|---|---|---|---|---|
| **host:read** | ✓ | ✓ | ✓ | ✓ |
| **host:exec** | | ✓ | ✓ | ✓ |
| **host:revoke** | | | ✓ | ✓ |
| **secret:read** | | | ✓ | ✓ |
| **secret:write** | | | ✓ | ✓ |
| **user:write** | | | ✓ | ✓ |
| **role:write** | | | ✓ | ✓ |
| **user:impersonate** | | | | ✓ |
| **audit:read** | | ✓ | ✓ | ✓ |

---

## Code Reference

### Files

- `server/app/rbac/catalog.py` — Canonical permission list (`CATALOG` tuple).
- `server/app/rbac/roles.py` — Built-in role permission sets.
- `server/app/rbac/engine.py` — `RBACEngine` decision logic.
- `server/app/rbac/scope.py` — Scope enforcement helpers.
- `server/app/models/role.py` — `Role` and `UserRoleAssignment` ORM models.
- `server/app/api/v1/rbac.py` — REST endpoints (`GET /v1/rbac/roles`, `POST /v1/rbac/check`, etc.).

### Catalog Enum

Every permission in the catalog is exposed as a Python constant:

```python
from server.app.rbac.catalog import CATALOG

for perm in CATALOG:
    print(f"{perm.name} (category={perm.category}, high_risk={perm.high_risk})")
```

---

## Related

- [Threat Model](../secure-dev/threat-model.md) — RBAC mitigations
- [Agent Privilege Model](../secure-dev/agent-privilege-model.md) — Agent-side capability enforcement
- [Authentication](auth.md) — Session/user context
