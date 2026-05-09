---
title: RBAC Basics
status: stable
---

# RBAC Basics

RBAC stands for **Role-Based Access Control**. It's a way to decide who can do what in a system. This page explains the concept in general terms; the next page shows how hl_helper implements it.

## The Problem: Access Control

Imagine you're running a small company with three employees:

- **Alice**: The founder. She needs to access everything (create backups, manage users, change settings).
- **Bob**: Operations engineer. He needs to run commands, check logs, but shouldn't change user permissions or delete backups.
- **Charlie**: Contractor. He needs read-only access to view system status, but nothing else.

How do you grant the right access without giving everyone admin access?

With passwords: you could give each person their own account. But then you need to manage three separate accounts, rotate three passwords, and audit three login histories.

With **RBAC**, you define roles that describe common job functions, then assign people to those roles.

## Three Concepts: Roles, Permissions, and Actors

### Roles

A role is a collection of permissions. Examples:

- **Admin**: Can do everything.
- **Operator**: Can run commands, view logs, restart services.
- **Viewer**: Can only read information.
- **Backup Manager**: Can trigger backups, restore, view backup history.

### Permissions

A permission describes a specific action on a specific resource. Format: `resource:action`.

Examples:

- `host:read` — View host information
- `host:exec` — Run commands on a host
- `backup:create` — Create a new backup
- `backup:restore` — Restore from a backup
- `user:write` — Create or modify users

### Actors

An actor is a person (or a service) that has roles assigned. Each actor has a user account.

When Alice logs in, the system says: "Alice has the Admin role, so Alice has all permissions in the Admin role."

## The Matrix

Here's a simple matrix showing roles and their permissions:

|  | Viewer | Operator | Admin |
|---|---|---|---|
| **host:read** | ✓ | ✓ | ✓ |
| **host:exec** |  | ✓ | ✓ |
| **host:revoke** |  |  | ✓ |
| **backup:create** |  | ✓ | ✓ |
| **backup:restore** |  | ✓ | ✓ |
| **user:write** |  |  | ✓ |

- **Alice** (Admin): ✓ all
- **Bob** (Operator): ✓ read, exec, backup; ✗ revoke, user:write
- **Charlie** (Viewer): ✓ read; ✗ exec, backup, user:write

## Enforcement: How the System Decides Yes or No

When an actor tries to do something, the system checks:

1. Who is the actor? (Look up their user account.)
2. What role(s) does the actor have? (Look up their role assignments.)
3. Does the role have the required permission? (Check the permission list.)
4. If yes, allow. If no, deny.

```
Actor tries to run `host:exec`
  ↓
System looks up actor's roles: [Operator]
  ↓
System checks if Operator role has `host:exec`: YES
  ↓
Allow
```

## Why Roles Matter (Over Direct Permissions)

Imagine you assign permissions directly to people (no roles):

- Alice: `host:read, host:exec, host:revoke, user:write, ...` (20 permissions)
- Bob: `host:read, host:exec, backup:create, ...` (10 permissions)
- Charlie: `host:read` (1 permission)

Now Alice leaves and you hire David with the same job as Bob. You manually copy Bob's 10 permissions to David. Easy for Bob, but what if you have 100 people?

With roles, you just say: "David is an Operator" and he automatically gets all the permissions.

If you change what "Operator" means (add `audit:read` permission), *all* operators immediately have it without touching 20 user accounts.

## High-Risk Permissions

Some permissions are dangerous and need extra protection.

Examples:
- `host:revoke` — Can remove hosts from your fleet (data loss potential)
- `user:write` — Can create new admin accounts (privilege escalation)
- `secret:write` — Can store new secrets (data exfiltration potential)

For high-risk operations, systems often add extra checks:

1. **MFA step-up**: "You're about to do something dangerous. Enter your authenticator code again to confirm."
2. **Approval gates**: "This operation needs approval from another admin."
3. **Audit logging**: "This action is logged in detail for later review."

## Scope: Limiting Access to Specific Resources

RBAC can be scoped to specific resources. Example:

- **Alice** has Operator role scoped to `group:production` — she can run commands on production hosts only.
- **Bob** has Operator role scoped to `group:staging` — he can run commands on staging hosts only.
- **Charlie** has Viewer role scoped `fleet-wide` — he can see all hosts.

This prevents accidental damage (Alice can't break production by accident) and follows the principle of least privilege.

## Custom Roles

Most systems come with built-in roles (Admin, Operator, Viewer). But you might need a custom role:

- **Database Backup Admin**: Can trigger backups, restore, but can't run arbitrary commands.
- **Security Audit**: Can read logs, audit trails, but can't modify anything.
- **Container Manager**: Can manage containers, update images, but can't manage other resources.

Custom roles allow flexibility without overhauling the entire permission system.

## Audit: Logging Access Decisions

Every permission check should be logged:

- "Alice requested `host:exec` on host_prod_01 — Allowed (Admin role)"
- "Bob requested `user:write` — Denied (Operator role does not have permission)"
- "Charlie requested `host:exec` on host_prod_01 — Denied (Viewer role does not have permission)"

These logs let you:
1. Audit who did what.
2. Detect unauthorized access attempts.
3. Investigate incidents.

## Common Patterns

### Least Privilege

Grant only the minimum permissions needed for a job.

Bad: Everyone is Admin (all permissions).
Good: Viewer if they only need to read; Operator if they run commands; Admin only for essential staff.

### Segregation of Duties

No single person should have all-powerful access. Example:

- One admin creates users.
- Another admin assigns roles.
- A third admin reviews the audit log.

If one person is compromised, the attacker is limited to that person's scope.

### Defense in Depth

RBAC alone is not enough. Combine it with:
- MFA (multi-factor authentication)
- Audit logging
- Network segmentation
- Secrets management
- Certificate pinning

hl_helper uses all of these together.

## Summary

RBAC is a framework for saying "who can do what." It simplifies access control by grouping permissions into roles, assigning roles to people, and logging every decision.

The next page, [Cedar Policies](./31-cedar-policies.md), shows how hl_helper implements RBAC and offers advanced options for complex access control scenarios.
