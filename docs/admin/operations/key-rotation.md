---
title: Key Rotation Procedures
status: stable
---

# Key Rotation Procedures

Operators manage three types of keys: agent TLS certificates (auto-rotated), server signing key (manual, yearly), and agent signing keys (manual, on compromise). This document covers procedures for each.

---

## Key Types Overview

| Key | TTL | Rotation | Role | Compromise Impact |
|---|---|---|---|---|
| **Agent TLS cert** | 7 days | Auto (at 50% TTL) | mTLS handshake | Attacker can impersonate host; mitigated by auto-rotation |
| **Server signing key** | 1 year | Manual (annual) | Sign commands | Attacker can forge commands; mitigated by grace period |
| **Agent signing key** | Lifetime | Manual (on compromise) | Sign results | Attacker can forge results; per-host isolation |

---

## Agent TLS Certificate Rotation (Automatic)

Agent TLS certificates are automatically rotated before expiry. No operator action is required for normal operation.

### How it works

- **TTL**: 7 days (configurable via `HL_CERT_TTL_DAYS`)
- **Trigger**: Agent checks cert expiry at startup and periodically; rotates at 50% TTL (~3.5 days) with ±10% jitter
- **Process**: Agent generates new CSR, sends to server, receives new cert, installs it, reconnects
- **Old cert**: Immediately added to Certificate Revocation List (CRL)

### Monitor rotation across fleet

```bash
# Check all host cert expiry
curl http://localhost:8000/v1/hosts \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.[] | {host_id, hostname, cert_expires_at}'

# Output:
# {
#   "host_id": "host_a1b2c3d4",
#   "hostname": "lab-host-01",
#   "cert_expires_at": "2026-05-16T14:30:00Z"
# }
```

### Force rotation on a specific host

```bash
# Trigger immediate cert rotation (bypasses cooldown)
curl -X POST http://localhost:8000/v1/hosts/host_a1b2c3d4/rotate-cert \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .

# Response:
# {
#   "host_id": "host_a1b2c3d4",
#   "message": "Rotation requested; agent will rotate within 60 seconds"
# }
```

### Check rotation status

```bash
# Query audit log for recent rotations
curl "http://localhost:8000/v1/audit?action=cert_rotated&since=2026-05-08" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.entries[] | {timestamp, subject, payload}'

# Output:
# {
#   "timestamp": "2026-05-09T14:30:45Z",
#   "subject": "host_a1b2c3d4",
#   "payload": {
#     "cert_serial": "abc123",
#     "cert_expires": "2026-05-16T14:30:45Z",
#     "rotation_count": 42
#   }
# }
```

### Verify rotation completeness

Alert if any host has no recent rotation:

```bash
# Hosts that haven't rotated in >4 days (likely stale cert)
# Query: SELECT * FROM hosts WHERE cert_rotated_at < now() - interval '4 days'

# Check via API
curl "http://localhost:8000/v1/hosts?cert_expiry_before=2026-05-13" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.[] | select(.status != "online")'
# If any are offline with expiry soon, investigate
```

---

## Server Signing Key Rotation (Manual, Yearly)

The server signs all commands with an Ed25519 key. Yearly rotation with a grace period allows in-flight commands to verify against both old and new keys.

### When to rotate

- **Scheduled**: Annually, during maintenance window
- **Emergency**: If key is suspected compromised
- **Compliance**: After security audit

### Rotation procedure

**1. Prepare**

```bash
# Document current key info
curl http://localhost:8000/v1/trust-anchors \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.current_key'

# Output:
# {
#   "kid": "2025-05-09-server-signing",
#   "pubkey": "<base64>",
#   "valid_from": "2025-05-09T00:00:00Z"
# }

# Backup current key (if local file-based)
sudo cp /data/signing/current.key /backup/signing-key-2025-05-09.key.enc
```

**2. Rotate key** (server-side)

```bash
# Trigger rotation with 7-day grace period
curl -X POST http://localhost:8000/v1/signing-key/rotate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "grace_period_days": 7
  }' | jq .

# Response:
# {
#   "status": "rotating",
#   "new_key_id": "2026-05-09-server-signing",
#   "grace_until": "2026-05-16T00:00:00Z",
#   "message": "Grace period active: old key verifies commands until 2026-05-16"
# }
```

**3. Verify rotation**

```bash
# Check trust anchors (should have both old and new)
curl http://localhost:8000/v1/trust-anchors \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .

# Output:
# {
#   "current_key": {
#     "kid": "2026-05-09-server-signing",
#     "pubkey": "...",
#     "valid_from": "2026-05-09T00:00:00Z"
#   },
#   "retired_keys": [
#     {
#       "kid": "2025-05-09-server-signing",
#       "pubkey": "...",
#       "valid_until": "2026-05-16T00:00:00Z"
#     }
#   ]
# }
```

**4. Monitor grace period**

During grace, agents trust both keys:

```bash
# Query for commands signed with new key
curl "http://localhost:8000/v1/audit?action=command.issued&since=2026-05-09" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.entries[] | .payload.signature_key_id' | sort | uniq -c

# New commands should be signed with new key_id:
#      123 "2026-05-09-server-signing"  (new)
#       12 "2025-05-09-server-signing"  (old, from cache)
```

**5. Grace expiry** (automatic after 7 days)

```bash
# After grace period, old key is removed from trust list
# New agents/caches will only see new key

# Verify old key is retired
curl http://localhost:8000/v1/trust-anchors \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.retired_keys | length'
# Should be 0 or 1 (previous rotation, if any)
```

### Emergency rotation (key compromise)

If the signing key is compromised, rotate immediately without grace:

```bash
# Force immediate rotation (no grace period)
curl -X POST http://localhost:8000/v1/signing-key/rotate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "grace_period_days": 0,
    "reason": "suspected_compromise"
  }' | jq .

# Old key is immediately removed from trust list
# Any in-flight commands signed with old key will fail verification
# New agents/caches cannot verify old key

# Action: Notify admins to immediately issue new commands
curl -X POST http://localhost:8000/v1/settings/broadcast \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "message": "Signing key rotated due to compromise. All queued commands will be re-issued with new signature."
  }'
```

---

## Agent Signing Key Rotation (On Compromise)

Agent signing keys are long-lived. Rotation is triggered by the server when compromise is detected.

### Normal scenario (none needed)

Agent signing keys have a lifetime equal to the agent's lifetime. They do not rotate unless:
- Key is compromised
- Host is re-enrolled (new agent identity)
- Admin manually requests rotation

### Emergency: Rotate on compromise

**Detection**:
- Anomaly in result signatures
- Administrator discovers unauthorized access to host
- Security audit

**Immediate action**:

```bash
# Decommission the host (revokes cert + signing key)
curl -X POST http://localhost:8000/v1/hosts/host_a1b2c3d4/decommission \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "security.signing_key_compromise"
  }' | jq .

# Server immediately:
# 1. Closes gRPC stream
# 2. Revokes TLS cert (serial added to CRL)
# 3. Marks host as decommissioned
# 4. Logs audit entry: host.decommissioned
# 5. Publishes new CRL

# Agent (if still connected):
# 1. Receives Decommission RPC
# 2. Wipes all keys (tls.*, signing.key, manifest)
# 3. Disables systemd service
# 4. Logs decommission event to /var/lib/hl-agent/decommission.log
```

**Recovery**:

```bash
# On the host, after forensics/remediation:
# 1. OS is confirmed clean (or completely re-installed)
# 2. Agent is re-installed from trusted source

# Generate new bootstrap token
curl -X POST http://localhost:8000/v1/enrollment-tokens \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"label": "lab-host-01-recovery"}' | jq .token

# Re-enroll the host
sudo hl-agent enroll --server https://fleet.example.com:50051 --token hlb_xxx

# Host receives new host_id and signing key
```

---

## Monitoring Key Health

### Dashboard checks

```bash
# 1. Agent cert expiry distribution
curl http://localhost:8000/v1/hosts \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '[.[] | .cert_expires_at] | sort'

# 2. Rotation rate
curl "http://localhost:8000/v1/audit?action=cert_rotated&since=2026-05-08" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.entries | length'
# Should be roughly 1 per host per day (if rotation is healthy)

# 3. Failed rotations
curl "http://localhost:8000/v1/audit?action=cert_rotation_failed&since=2026-05-08" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.entries | map({host: .subject, reason: .payload.reason})'
```

### Alerts to set

| Alert | Threshold | Action |
|---|---|---|
| Host cert expires in <24h | cert_expires_at < now + 1 day | Investigate why rotation didn't trigger |
| Signing key rotation pending | grace_until expired | Verify old key is removed from trust list |
| Rotation failure surge | >5 failures in 5min | Check server logs; possible clock skew or network issues |

---

## Key Backup & Recovery

### Root CA key backup

```bash
# Backup immediately after install (and before rotation)
sudo openssl enc -aes-256-cbc -in /data/ca/root.key \
  -out /offline/secure/fleet-root-ca-$(date +%Y-%m-%d).key.enc

# Password protect (store password in separate secure location)
# Encrypt to a USB key / vault / safe
```

### Signing key backup

```bash
# Backup weekly (encrypted)
sudo openssl enc -aes-256-cbc -in /data/signing/current.key \
  -out /backup/signing-key-$(date +%Y-%m-%d).key.enc -k $(cat /secure/backup-password)

# Store in encrypted backup system (S3 with KMS, separate from DB)
```

### Recovery (lost signing key)

See [Recovery: Lost Server Signing Key](../runbooks/recovery.md#lost-server-signing-key).

---

## Operational Checklist

**Monthly**:
- [ ] Review cert expiry distribution; confirm no hosts have certs expiring in <3 days
- [ ] Verify rotation count increasing (audit log)

**Quarterly**:
- [ ] Test signing key backup restore procedure
- [ ] Verify CA key backup is current and accessible

**Annually**:
- [ ] Rotate server signing key (scheduled, 7-day grace)
- [ ] Audit all key rotation events (query audit log for year)
- [ ] Update backup encryption passwords
- [ ] Disaster-recovery drill: practice root CA key restoration

---

## References

- [Key Rotation Design](../../developer/design/key-rotation.md) — Technical deep dive
- [Enrollment](../deployment/enroll-host.md) — Initial cert issuance
- [Recovery Procedures](../runbooks/recovery.md) — Incident response
- [Key Compromise](../runbooks/key-compromise-recovery.md) — Breach recovery
