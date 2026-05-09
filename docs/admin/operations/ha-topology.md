---
title: HA Topology and Scaling
status: stable
---

# HA Topology and Scaling

This document describes deployment topologies for hl_helper: single-node, read replicas, and active/passive failover. It also explains why true active/active (multi-writer) is not supported today.

---

## Single-Node Topology (Default)

The default deployment runs a single hl_helper server managing all control-plane responsibilities:

```
┌─────────────────────────────────────────┐
│   HL Helper Server (single instance)    │
│  ┌─────────────────────────────────────┐│
│  │ FastAPI control plane (port 8000)   ││
│  ├─────────────────────────────────────┤│
│  │ gRPC bridge (port 50051, mTLS)      ││ ← agents connect here
│  ├─────────────────────────────────────┤│
│  │ SQLite/Postgres backend             ││
│  │ - Host records + certs              ││
│  │ - Audit chain (hash-chained)        ││
│  │ - Approvals + schedules             ││
│  ├─────────────────────────────────────┤│
│  │ Singletons (only one per fleet)     ││
│  │ - ApprovalSweeper (expires old reqs)││
│  │ - ScheduleEngine (fires maintenance)││
│  │ - CommandDispatcher (in-mem queues) ││
│  └─────────────────────────────────────┘│
└─────────────────────────────────────────┘
        ↓ (bidirectional streams)
    [ agent-1, agent-2, ..., agent-N ]
```

**What state lives where**:

| Component | Storage | Replicated? | Writable | Notes |
|---|---|---|---|---|
| Host records | SQLite/Postgres | Yes (Postgres only) | Single writer | Certs, capability manifests, enrollment tokens |
| Audit chain | SQLite/Postgres | Yes (Postgres only) | Append-only (single serialized writer) | Hash-chained log; tampering detectable |
| Pending commands | In-memory (CommandDispatcher) | No | Single writer | Lost on restart; agents re-fetch from `outbox` table |
| Approval engine | SQLite/Postgres | Yes (Postgres only) | Single writer | ApprovalSweeper expires old requests |
| Schedules + jobs | SQLite/Postgres (APScheduler) | Yes (Postgres only) | Single writer | ScheduleEngine fires cron jobs; all jobs must run once |
| Root CA key | Filesystem (/data/ca/) | Manual (backup) | Single owner | Never replicated automatically; operator backs up offline |
| Signing key | Filesystem (/data/signing/) | Manual (backup) | Single owner | Rotated annually; old key moved to anchors/ with grace period |

---

## Why HL Helper is Single-Writer Today

### 1. Audit Chain Serialization

The audit chain is a hash-chained log: each entry hashes the previous entry + payload. This creates a strict serial dependency:

```
Entry 1: hash = sha256(GENESIS_HASH || actor || action || ...)
Entry 2: hash = sha256(Entry1.hash || actor || action || ...)
Entry 3: hash = sha256(Entry2.hash || actor || action || ...)
  ...
```

Two writers appending concurrently would race and produce inconsistent chains. Even with a database-level mutex, distributed writers (across replicas) cannot serialize reliably without a consensus protocol (e.g., Raft). Today, there is only one writer.

**Future**: Redis-backed audit log with Raft consensus (C12 roadmap).

### 2. Scheduler Singletons

APScheduler is configured to fire each job **exactly once**. With multiple writers:

- **ScheduleEngine** (maintains in-memory job registry): two engines might both claim a job to fire → duplicate task execution
- **ApprovalSweeper** (batch expires old approvals): two sweepers might expire the same request twice → inconsistent state

**Future**: Distributed scheduler lock (Postgres advisory lock or Redis).

### 3. CommandDispatcher In-Memory Queues

Commands are queued in memory per agent. If a writer crashes:

- Queued commands are lost (not yet persisted to outbox)
- Agent reconnects to new writer; old commands are gone

**Workaround**: Commands are re-fetched from the `outbox` table on reconnect. Ephemeral in-memory queues are acceptable as long as outbox is durable.

**Future**: Move queues to Redis Streams for durability across restarts.

---

## Multi-Replica Read Scaling (Supported)

You can run **read-only API replicas** behind a load balancer. They cannot issue commands, but they can serve inventory queries, audit log reads, and reports.

### Architecture

```
                    ┌─────────────────────┐
                    │ Load Balancer       │
                    │ (sticky: /v1/auth)  │
                    └──────┬──────┬───────┘
                           │      │
        ┌──────────────────┘      └───────────────────┐
        │                                              │
    ┌───▼────────────────┐            ┌─────────────▼──┐
    │ Replica 1 (RO)     │            │ Replica 2 (RO) │
    │ Port 8000 (read)   │            │ Port 8000 (read)│
    │ - GET /v1/hosts    │            │ - GET /v1/audit│
    │ - GET /v1/approvals│            │ - GET /v1/reports
    └──────────┬─────────┘            └────────┬───────┘
               │                                │
               └────────────────┬───────────────┘
                                │
                        ┌───────▼────────┐
                        │ Postgres (shared)
                        │ - Streaming replication
                        │ - Primary handles writes
                        │ │
                        │ ├─ Host records
                        │ ├─ Audit log
                        │ ├─ Approvals
                        │ └─ Schedules
                        └────────────────┘

        ┌──────────────────────────────────────┐
        │ Primary Server (single, writer)      │
        │ Port 50051 (gRPC, agents connect)    │
        │ Port 8000 (read+write API)           │
        └──────────────────────────────────────┘
```

### What Works with Read Replicas

- **Inventory queries**: `GET /v1/hosts`, `GET /v1/groups`, filters, pagination
- **Audit log reads**: `GET /v1/audit/log` (read-only; no mutations)
- **Reports**: `GET /v1/reports/*` (pre-computed or on-the-fly analytics)
- **Session refresh**: `POST /v1/auth/refresh` (stateless JWT validation)

### What Does NOT Work with Read Replicas

| Operation | Why | Workaround |
|---|---|---|
| Issue commands (`POST /v1/commands`) | Requires access to CommandDispatcher queues (primary only) | Route to primary server |
| Approve/reject (`POST /v1/approvals/:id/decide`) | Writes to approval engine (primary only) | Route to primary server |
| Create schedules (`POST /v1/schedules`) | Writes + ScheduleEngine registration (primary only) | Route to primary server |
| Create/rotate certs | Certificate generation is not replicated (primary only) | Route to primary server |
| Login (first time) | User creation + session minting (primary only) | Route to primary server; replicas can refresh |
| Settings changes | Write to configuration table (primary only) | Route to primary server |

### Setup

Requires **Postgres** (SQLite does not support replication):

```bash
# Primary: streaming replication enabled
# On replica, connect with read-only DSN:
export FLEET_DATABASE_URL="postgresql://fleet_ro:password@primary:5432/fleet?options=-c%20default_transaction_read_only=on"

# Start replica in read-only mode (no writers)
python -m server.app --port 8001 --workers 4

# Behind load balancer, route write operations to primary
# Route read operations to any replica
```

Consistency: eventual (Postgres streaming replication has ~1–5 second lag). Acceptable for dashboards and reports; not suitable for transactional reads that require real-time consistency.

---

## Active/Passive Failover (Cold Standby + Shared Postgres)

If using **Postgres**, you can set up a **cold standby** that takes over in case of primary failure:

### Architecture

```
┌──────────────────────────────┐
│ Primary Server               │ ← agents connect (gRPC :50051)
│ - Writer (all operations)    │
│ - Writes to Postgres         │ ← primary connection
└───────────────┬──────────────┘
                │
        ┌───────▼─────────┐
        │  Postgres       │
        │  Primary        │
        │                 │
        │ Replication ────┼──→ WAL Streaming
        │  connection     │
        └───────┬─────────┘
                │
        ┌───────▼────────────────┐
        │ Postgres Standby       │
        │ (hot-standby, read)    │
        │ wal_level=replica      │
        └───────┬────────────────┘
                │
        ┌───────▼─────────────────┐
        │ Standby Server          │ ← sleeping, watches DB
        │ (cold: systemd stopped) │
        │ /data → NFS/shared-disk │
        │ - On primary crash:     │
        │   1. Detect (no heartbeat)
        │   2. Promote Postgres   │
        │   3. Start standby srv  │
        │   4. Point agents here  │
        └─────────────────────────┘
```

### Recovery Steps (Manual, No Automation Today)

**Assumes**:
- Both servers share `/data` (NFS, SAN, or Postgres handles state)
- Standby database already synced via streaming replication
- Standby server is stopped (systemd unit disabled)

**1. Detect primary failure** (operator runs health check or is alerted):

```bash
# Primary server is unresponsive
curl -s http://primary:8000/v1/health || echo "PRIMARY DOWN"
```

**2. Promote Postgres standby** (if using Postgres):

```bash
# On standby DB host
sudo -u postgres pg_ctl promote -D /var/lib/postgresql/14/main

# Wait for promotion (30–60 seconds)
sudo -u postgres psql -c "SELECT pg_is_in_recovery();"  # should return False
```

**3. Start standby server**:

```bash
# On standby server host (now becomes primary)
sudo systemctl start fleet-server
sudo systemctl status fleet-server

# Verify it's ready
curl http://localhost:8000/v1/health
```

**4. Point agents to new primary** (if DNS was used, DNS propagates; else manual):

```bash
# Agents will reconnect within next heartbeat interval (default: 30 seconds)
# Or restart agents immediately:
on_all_agents: sudo systemctl restart hl-agent
```

**5. Restore audit chain continuity**:

```bash
# New primary inherits audit log from Postgres
# No repair needed if Postgres replication was working
# Verify:
fleet audit log list | head -10
```

### Recovery Characteristics

| Metric | Value | Notes |
|---|---|---|
| **RPO (Recovery Point Objective)** | ~5 seconds (Postgres replication lag) | No data loss; audit log preserved |
| **RTO (Recovery Time Objective)** | 2–5 minutes (manual) | Detect failure + promote + start + agent reconnect |
| **Manual steps** | 5 (detect, promote DB, start server, DNS, verify) | Can be automated with orchestration (Pacemaker, Kubernetes, etc.) |
| **Outage window** | 2–5 minutes | Agents see connection refused; backoff to ~30s retry; new primary accepts connections |

---

## Why Active/Active is NOT Supported

### Why No Multi-Writer?

Two (or more) primary servers writing concurrently would cause:

1. **Audit chain corruption**: Entry hashes diverge; chain breaks
2. **Duplicate operations**: Two writers both approve the same request → approval processed twice
3. **Scheduler races**: Two ScheduleEngines both fire the same job → e.g., cert renewal runs twice
4. **Agent confusion**: Agent connects to writer-1, sees command queue A. Network partition happens. Agent reconnects to writer-2, sees command queue B. Which is authoritative?

### Why It's Hard to Fix

- **Audit chain**: requires **quorum consensus** (Raft/Paxos) to serialize entries. No single writer = no simple hash chain.
- **Singletons**: ScheduleEngine, ApprovalSweeper need **distributed locking** (Postgres advisory lock, Redis). Today they assume local in-memory locks.
- **gRPC streams**: each writer maintains separate in-memory queues per agent. **Agent stream affinity** is required (agent always talks to same writer, else reconnects cause lost messages).
- **Commands in-flight**: if a writer crashes mid-command, the command must be re-fetched atomically. Requires **consistent, replicated outbox**.

### Roadmap to Multi-Writer (C12+)

- [ ] Redis Streams for audit log (consensus via Redis XAUTOCLAIM groups)
- [ ] Redis or Postgres advisory locks for scheduler/sweeper
- [ ] Replicated command outbox (agent re-fetches on failover)
- [ ] Agent stream stickiness (agent pinned to one writer until it fails)

---

## Backup and Disaster Recovery

### What to Backup

| Item | Frequency | Destination | Encryption |
|---|---|---|---|
| **SQLite/Postgres database** | Daily | Offsite (S3, NAS, cold storage) | Yes (at-rest AES-256) |
| **Root CA key** (/data/ca/root.key) | After install + annual rotation | Offline (USB, vault, safe) | Yes (openssl enc or HSM) |
| **Signing key** (/data/signing/) | Weekly | Encrypted backup store | Yes (separate from DB) |
| **Config** (/data/settings.json, .env) | With each deploy | Encrypted version control or backup | Yes (secrets via Vault/KMS) |

### Disaster Recovery Checklist

After total data loss:

1. **Restore database** from latest good backup
   ```bash
   sudo systemctl stop fleet-server
   sudo cp /backup/fleet.db.2026-05-01 /data/fleet.db
   sudo chown fleet:fleet /data/fleet.db
   sudo systemctl start fleet-server
   ```

2. **Restore CA key** from offline backup
   ```bash
   sudo openssl enc -aes-256-cbc -d -in /offline/root.key.enc -out /data/ca/root.key
   sudo chown root:root /data/ca/root.key && sudo chmod 0600 /data/ca/root.key
   ```

3. **Restore signing key** from encrypted backup
   ```bash
   sudo openssl enc -aes-256-cbc -d -in /backup/signing.key.enc -out /data/signing/current.key
   ```

4. **Verify audit chain integrity**:
   ```bash
   fleet audit verify
   # Should report: "Hash chain valid" if no tampering occurred
   ```

5. **Force agents to reconnect** (optional, speeds up recovery):
   ```bash
   on_all_agents: sudo systemctl restart hl-agent
   ```

---

## Monitoring and Alerts

### Health Checks

```bash
# Primary server readiness
curl http://primary:8000/v1/health

# Audit chain integrity (run daily)
fleet audit verify --detailed

# Replication lag (Postgres only)
psql -c "SELECT now() - pg_last_wal_receive_lsn()::text::timestamptz;"

# Agent connectivity
fleet agents list  # all should show last_heartbeat < 1 minute
```

### Red Flags (Alert on)

- Primary server `/v1/health` returns 5xx for >30 seconds
- `fleet audit verify` reports hash-chain mismatch
- Postgres replication lag > 30 seconds
- Any agent has `last_heartbeat` > 2 minutes (indicates network issue or agent crash)

---

## References

- [Key Management](../security/key-management.md) — backup procedures, CA renewal
- [Recovery and Incident Response](../security/recovery.md) — detailed incident procedures
- [Threat Model](../security/threat-model.md) — audit chain & signing key security assumptions
