---
title: Cedar Policies in hl_helper
status: partial
---

# Cedar Policies in hl_helper

This page explains how hl_helper implements RBAC and introduces Cedar, an optional advanced policy engine for complex access control scenarios.

## Built-In RBAC Roles

hl_helper ships with four standard roles that cover most use cases:

| Role | Use Case | Key Permissions |
|---|---|---|
| **Viewer** | Read-only access for monitoring and compliance | `*:read` (all resources, read-only) |
| **Operator** | Day-to-day operations | `host:read`, `host:exec`, `task:create`, `update:trigger`, `audit:read`, `events:subscribe` |
| **Admin** | Administrative access (all except impersonation) | All permissions except `user:impersonate` |
| **Owner** | Founder/owner level (highest privileges) | All permissions including `user:impersonate` |

### Permission Categories

Permissions are organized by resource category. Here's a summary:

| Category | Permissions | Risk Level |
|---|---|---|
| **host** | read, write, exec, enroll, revoke, terminal, file_transfer | High (exec, revoke) |
| **power** | reboot, shutdown, wol, event_subscribe | High (destructive) |
| **secret** | read, write, rotate | High (write, rotate) |
| **user** | read, write, impersonate | High (write, impersonate) |
| **role** | read, write | High (write) |
| **task** | read, create, cancel, approve | Medium (approve) |
| **update** | read, trigger, approve, policy_write | Medium (trigger, approve) |
| **audit** | read, export, verify | Low (read-only) |
| **group** | read, write, assign | Medium (assign) |
| **plugin** | read, install, enable, manage, configure, invoke | High (install, manage) |

### Example Assignments

Alice (founder):
```
Alice → Owner role (fleet-wide)
```

Bob (ops engineer):
```
Bob → Operator role (fleet-wide)
```

Charlie (contractor):
```
Charlie → Viewer role (fleet-wide)
```

## High-Risk Permissions

Permissions marked as high-risk require extra confirmation:

`host:exec`, `host:revoke`, `host:reboot`, `host:shutdown`, `host:terminal`, `task:approve`, `update:approve`, `secret:write`, `secret:rotate`, `user:write`, `user:impersonate`, `role:write`, `plugin:install`, `plugin:manage`, `session:terminate`, `setting:write`

When a high-risk permission is used:

1. **MFA step-up**: If the user's last MFA authentication was more than 5 minutes ago, prompt them to authenticate again.
2. **Audit log extra detail**: Include IP address, device fingerprint, HTTP user-agent.
3. **Optional approval gate** (if enabled): The operation is queued for approval by another admin.

## Capability Tokens (Biscuit)

Commands sent to agents are wrapped in **capability tokens** (using the Biscuit format). Each token encodes:

```
Issuer: server's signing key
Holder: the agent
Validity: 5 minutes from now
Claims:
  - action: host:exec | host:reboot | etc.
  - resource: host_id (which host)
  - scope: what the command can do
  - actor: which user requested it
```

### Example: Running a Command on a Host

1. User (Alice) requests: "Run `apt update` on host_prod_01"
2. hl_helper checks: "Does Alice have `host:exec`?" → Yes (she's Owner).
3. hl_helper generates a biscuit:
   ```
   {
     "issuer": "server_signing_key",
     "action": "host:exec",
     "resource": "host_prod_01",
     "actor": "alice",
     "expires_at": "now + 5 minutes"
   }
   Signed: <ed25519 signature>
   ```
4. The biscuit is sent to the agent in the command envelope.
5. The agent verifies:
   - The signature is valid (server's key).
   - The expiry hasn't passed.
   - The action matches the request (host:exec).
   - The resource matches the target host (host_prod_01).
6. If all checks pass, the agent executes. If any check fails, the agent rejects with "PermissionDenied."

### Why Biscuits?

Biscuits allow the agent to verify permissions *without calling the server*. Advantages:

- **Offline operation**: If the agent can't reach the server temporarily, in-flight commands still execute.
- **No permission callback**: The agent doesn't ask the server "is Alice allowed to run this?" The answer is already in the token.
- **Tamper-proof**: Signature prevents the agent (if compromised) from forging permissions.

## Cedar Plugin (Planned/Optional)

Cedar is an open-source language for writing access control policies. It's planned for hl_helper but not yet shipped.

### When You Might Need Cedar

Built-in RBAC covers most cases. But sometimes you need more complex rules:

**Example 1: Time-based access**

```cedar
permit(principal, action, resource)
if principal.department == "ops"
   && action == "host:exec"
   && resource.environment == "staging"
   && request.time.hour >= 9 && request.time.hour < 17;
```

This rule means: "Ops team can exec on staging hosts during business hours only."

**Example 2: Attribute-based access**

```cedar
permit(principal, action, resource)
if principal.clearance_level >= resource.required_clearance
   && (resource.owner == principal || principal.role == "admin");
```

This rule means: "Access is allowed if the principal's clearance is high enough AND they're either the owner or an admin."

**Example 3: Geo-fencing**

```cedar
permit(principal, action, resource)
if principal.office_location == resource.location
   || principal.role == "admin";
```

This rule means: "Access is allowed if the principal is in the same office as the resource, or if they're an admin."

### Cedar Configuration (Planned)

When Cedar is enabled (planned feature):

1. The admin writes a `.cedar` policy file:
   ```cedar
   // /etc/hlhelper/policies.cedar
   permit(principal, action, resource)
   if principal.role == "admin";
   
   permit(principal, action, resource)
   if principal.role == "operator"
      && action == "host:exec"
      && resource.environment == "staging";
   ```

2. The policy is loaded on server startup:
   ```bash
   export HL_CEDAR_POLICY_FILE="/etc/hlhelper/policies.cedar"
   ./hl-helper server
   ```

3. On each permission check, the decision flow is:

   a. Fast-path: Check built-in RBAC (does the user's role have the permission?).
   b. If granted → allow.
   c. If denied → check Cedar policies.
   d. If Cedar allows → allow.
   e. Otherwise → deny.

This means Cedar is a supplement to RBAC, not a replacement.

### Cedar Syntax (Light Example)

```cedar
// Viewer role: read everything
permit(principal, action, resource)
if principal.role == "viewer"
   && action like ".*:read";

// Operator role: exec on hosts
permit(principal, action, resource)
if principal.role == "operator"
   && action == "host:exec";

// Admin role: everything
permit(principal, action, resource)
if principal.role == "admin";

// Deny: no one can impersonate except owner
deny(principal, action, resource)
if action == "user:impersonate"
   && principal.role != "owner";
```

## Audit Logging of Access Checks

Every permission decision is logged:

```json
{
  "event": "rbac.check_allow",
  "timestamp": "2025-05-09T14:23:45Z",
  "user_id": "alice",
  "action": "host:exec",
  "resource_id": "host_prod_01",
  "role": "owner",
  "decided_by": "rbac"
}
```

And denials:

```json
{
  "event": "rbac.check_deny",
  "timestamp": "2025-05-09T14:23:46Z",
  "user_id": "bob",
  "action": "user:write",
  "resource_id": null,
  "role": "operator",
  "reason": "operator role does not have permission user:write",
  "peer_ip": "192.168.1.100"
}
```

You can query these logs to:
- Audit who did what (compliance).
- Detect unauthorized access attempts.
- Investigate incidents ("Who tried to delete the database?").

## Scope: Resource-Level Access

Roles can be scoped to specific resources or groups. Example:

```
Alice → Admin role (fleet-wide)        # All permissions, all resources
Bob → Operator role (group:staging)    # Operator permissions, staging hosts only
Charlie → Viewer role (host:backup01)  # View only, one specific host
```

Scoped roles are useful for:
- **Multi-tenant environments**: Each tenant operator can only see their hosts.
- **Blast radius limitation**: A contractor can only access staging, not production.
- **Compliance**: Audit trails can filter by scope.

The scope is enforced at the API layer: when Bob requests "list all hosts," the server returns only hosts in the `group:staging` group.

## Custom Roles

You can create custom roles for special cases:

```bash
POST /v1/rbac/roles
{
  "name": "backup-admin",
  "description": "Can manage backups and perform restores",
  "permissions": [
    "host:read",
    "backup:create",
    "backup:restore",
    "audit:read"
  ]
}
```

Then assign it to a user:

```bash
POST /v1/users/dave/role-assignments
{
  "role_id": "backup-admin",
  "scope": "fleet-wide"
}
```

Now Dave has exactly those four permissions, nothing more.

## Best Practices

1. **Follow least privilege**: Assign the smallest role that lets someone do their job.
2. **Use built-in roles when possible**: They're well-tested. Custom roles should be rare.
3. **Separate duties**: Don't give one person all the power. One admin manages users, another reviews audit logs.
4. **Monitor denials**: High-frequency denials might indicate misconfiguration or an attacker probing for access.
5. **Review assignments quarterly**: Remove roles people no longer need.
6. **Use MFA for high-risk actions**: Even if Alice is Owner, MFA prevents accidental damage.

## Related Pages

- [RBAC Basics](./30-rbac-basics.md) — Concept overview
- [Design: RBAC](../../developer/design/rbac.md) — Architecture and code reference
- [Cedar Policy Language](https://www.cedarpolicy.com/) — Official Cedar documentation
