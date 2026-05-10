---
title: Runbooks
status: stable
---

# Runbooks

Emergency procedures for incident response and recovery.

## Quick Access

- **[Key Compromise Recovery](./key-compromise-recovery.md)** — Compromised agent/server keys, audit tampering
- **[Recovery and Incident Response](./recovery.md)** — Data loss, corruption, compromised hosts/admins, multi-host incidents
- **Lost Admin Access** — Bootstrap token reset, emergency access (planned)
- **Database Corruption** — Repair & restore procedures (planned)

---

## Incident Decision Tree

**Is the issue security-related?**

- **Yes, keys compromised** → [Key Compromise Recovery](./key-compromise-recovery.md)
- **Yes, admin account compromised** → [Recovery: Compromised admin session token](./recovery.md#compromised-admin-session-token)
- **Yes, host compromised** → [Recovery: Compromised enrolled host](./recovery.md#compromised-enrolled-host)

**Is the issue availability-related?**

- **Server down / won't start** → [Recovery: Data directory corruption](./recovery.md#data-directory-corruption-or-loss)
- **Agents can't connect** → [Recovery: Server not responding](./recovery.md#network-outage--mass-agent-disconnection)
- **Database locked / corrupted** → [Recovery: Server database corruption](./recovery.md#server-database-corruption-sqlitepostgres)

**Is the issue audit-related?**

- **Audit chain broken** → [Recovery: Audit log tampering](./recovery.md#audit-log-tampering)
- **Need to verify integrity** → [Audit Operations: Hash-Chain Verification](../operations/audit.md#hash-chain-verification)

---

## Severity Levels

| Level | Definition | Response Time | Example |
|---|---|---|---|
| **Critical** | Full outage; control plane unreachable; keys lost | <30 min | Root CA key lost; server won't start |
| **High** | Partial outage; one critical system affected | <2 hours | Admin token compromised; signing key lost |
| **Medium** | Degraded performance; single host affected | <24 hours | Agent key compromised; audit tampering detected |
| **Low** | Informational; no impact on operations | <7 days | Agent crash; certificate expiry soon |

---

## Always

1. **Do not panic.** Most incidents are recoverable with offline backups.
2. **Preserve evidence.** Take filesystem snapshots before making changes.
3. **Verify before and after.** Test recovery procedures in staging first.
4. **Document.** Log actions, timestamps, and decisions in incident ticket.
5. **Notify.** Alert stakeholders (users, security team) per your incident policy.

---

## References

- [Recovery Procedures](./recovery.md) — Complete incident playbooks
- [Key Compromise](./key-compromise-recovery.md) — Security incident response
- [Audit Operations](../operations/audit.md) — Integrity verification
- [Key Rotation](../operations/key-rotation.md) — Preventive maintenance
