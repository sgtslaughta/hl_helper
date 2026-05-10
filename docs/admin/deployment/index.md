---
title: Deployment
status: stable
---

# Deployment

This section covers deploying and managing hl_helper infrastructure.

## Getting Started

Choose your deployment method:

- **[Single Container Quickstart](./single-container.md)** — Docker/Podman, <5 minutes to working install
- **[Enroll a Host](./enroll-host.md)** — Zero-trust agent onboarding
- **[Agent Installation](./agent-install.md)** — Per-distro agent setup

## Operations & Topology

- **[High Availability Topology](../operations/ha-topology.md)** — HA failover, read replicas, disaster recovery
- **[Backup & Restore](../operations/ha-topology.md#backup-and-disaster-recovery)** — Database, CA key, signing key backup strategy

## Further Reading

- [Enrollment design](../../developer/design/enrollment.md) — Technical deep dive
- [Transport & mTLS](../../developer/architecture/transport.md) — Certificate lifecycle, SPIFFE
