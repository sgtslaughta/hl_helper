---
title: Audit Chain
status: stable
---

# Audit Chain

The audit chain is a hash-linked, tamper-evident log of all operations (user actions, host events, configuration changes, security incidents). The chain enables forensic verification: any offline tampering is detectable via hash recomputation.

---

## Design Goals

1. **Tamper detection**: Hash chain + periodic Merkle checkpoints enable verification of audit integrity post-incident.
2. **Non-repudiation**: Ed25519 signatures on entries tie events to verified actors and keys.
3. **Completeness**: Append-only; no deletion or selective purging of entries.
4. **Queryability**: Fast filtering by timestamp, actor, action, resource.
5. **Auditability of audit**: Audit-log retention policy itself is logged (setting changes).
6. **Export**: Audit trail exportable for external SIEM/compliance tools (NDJSON, CSV).

---

## Hash-Chained Structure

### Entry Schema

Each audit entry contains:

```
CREATE TABLE audit_entries (
  sequence INTEGER PRIMARY KEY,        -- monotonic, starts at 1
  timestamp TIMESTAMPTZ NOT NULL,      -- UTC, set at insert time
  actor TEXT NOT NULL,                 -- user_id or service identity
  action TEXT NOT NULL,                -- e.g., "host.enrolled", "user.login_success"
  subject TEXT,                        -- resource ID (host_id, user_id, etc.)
  payload JSONB NOT NULL,              -- action-specific data
  prev_hash BLOB NOT NULL,             -- 32 bytes, hash of previous entry
  entry_hash BLOB NOT NULL,            -- 32 bytes, hash of this entry
  signature BLOB,                      -- 64 bytes, optional Ed25519 signature
  UNIQUE (sequence)
);
```

### Hash Computation

Each entry's hash is computed as:

```
entry_hash = SHA-256(
  prev_hash || 
  sequence (8 bytes, big-endian) ||
  timestamp (ISO8601 string) ||
  actor ||
  action ||
  subject ||
  payload (JSON, sorted keys) ||
  "hl_helper_v1"  -- domain separator
)
```

The first entry's `prev_hash = SHA-256("")` (hash of empty string).

### Verification

To verify audit integrity (offline):

1. Load all entries from export (NDJSON/CSV).
2. Recompute each entry's hash using the formula above.
3. Check that `recomputed_hash == stored_hash`.
4. Check that chain is unbroken: each entry's `prev_hash == previous_entry.entry_hash`.

Any mismatch indicates tampering at that point.

---

## Merkle Checkpoints

### Checkpoint Schema

Periodic Merkle checkpoints provide a signed root hash over a range of entries:

```
CREATE TABLE audit_checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  covers_sequence INTEGER NOT NULL,    -- last entry seq included
  merkle_root BLOB NOT NULL,           -- 32 bytes, Merkle tree root
  signature BLOB NOT NULL,             -- 64 bytes, Ed25519(merkle_root)
  signing_pubkey BLOB NOT NULL,        -- 32 bytes, Ed25519 public key
  timestamp TIMESTAMPTZ NOT NULL,
  FOREIGN KEY (covers_sequence) REFERENCES audit_entries(sequence)
);
```

### Merkle Tree Construction

Every N entries (default N=1000, configurable), server computes a Merkle tree:

1. Load entries `[seq_from .. seq_to]`.
2. Compute leaf hash for each: `leaf_i = SHA-256("hl_audit_leaf_v1" || entry_i.entry_hash)`.
3. Build binary tree bottom-up, pairing adjacent leaves and hashing parent: `parent = SHA-256(left_child || right_child)`.
4. Root hash is the single remaining node.
5. Sign root with server's Ed25519 key: `signature = Ed25519(root_hash)`.
6. Store checkpoint in DB.

### Offline Verification with Checkpoints

After verifying the hash chain up to a checkpoint, verify the Merkle root:

1. Load checkpoint.
2. Recompute Merkle tree from entries `[1 .. covers_sequence]`.
3. Check `recomputed_root == checkpoint.merkle_root`.
4. Verify checkpoint signature using stored `signing_pubkey`.

This gives cryptographic assurance that the audit trail from seq 1 to checkpoint has not been altered.

---

## Append-Only Persistence

### Writing Entries

Entries are appended atomically:

```python
async def emit(self, actor: str, action: str, subject: str | None, payload: dict):
    prev_entry = await self.db.query(AuditEntry).order_by(-AuditEntry.sequence).first()
    prev_hash = prev_entry.entry_hash if prev_entry else SHA256(b"")
    
    entry_hash = compute_entry_hash(
        prev_hash, sequence=prev_entry.sequence + 1 if prev_entry else 1,
        timestamp=now(), actor, action, subject, payload
    )
    
    new_entry = AuditEntry(
        sequence=next_seq,
        timestamp=now(),
        actor=actor,
        action=action,
        subject=subject,
        payload=payload,
        prev_hash=prev_hash,
        entry_hash=entry_hash
    )
    await self.db.add(new_entry)
    await self.db.commit()  # atomic INSERT
```

**Concurrency**: SQL `sequence` primary key prevents duplicates. If two threads race to insert at the same sequence, one fails with constraint violation; exception is retried with exponential backoff.

### No Deletion

Retention policies are **immutable per entry**, not deletion:

```
CREATE TABLE audit_retention_policy (
  action TEXT PRIMARY KEY,           -- e.g., "user.login_success"
  keep_for_days INTEGER,             -- 90, 365, 2555, etc.
  archived_destination TEXT,         -- S3 bucket, Splunk endpoint, etc.
  last_archived_seq INTEGER
);
```

When retention period expires:
1. Entry marked for archival (new column `archived_at`), not deleted.
2. Entry optionally uploaded to external storage (S3, Splunk, etc.).
3. Periodic cleanup removes archived entries older than grace window (default 30 days).
4. Audit of archival itself is logged: `action="audit.archived"`.

---

## Verification API

### REST Endpoints

**`GET /v1/audit`** (requires `audit:read`)

Filters + pagination:

```
GET /v1/audit?action=host.enrolled&actor=user_abc&since=2026-05-01&limit=100&offset=0
```

Returns:

```json
{
  "entries": [
    {
      "sequence": 1234,
      "timestamp": "2026-05-09T12:00:00Z",
      "actor": "user_abc",
      "action": "host.enrolled",
      "subject": "host_xyz",
      "payload": {...},
      "entry_hash": "deadbeef...",
      "prev_hash": "cafebabe..."
    }
  ],
  "total": 5432,
  "has_more": true
}
```

**`POST /v1/audit/verify`** (requires `audit:verify`)

Verifies a range of entries (inline):

```json
{
  "from_sequence": 1,
  "to_sequence": 1000,
  "checkpoint_id": 1
}
```

Response:

```json
{
  "valid": true,
  "chain_verified": true,
  "merkle_verified": true,
  "merkle_root": "...",
  "checkpoint_signature_valid": true,
  "anomalies": []
}
```

If any hash mismatch detected, `"valid": false` and `"anomalies"` lists the tampering attempts.

**`POST /v1/audit/export`** (requires `audit:export`)

Exports entries in NDJSON or CSV format:

```json
{
  "action_filter": "host.enrolled",
  "since": "2026-04-01T00:00:00Z",
  "until": "2026-05-09T23:59:59Z",
  "format": "ndjson"
}
```

Returns NDJSON stream (one entry per line), optionally gzipped.

---

## Export Formats

### NDJSON (newline-delimited JSON)

Each line is a complete audit entry as JSON:

```
{"sequence":1,"timestamp":"2026-05-01T10:00:00Z","actor":"user_abc","action":"user.login_success",...}
{"sequence":2,"timestamp":"2026-05-01T10:05:00Z","actor":"system","action":"heartbeat.received",...}
...
```

**Advantages**: Streamable, parseable line-by-line, compatible with jq.

### CSV

Tabular format with headers:

```
sequence,timestamp,actor,action,subject,entry_hash,prev_hash
1,2026-05-01T10:00:00Z,user_abc,user.login_success,user_abc,deadbeef...,cafebabe...
2,2026-05-01T10:05:00Z,system,heartbeat.received,host_xyz,badfood...,deadbeef...
...
```

**Advantages**: Importable into Excel, Splunk, other tools.

---

## Retention Policy

### Configuration

```
CREATE TABLE audit_retention_policies (
  action TEXT PRIMARY KEY,
  keep_for_days INTEGER DEFAULT 365,
  export_destination TEXT,
  last_export_seq INTEGER,
  last_export_at TIMESTAMPTZ,
  CONSTRAINT keep_for_days_positive CHECK (keep_for_days > 0)
);
```

Default policy: keep all audit entries for **1 year** (365 days).

Per-action policy overrides:

| Action | Default | Typical Override |
|---|---|---|
| `user.login_success` | 365 days | 90 days (high volume) |
| `user.login_failed` | 365 days | 90 days |
| `host.enrolled` | 365 days | 2555 days (compliance) |
| `secret:write` | 2555 days | 7 years (PCI/SOC2) |
| `role.modified` | 2555 days | 7 years (compliance) |

### Enforcement

Entries older than `now() - keep_for_days` are eligible for removal. Before removal:

1. Export to configured destination (S3, Splunk, etc.) if set.
2. Log archival event: `action="audit.archived"` with seq range.
3. Mark entry `archived_at = now()` (soft delete).
4. After 30-day grace window, hard delete (if configured).

Administrators can query `audit_retention_policies` table to audit the policy itself.

---

## Anomaly Detection

Server monitors audit stream for suspicious patterns:

| Pattern | Detection | Response |
|---|---|---|
| Rapid admin account creation | >5 new `user:write` actions in 5min | Alert, log as `audit.anomaly_detected` |
| Escalated privilege | User role changes from viewer→admin | Always log as `audit.escalation` |
| Bulk secret rotation | >50 `secret:rotate` in 1min | Alert, log with `severity=high` |
| Failed logins surge | >20 `user.login_failed` from same IP in 10min | Block source IP, log as DDoS |

Anomalies are surfaced in Security Posture checks and can trigger webhooks.

---

## Integration with Other Systems

### Splunk / SIEM

Export via configured destination:

```
FLEET_AUDIT_EXPORT_DESTINATION=s3://audit-logs-prod/hl-helper/
FLEET_AUDIT_EXPORT_INTERVAL=3600  # hourly
```

Server batch-uploads entries older than last export to S3; Splunk HTTP Event Collector ingests via Lambda.

### Compliance (SOC 2, PCI-DSS)

Audit log retention tied to compliance requirements:

```
# PCI-DSS: 1 year minimum
role.write: 2555  # 7 years to be safe
secret.*: 2555
setting:write: 2555

# General operations: 1 year
user.login*: 365
host.enrolled: 365
```

---

## Verification Workflow (Incident Response)

After a suspected breach:

1. **Export**: `POST /v1/audit/export?since=<breach_window_start>&until=<breach_window_end>`
2. **Download**: Save NDJSON export locally.
3. **Verify**: Run offline hash-chain verification tool (provided in admin docs):
   ```bash
   hl-audit-verify audit-export.ndjson
   ```
4. **Analyze**: If hash chain valid, audit integrity confirmed; focus on suspicious **content** (who accessed what, when). If invalid, tampering detected at specific sequence; investigate that point in time.
5. **Cross-check**: Compare against logs from agents, external systems (SIEM, NetFlow) to triangulate breach.

---

## Code Reference

- `server/app/models/audit.py` — `AuditEntry` and `AuditCheckpoint` ORM models.
- `server/app/api/v1/audit.py` — REST endpoints.
- `server/app/audit/chain.py` — Hash computation, verification logic.
- `server/app/audit/merkle.py` — Merkle tree construction.
- `server/app/audit/export.py` — NDJSON/CSV export helpers.
- `admin/hl-audit-verify` — CLI tool for offline verification (TODO - verify against code).

---

## Related

- [Threat Model](../secure-dev/threat-model.md) — T5 (audit tampering)
- [Transport](../architecture/transport.md) — Per-command audit entries
