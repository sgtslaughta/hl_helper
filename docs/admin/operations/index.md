---
title: Operations
status: stable
---

# Operations

Operational procedures and best practices for running hl_helper in production.

## Contents

- **[Audit Log Operations](./audit.md)** — Verification, export, retention, SIEM integration
- **[Key Rotation Procedures](./key-rotation.md)** — Agent certs, server signing key, manual rotation
- **[High Availability & Topology](./ha-topology.md)** — Failover, read replicas, backup strategy, disaster recovery

## Quick Links

- [Audit hash-chain verification](./audit.md#hash-chain-verification)
- [Server signing key rotation](./key-rotation.md#server-signing-key-rotation)
- [Backup & disaster recovery](./ha-topology.md#backup-and-disaster-recovery)
- [Health checks & monitoring](./ha-topology.md#monitoring-and-alerts)

## Further Reading

- [Key Rotation Design](../../developer/design/key-rotation.md) — Technical deep dive
- [Audit Chain Design](../../developer/design/audit-chain.md) — Hash-chaining & verification
- [Recovery Runbooks](../runbooks/recovery.md) — Incident response procedures
