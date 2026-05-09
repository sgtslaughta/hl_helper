---
title: Key Rotation
status: stable
---

# Key Rotation

TLS and signing key lifecycles ensure that compromised keys have a bounded impact window. Three keys are managed: host TLS certificates (auto-rotated), the server's command-signing key (manual, yearly), and agent signing keys (manual on compromise).

---

## Key Types & Timelines

### 1. Host TLS Certificate (Ephemeral)

**Lifecycle**:
- **TTL**: 7 days (configurable via `HL_CERT_TTL_DAYS`, default overrides legacy 24h spec).
- **Generated**: At enrollment via CSR.
- **Rotation trigger**: Automatic at 50% TTL (~3.5 days) with ±10% jitter.
- **Purpose**: Authenticate host in mTLS 1.3 handshake.

**Risk window if compromised**: 7 days maximum. Old certificates are revoked and added to `cert_revocations` table; mTLS verifier checks this table and rejects revoked serials.

### 2. Server Signing Key (Ed25519)

**Lifecycle**:
- **TTL**: 1 year (default, configurable).
- **Rotation trigger**: Manual or scheduled (recommended yearly).
- **Purpose**: Sign command envelopes (`CommandEnvelope.signature`).
- **Trust distribution**: Public key published in a trust anchor list; agents query at startup and cache for 24h.

**Risk window if compromised**: Attacker can forge commands. Mitigation: 7-day grace window during rotation allows both old and new public keys to verify. All in-flight commands with old key signatures continue to work during grace; new commands use new key.

### 3. Agent Signing Key (Ed25519)

**Lifecycle**:
- **TTL**: Lifetime of the agent (unless compromised).
- **Rotation trigger**: Server can request rotation via `Decommission` message.
- **Purpose**: Sign result envelopes (`ResultEnvelope.signature`).
- **Recovery**: If signing key is lost (disk corruption, VM snapshot), agent must re-enroll (see [Enrollment](enrollment.md)).

**Risk window if compromised**: Attacker can forge results. Mitigation: sign-count anomaly detection on re-enrollment; server maintains signing-key fingerprint per host and rejects mismatches.

---

## TLS Rotation (Automatic)

### Timing

Agent monitors its current TLS certificate's `not_after` field. At 50% of remaining TTL:

```
rotation_time = (not_before + not_after) / 2
jitter = uniform_random(-10%, +10%) * (not_after - now())
trigger_time = rotation_time + jitter
```

Jitter avoids thundering herd at rotation window boundary.

### Rotation Flow

**Phase 1: CSR Generation (in-memory)**

1. Agent generates fresh ECDSA P-256 keypair in memory.
2. Agent creates a Certificate Signing Request (PKCS#10) with the new public key.
3. CSR signed by agent's Ed25519 signing key (proof of possession).

**Phase 2: Server Validation & Issuance**

Agent sends `CertRotateRequest` over authenticated gRPC stream:

```protobuf
message CertRotateRequest {
  string host_id = 1;
  bytes csr_pem = 2;
  bytes signing_pubkey = 3;        // must match Host.agent_pubkey
  string prev_serial = 4;          // current cert serial
}
```

Server validates:

- mTLS client cert valid and not revoked.
- Host ID matches client cert subject.
- `signing_pubkey` matches `Host.agent_pubkey` (proof of key consistency).
- `prev_serial` matches `Host.cert_serial` (prevents replay).
- Rate limit: max 1 rotation per host per hour.
- CSR signature valid (using agent's signing key).
- CSR public key ≠ current TLS public key (no key reuse).

On success, server:

1. Signs leaf certificate (ECDSA P-256, 7-day TTL, subject CN=`spiffe://hl_helper/host/<host_id>`).
2. Updates `Host.cert_serial`, `Host.cert_expires_at`, `Host.cert_rotated_at`, increments `Host.cert_rotation_count`.
3. Inserts `CertRevocation(serial=prev_serial, reason='rotated', host_id=...)`.
4. Emits audit entry: `action="cert_rotated"`.
5. Returns `CertIssueResponse` with new chain.

**Phase 3: Agent Installation**

Agent receives certificate chain:

1. **Stage**: Write new cert/key to `tls.crt.new`, `tls.key.new` (mode 0600, fsync).
2. **Verify**: Load new cert, check public key matches sent CSR public key. Verify cert chain against pinned root CA.
3. **Commit**: Atomic rename:
   ```bash
   mv tls.crt.new tls.crt
   mv tls.key.new tls.key
   fsync <keystore_dir>  # ensure both files visible to OS
   ```
4. **Reconnect**: Close old gRPC stream, open new one with new TLS credentials.
5. **Success**: First heartbeat after reconnect confirms rotation success.

### Failure Recovery

If any step fails:

| Failure | Detection | Recovery |
|---|---|---|
| CSR generation fails | Agent exception | Log, retry at next jitter window (within same TTL slot) |
| Network error during RPC | gRPC stream error | Discard staged cert, retry next window |
| Server rate-limited | `RESOURCE_EXHAUSTED` gRPC code | Exponential backoff 5m → 1h, keep attempting |
| Cert verification fails | `VerifyStagedTLS` assertion error | Log as critical tampering attempt, discard, retry |
| File write fails | `fsync` / rename error | Discard staged, abort, retry next window |
| TLS reconnect fails | Handshake error after commit | Rollback via `tls.crt.prev` (kept from last rotation) |
| Rollback fails | Rollback error | Enter HALTED state, operator intervention required |

### Atomic Cutover

The stage-verify-commit pattern ensures **no race condition**:

- Verification uses cert bytes in memory, not re-read from disk.
- Rename is atomic at OS level.
- Parent directory fsync ensures visibility.
- If crash between commit and reconnect, agent restarts with new cert already in place (idempotent).

---

## Server Signing Key Rotation (Manual, Yearly)

### Rotation Window

Server publishes TWO signing public keys during rotation (7-day grace window):

```
Timeline:
Day 0: New signing key created, published alongside old key.
Days 1-6: Both keys verify commands. Agents cache for 24h.
Day 7: Old key removed from trust anchor list. New key is sole trust anchor.
```

### Flow

1. **Pre-rotation**: Admin schedules rotation window (e.g., 2026-05-16 00:00 UTC).
2. **Key generation**: Server generates new Ed25519 keypair (offline or via KMS).
3. **Grace window start**: Publish new public key in trust anchor list via `/v1/trust-anchors` endpoint.
4. **In-flight commands**: Existing agents cache public key list. New commands signed by new key; old commands still in flight verify with old key.
5. **Grace expiry**: Remove old key from published list after 7 days. New agents fetching trust anchors get only the new key.

### Verification

Agents query `/v1/trust-anchors` at startup and cache for 24 hours. Trust anchor list includes:

```json
{
  "current_key": {
    "kid": "2026-05-16-server-signing",
    "pubkey": "<base64 Ed25519>",
    "valid_from": "2026-05-16T00:00:00Z"
  },
  "retired_keys": [
    {
      "kid": "2026-05-15-server-signing",
      "pubkey": "<base64 Ed25519>",
      "valid_until": "2026-05-23T00:00:00Z"
    }
  ]
}
```

When verifying a command signature, agent checks:
1. Is signature from `current_key`? → Accept.
2. Is signature from a `retired_keys[*]` with `valid_until > now()`? → Accept.
3. Otherwise → Reject with `PERMISSION_DENIED`.

### Audit

Rotation logged:

- `action="server_signing_key_rotated"` — new key published.
- `action="server_signing_key_retired"` — old key removed from trust list.

---

## Agent Signing Key Rotation (On Compromise)

Agent signing keys are long-lived (lifetime of agent) and tied to host identity. Rotation is requested by server via `Decommission` message.

### Trigger

Server sends `Decommission` RPC message when:

- Key compromise suspected (anomalous agent behavior, security incident report).
- Agent hardware replaced (operator-initiated, reuses host_id).
- Key expiry policy enforced (optional per-site policy).

### Flow

**Server-side**:

1. Send `Decommission { requested_by: user_id, reason: "compromise" }` over gRPC stream.
2. Expect agent to generate new Ed25519 keypair and send new CSR.

**Agent-side**:

1. Receive `Decommission` message.
2. Generate new Ed25519 keypair (in secure enclave if TPM available).
3. Create CSR with new public key.
4. Send `EnrollRequest` (equivalent to initial enrollment, but reuses `host_id`).

**Server-side (re-enrollment)**:

1. Lookup `Host` by ID.
2. Verify signature on CSR using **old** public key (`Host.agent_pubkey`) — proves agent still has old key.
3. Update `Host.agent_pubkey = new_pubkey`.
4. Mark old signing key as "superseded" (retain in `cert_revocations` for forensics).
5. Emit audit: `action="agent_signing_key_rotated"`.

### Sign-Count Anomaly Detection

TBD — verify against code. Recovery flow checks agent's WebAuthn sign-count or analog to detect cloned/replayed credentials.

---

## Compromise Scenarios

### Compromised TLS Key

**Attacker can**: Impersonate host in mTLS handshake, decrypt traffic until rotation.

**Mitigation**:
- Automatic rotation every 3.5 days (halfway through 7-day TTL).
- Old serial immediately added to `cert_revocations`; mTLS verifier rejects.
- Impact window: ≤7 days; in practice ≤3.5 days if detected promptly.

### Compromised Server Signing Key

**Attacker can**: Forge commands to all hosts until old key is retired.

**Mitigation**:
- Manual rotation (yearly, scheduled).
- 7-day grace window: both old and new keys valid.
- Audit logs all commands; operator can detect forged ones post-incident.
- New agents fetching trust list after grace window no longer accept old-key signatures.

### Compromised Agent Signing Key

**Attacker can**: Forge results from that host (e.g., report false task completion), until key is rotated.

**Mitigation**:
- Per-host key; compromise isolated to one agent.
- Server can request rotation immediately (see [flow](#flow) above).
- Result verification fails if signature doesn't match current public key.
- Audit trail shows mismatched signatures; operator can quarantine host.

### Compromised Bootstrap Token

**Attacker can**: Enroll one malicious host with a single token.

**Mitigation**:
- Single-use; consuming token marks it redeemed.
- 15-minute TTL; expiry prevents use after window closes.
- Per-IP rate limiting (5 per minute) prevents brute force.
- Audit log shows enrollment source IP; operator can track.

---

## Operator Verification Commands

Administrators can verify key states via CLI:

**Check host cert expiry:**
```bash
hl-admin hosts cert-status <host_id>
# Output:
# Serial: 32d8f0...57899
# Expires: 2026-05-15 15:23 UTC (in 6d 4h)
# Rotations: 3 (last at 2026-05-09 12:00 UTC)
# Status: Healthy
```

**List revoked certificates:**
```bash
hl-admin audit revocations --since 2026-05-01 --reason rotated
# Output: serial, host_id, revoked_at, reason
```

**Verify signing key rotation:**
```bash
hl-admin keys trust-anchors
# Output: current key, retired keys with expiry, cache TTL
```

**Force rotation on a host:**
```bash
hl-admin hosts rotate-cert <host_id> --force
# Sends immediate CertRotate trigger; optional 1hr cooldown waived
```

---

## Code Reference

- `server/app/enrollment/service.py` — Cert issuance, TTL configuration.
- `server/app/grpc/cert_rotate_policy.py` — Rotation rate-limit, validation.
- `server/app/grpc/agent_bridge.py` — `CertRotateRequest` handler.
- `server/app/models/cert_revocation.py` — Revocation tracking.
- `server/app/models/host.py` — Cert metadata (serial, expiry, rotation count).
- `server/app/models/signing_key.py` — Server signing key + trust anchor list.
- `agent/internal/rotator/` — Agent-side rotation state machine.
- `agent/internal/keystore/` — TLS key staging, commit, rollback.

---

## Related

- [Enrollment](enrollment.md) — Initial CSR flow, re-enrollment.
- [Transport](../architecture/transport.md) — mTLS 1.3, cipher suites, SPIFFE URIs.
- [Threat Model](../secure-dev/threat-model.md) — Key compromise mitigations.
