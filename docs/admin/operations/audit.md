---
title: Audit Log Operations
status: stable
---

# Audit Log Operations

Operators manage the audit log—a hash-chained, tamper-evident record of all system actions. This document covers verification, export, retention, and compliance integration.

---

## Audit Log Basics

The audit trail records all operations:

| Action | Actor | Resource | Payload | Logged To |
|---|---|---|---|---|
| `host.enrolled` | user_abc | host_xyz | hostname, ip, token_used | Audit log, DB |
| `cert_rotated` | system | host_xyz | serial, ttl, rotation_count | Audit log |
| `command.issued` | user_admin | host_xyz | command_name, args, approval_id | Audit log, outbox |
| `result.submitted` | agent_xyz | command_id | exit_code, stdout, signature | Audit log (if configurable) |
| `user.login_success` | user_abc | session_id | ip, timestamp, mfa_verified | Audit log |
| `audit.archived` | system | entry_range | seq_from, seq_to, destination | Audit log |

---

## Hash-Chain Verification

Each audit entry includes a hash of the previous entry, forming a tamper-evident chain. Tampering is detected by recomputing hashes offline.

### Verify Chain (Server-Side)

```bash
# Verify entire audit log integrity
curl -X POST http://localhost:8000/v1/audit/verify \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "from_sequence": 1,
    "to_sequence": 999999
  }' | jq .
```

Response (valid):

```json
{
  "valid": true,
  "chain_verified": true,
  "merkle_verified": true,
  "merkle_root": "deadbeef...",
  "checkpoint_signature_valid": true,
  "anomalies": []
}
```

Response (tampering detected):

```json
{
  "valid": false,
  "chain_verified": false,
  "first_tampered_entry": 12345,
  "anomalies": [
    {
      "sequence": 12345,
      "expected_prev_hash": "cafebabe...",
      "actual_prev_hash": "deadbeef...",
      "evidence": "Previous entry hash does not match stored prev_hash"
    }
  ]
}
```

### Verify Checkpoints

Checkpoints are periodic Merkle roots, signed by the server. Verify their signatures:

```bash
# List checkpoints
curl http://localhost:8000/v1/audit/checkpoints \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.[]'

# Output:
# {
#   "id": 1,
#   "covers_sequence": 1000,
#   "merkle_root": "deadbeef...",
#   "signature": "base64...",
#   "timestamp": "2026-05-01T10:00:00Z",
#   "signing_pubkey": "base64..."
# }
```

Offline verification:

```bash
# Export and verify checkpoint signature (TBD — CLI tool)
hl-audit-verify checkpoint-1.json
# Output: Signature valid (signed by server key ID: 2026-05-01-server-signing)
```

---

## Export Audit Log

### Export to NDJSON

Newline-delimited JSON is suitable for streaming to SIEM, Splunk, or local analysis with `jq`.

```bash
# Export all entries since a date
curl -X POST http://localhost:8000/v1/audit/export \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "since": "2026-05-01T00:00:00Z",
    "until": "2026-05-09T23:59:59Z",
    "action_filter": "*",
    "format": "ndjson",
    "gzip": true
  }' --output audit-2026-05-01.ndjson.gz

# Decompress and view
gunzip audit-2026-05-01.ndjson.gz
cat audit-2026-05-01.ndjson | jq .

# Filter entries by action
jq 'select(.action == "host.enrolled")' audit-2026-05-01.ndjson
```

### Export to CSV

Tabular format for Excel, databases, or BI tools:

```bash
curl -X POST http://localhost:8000/v1/audit/export \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "since": "2026-05-01T00:00:00Z",
    "format": "csv"
  }' --output audit-2026-05-01.csv

# View in Excel or import to Splunk
head -5 audit-2026-05-01.csv
```

---

## Retention Policy

Audit entries are retained per-action. After expiry, entries are archived (soft-deleted) and optionally exported.

### View Retention Policy

```bash
# Query database
curl http://localhost:8000/v1/audit/retention-policy \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.[]'

# Output:
# {
#   "action": "user.login_success",
#   "keep_for_days": 90,
#   "export_destination": "s3://audit-logs-prod/",
#   "last_export_seq": 5000,
#   "last_export_at": "2026-05-08T10:00:00Z"
# }
```

### Default Retention

| Action | Default | Override |
|---|---|---|
| `user.login_success` | 365 days | Reduce to 90 for compliance (high volume) |
| `user.login_failed` | 365 days | Reduce to 90 |
| `host.enrolled` | 365 days | Increase to 2555 (7 years) for PCI-DSS |
| `secret.write` | 2555 days | 7 years (compliance requirement) |
| `role.modified` | 2555 days | 7 years (audit trail) |
| `audit.tampering_detected` | 2555 days | Never delete (compliance) |

### Update Retention Policy

```bash
# Set custom retention for a specific action
curl -X PUT http://localhost:8000/v1/audit/retention-policy/user.login_success \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "keep_for_days": 90,
    "export_destination": "s3://audit-logs/logins/"
  }' | jq .

# Response:
# { "action": "user.login_success", "keep_for_days": 90, "updated_at": "2026-05-09T14:00:00Z" }
```

---

## Archival & Expiration

When an entry reaches the end of its retention period:

1. **Export** (optional): Upload to S3, Splunk, etc. if `export_destination` is set
2. **Archive**: Mark entry `archived_at = now()` (soft delete)
3. **Purge** (optional): After 30-day grace, hard delete from database

### Trigger archival (manual)

```bash
# Archive entries older than retention period
curl -X POST http://localhost:8000/v1/audit/archive \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "user.login_success",
    "before_date": "2026-02-01T00:00:00Z"
  }' | jq .

# Output:
# {
#   "archived_count": 5234,
#   "exported_count": 5234,
#   "destination": "s3://audit-logs/logins/2026-02/",
#   "audit_event_id": 99999
# }
```

---

## SIEM & External Integration

### S3 Bucket Export

Configure automatic export to S3:

```bash
# Update environment or settings
export FLEET_AUDIT_EXPORT_DESTINATION="s3://audit-logs-prod/hl-helper/"
export FLEET_AUDIT_EXPORT_INTERVAL=3600  # hourly

# Restart server
docker restart hl_helper
```

Server will periodically batch-export audit entries to S3 with object metadata:

```
s3://audit-logs-prod/hl-helper/
├── 2026-05/
│   ├── 2026-05-01T10:00:00Z_seq-1-5000.ndjson.gz
│   ├── 2026-05-01T11:00:00Z_seq-5001-10000.ndjson.gz
│   └── ...
```

### Splunk Integration

Splunk HTTP Event Collector (HEC) ingest:

```bash
# Configure
export FLEET_AUDIT_EXPORT_DESTINATION="https://splunk.example.com:8088/services/collector"
export FLEET_AUDIT_EXPORT_TOKEN="<HEC token>"
export FLEET_AUDIT_EXPORT_INTERVAL=600  # every 10 minutes

# Server will POST batches to Splunk
# Splunk indexes as: `index=hl_helper source=audit_log`
```

### Loki (Grafana Logs)

Forward to Loki for centralized log storage:

```bash
export FLEET_AUDIT_EXPORT_DESTINATION="http://loki.monitoring:3100/loki/api/v1/push"
export FLEET_AUDIT_EXPORT_INTERVAL=300  # every 5 minutes
```

---

## Query Audit Log

### List recent entries

```bash
curl "http://localhost:8000/v1/audit?limit=10&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.entries'
```

### Filter by action

```bash
curl "http://localhost:8000/v1/audit?action=host.enrolled&since=2026-05-01" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.entries | length'
```

### Filter by actor

```bash
curl "http://localhost:8000/v1/audit?actor=user_abc&since=2026-05-08" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.entries[] | {timestamp, action, payload}'
```

### Filter by subject (resource)

```bash
curl "http://localhost:8000/v1/audit?subject=host_xyz" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.entries[] | {timestamp, action, actor}'
```

---

## Anomaly Detection

Server monitors audit stream for suspicious patterns:

| Pattern | Threshold | Response |
|---|---|---|
| Rapid user creation | >5 `user.write` in 5min | Alert + log `audit.anomaly_detected` |
| Privilege escalation | Any role change `→admin` | Always logged + alert |
| Bulk secret rotation | >50 `secret.rotate` in 1min | Alert + auto-pause commands |
| Failed login surge | >20 `user.login_failed` from IP in 10min | Block source IP + alert |

### Query anomalies

```bash
curl "http://localhost:8000/v1/audit?action=audit.anomaly_detected" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.entries[]'
```

---

## Incident Response: Audit Tampering

If hash-chain verification fails:

1. **Isolate**: Take server offline (prevent further writes)
2. **Export**: Dump entire audit log to encrypted backup
3. **Investigate**: Identify first tampered entry sequence
4. **Contain**: Determine what happened between last-known-good and tampering
5. **Notify**: Alert security/compliance team

See [Recovery: Audit Log Tampering](../runbooks/recovery.md#audit-log-tampering) for detailed procedures.

---

## Compliance Notes

### PCI-DSS (Payment Card Industry)

Requirement 10: Logging & Monitoring

- ✓ Audit log captures all user actions
- ✓ Hash-chain prevents tampering
- ✓ Retention: 1 year minimum (configure to 2555 days)
- ✓ Export to SIEM or off-system storage monthly
- Recommendation: Quarterly verification of hash-chain integrity

### SOC 2 Type II

Control: Monitoring & Logging

- ✓ Comprehensive audit trail
- ✓ Non-repudiation via signatures
- ✓ Tamper detection capability
- ✓ Retention policy documented & enforced
- Recommendation: Annual disaster-recovery drill with audit restore

### HIPAA

Security Rule: Audit Controls

- ✓ Audit log captures access & modifications
- ✓ Encryption at rest (if using Vault/KMS)
- ✓ Retention: Per your organization's policy
- Consideration: Personal Health Information (PHI) should not appear in logs; use subject IDs or masked values

---

## References

- [Audit Chain Design](../../developer/design/audit-chain.md) — Technical specification
- [Hash-Chain Verification](../../developer/design/audit-chain.md#verification-api) — API details
- [Recovery: Audit Tampering](../runbooks/recovery.md#audit-log-tampering) — Incident response
- [Key Compromise: Checkpoint Key](../runbooks/key-compromise-recovery.md#scenario-3-audit-checkpoint-signing-key-compromised) — Emergency procedures
