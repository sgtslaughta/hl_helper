---
title: Runbooks
status: stable
---

# Runbooks

A runbook is a step-by-step procedure for handling a specific incident. This page summarizes the available runbooks and when to use each one. For detailed procedures, follow the links.

## Quick Reference

When something goes wrong, use this decision tree to find the right runbook:

**Is it security-related?**

- **Yes, keys compromised** → [Key Compromise Recovery](../runbooks/key-compromise-recovery.md)
- **Yes, admin account compromised** → [Recovery: Compromised admin session](../runbooks/recovery.md#compromised-admin-session-token)
- **Yes, host compromised** → [Recovery: Compromised host](../runbooks/recovery.md#compromised-enrolled-host)

**Is it availability-related?**

- **Server down / won't start** → [Recovery: Data directory corruption](../runbooks/recovery.md#data-directory-corruption-or-loss)
- **Agents can't connect** → [Recovery: Network outage](../runbooks/recovery.md#network-outage--mass-agent-disconnection)
- **Database is locked or corrupt** → [Recovery: Database corruption](../runbooks/recovery.md#server-database-corruption-sqlitepostgres)

**Is it audit-related?**

- **Audit chain is broken** → [Recovery: Audit tampering](../runbooks/recovery.md#audit-log-tampering)
- **Need to verify integrity** → Check `docs/admin/operations/audit.md` (hash-chain verification)

## The Runbooks

### [Key Compromise Recovery](../runbooks/key-compromise-recovery.md)

**Use when**: A private key is compromised (leaked, stolen, or revealed).

**Key scenarios**:
- Agent signing key is disclosed.
- Server signing key is disclosed.
- Intermediate CA key is disclosed.
- Root CA key is disclosed.
- Database password is in logs.

**What it covers**:
- Immediate isolation steps.
- Which key to rotate first.
- How to verify the compromise (audit logs, signed entries).
- Recovery procedures.

**Typical timeline**: 30 minutes to 2 hours depending on severity.

### [Recovery and Incident Response](../runbooks/recovery.md)

**Use when**: Availability or data integrity issues.

**Key scenarios**:

| Scenario | Section |
|---|---|
| Server won't start | Data directory corruption or loss |
| Database is locked | Server database corruption |
| Agents can't connect | Network outage / mass agent disconnection |
| Audit log is broken | Audit log tampering |
| Admin session is compromised | Compromised admin session token |
| Host is compromised | Compromised enrolled host |

**What it covers**:
- Diagnosis steps (how to confirm the problem).
- Containment (stop it from getting worse).
- Recovery (restore from backup or rebuild).
- Verification (confirm it's fixed).

**Typical timeline**: 30 minutes to 4 hours depending on the issue and backup availability.

## How to Use Runbooks

1. **Identify the incident type** — Use the decision tree above.
2. **Open the runbook** — Follow the link.
3. **Read the overview** — Understand the scope and impacts.
4. **Follow the steps** — Runbooks are numbered and sequential.
5. **Verify the fix** — Tests are included; don't skip them.
6. **Document your actions** — Write down timestamps, decisions, and outcomes.
7. **Do a post-mortem** — After the incident, review what happened and what you'd do differently.

## Before You Have an Incident

Prepare now:

1. **Read the runbooks** — Don't wait until there's a crisis to learn about recovery procedures.
2. **Test backups** — Regularly restore from backup to confirm they work.
3. **Monitor alerts** — Set up monitoring for certificate expiry, failed cert rotations, server crashes, etc.
4. **Document your setup** — Know where your backups are, where your root CA key is stored, who has access to what.
5. **Practice incident response** — Simulate an incident in staging (e.g., "what if the server crashes?") and practice recovering.

## Incident Severity Levels

Use these to decide how urgently to respond:

| Level | Definition | Response Time | Example |
|---|---|---|---|
| **Critical** | Full outage; keys lost; audit chain broken | < 30 min | Root CA key missing; server won't start |
| **High** | Partial outage; one critical component affected | < 2 hours | Admin token compromised; signing key leaked |
| **Medium** | Degraded service; single host affected | < 24 hours | One host is compromised; cert rotation failed |
| **Low** | Informational; no impact | < 7 days | Certificate expires in 30 days; log warning |

## Communication

When an incident occurs, keep stakeholders informed:

**Immediately**:
- "We've identified an issue. We're investigating."

**Within 15 minutes**:
- "The issue is [brief description]. Expected resolution time: [estimate]."

**Every 30 minutes** (if ongoing):
- "Status: [what we've done so far]. Still working on [next step]."

**After resolution**:
- "The issue is fixed. All systems are operational."

**Within 24 hours**:
- Post-mortem: "What happened, why, and what we're doing to prevent it."

## Always Remember

1. **Contain before investigating** — Stop the problem from getting worse.
2. **Preserve evidence** — Take snapshots, copy logs, before making changes.
3. **Test before deploying** — Fix the problem in staging first (if possible).
4. **Document your actions** — You'll need this for the post-mortem.
5. **Ask for help** — Don't waste time stuck on something. Reach out to the community.

## Related Pages

- [Incident Response Framework](./40-incident-response.md) — Concepts and decision-making
- [Key Compromise Recovery](../runbooks/key-compromise-recovery.md) — Security incident procedures
- [Recovery Procedures](../runbooks/recovery.md) — Detailed recovery steps
