---
title: HA & Scaling
status: planned
---

# HA & Scaling

!!! planned "Not yet implemented"
    Operator-facing topology document complete; engineering scope design pending. See: `docs/admin/operations/ha-topology.md` (describes deployment topologies for operators).

## Goal

HL Helper deployments range from single-node (default) to high-availability multi-replica architectures. This subsystem designs the engineering patterns for scaling: read replicas, stateless server nodes, external Postgres + Redis, S3 artifact storage, and coordinated singleton services. The operator-facing topology guide (`docs/admin/operations/ha-topology.md`) describes what to deploy; this scope covers how to build it.

## Planned scope

- Single-node default: FastAPI control plane + SQLite/Postgres backend + in-memory pub/sub (all-in-one container).
- Read replicas: stateless FastAPI instances behind load balancer; shared external Postgres; Redis Streams for pub/sub and inter-node communication.
- Coordinated singletons: approval sweeper, schedule engine, command dispatcher (only one instance runs per fleet at any time; elected via distributed lock on shared state).
- External storage: Postgres for transactional data, Redis for sessions/cache/streams, S3 for audit archives and registry-cache.
- Graceful failover: connection pooling, transaction retry, lock election, agent reconnection tolerance.
- gRPC load balancing: agents connect to any available server node (round-robin or pick-first per agent preference).
- Audit chain continuity: Merkle checkpoints persisted on each write (survives node crash/restart).
- Plugin runtime: plugin instances survive server node failures (isolated process; reconnects to any new server node on loss).

## Architecture (planned)

Single-node architecture keeps FastAPI, SQLite, in-memory queues, plugins all in one pod. Read replicas scale horizontally by adding stateless FastAPI replicas against shared Postgres + Redis. The `CommandDispatcher` registers a distributed lock via Redis (or Postgres advisory lock) so only one node dequeues commands at a time. The `ScheduleEngine` similarly locks so jobs fire once despite multiple nodes. The `ApprovalSweeper` sweeper also locks. Agents maintain bidirectional gRPC streams; a node failure causes agent reconnection to another node in ~5s without data loss (commands are persisted in SQLite/Postgres outbox; agent retries).

The audit chain (`AuditEntry` hash-chained, `MerkleCheckpoint` signed root every N entries) is persisted at write time, so even if a server node crashes, the chain is unbroken. Replicas read the same audit chain and verify independently. Posture findings, host risk scores, and other computed data are recalculated asynchronously (eventual consistency) on read-miss or by background workers running on any node.

For S3 storage (optional tier 2+), registry-cache and audit archive go to S3 with server-local LRU fallback. Plugins may request storage (e.g., for rate-limit tracking); plugin storage is scoped to plugin-id and auto-cleanup on uninstall.

## User-facing (planned)

Operators deploying HA will follow a topology guide that prescribes Postgres setup, Redis cluster, load balancer config, and multi-server scaling steps. The installation wizard detects single-node vs HA mode and adjusts prompts (e.g., Postgres connection string). HA status dashboard shows connected server nodes, leader election state, command dispatcher queue depth per node, and audit checkpoint freshness. Failover is transparent; agents reconnect automatically. Operators can take a server down for maintenance and the fleet continues (agent commands queued, singleton jobs re-elected to another node). Full audit trail is queryable across node boundaries (one continuous chain).

## Open questions

- Active/active multi-writer patterns for audit chain (currently single-writer design; active/active requires consensus, deferred).
- Kubernetes-specific patterns (StatefulSet, etcd lease, CRD) deferred to plugin or future spec.

## References

- Operator guide: `docs/admin/operations/ha-topology.md`
- Spec (engineering): not yet written; linked from this page once available.
- Related: [Observability](./observability.md), [Plugins](./plugins.md)
