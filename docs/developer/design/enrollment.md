---
title: Enrollment
status: stable
---

# Enrollment

Host enrollment is the zero-trust onboarding process that establishes identity and TLS credentials for a new agent. It combines a one-time bootstrap token with a Certificate Signing Request (CSR) flow to avoid pre-shared secrets or public key distribution.

---

## Goals

1. **Zero Trust**: No credentials pre-distributed to hosts; token single-use and short-lived.
2. **Self-Signed CSR**: Agent generates its own keypair; server signs only the CSR, never the keypair.
3. **Atomicity**: Token consumed exactly once; replay rejected.
4. **Auditability**: Every enrollment event (success, failure, token expiry, re-enrollment) logged to the hash-chained audit trail.
5. **Recovery**: Re-enrollment allowed for legitimate host loss scenarios (disk replacement, VM snapshot, etc.) with RBAC controls.

---

## Bootstrap Token

### Format & Lifetime

- **Format**: `hlb_` prefix + base32-encoded 256-bit entropy. Example: `hlb_a1b2c3d4e5f6g7h8...`
- **TTL**: Configurable, default 15 minutes via `FLEET_ENROLLMENT_TOKEN_TTL` env var.
- **Storage**: Hash (SHA-256) persisted in database; plaintext returned to admin only at creation time.
- **Single-use**: Atomic `UPDATE` with `WHERE redeemed_at IS NULL` ensures token cannot be consumed twice even under concurrent redemption attempts.
- **Rate limiting**: Per-source-IP token bucket (default 5 burst, ~0.5/sec sustained). Prevents brute-force token guessing.

### Token Lifecycle

1. Admin mints token via `POST /v1/enrollment-tokens` (admin-only) with optional label and TTL.
2. Plaintext token returned **once** to UI; never persisted.
3. Admin shares token with operator via secure out-of-band channel (e.g., encrypted chat, email, or printed label).
4. Operator runs install script on host with token: `curl -fsSL https://<server>/install.sh | sh -s -- --token=hlb_...`
5. Installer calls `POST /v1/enroll` with CSR + token.
6. Server verifies token hash, redeems atomically (atomic `UPDATE ... SET redeemed_at=now, host_id=<new_id>`), signs CSR.
7. On success, token disappears from the pending list (UI re-renders pending tokens).
8. On failure or expiry, token remains valid until TTL or revoked by admin (`DELETE /v1/enrollment-tokens/{id}`).

---

## Certificate Signing Request (CSR) Flow

### Agent-Side Generation

Agent performs the following at enrollment time:

1. **Key generation**: ECDSA P-256 keypair generated in memory. Private key never exposed.
2. **CSR creation**: Agent creates a Certificate Signing Request (PKCS#10) with:
   - Subject CN: derived from agent-reported hostname (not trusted; CA ignores it).
   - Additional Subject Alternative Names: None (agent does not know `host_id` yet).
3. **Signing the CSR**: CSR signed by the agent's Ed25519 signing key (which was also generated locally).
4. **Request to server**: Agent calls `POST /v1/enroll` with:
   ```json
   {
     "token": "hlb_a1b2c3d4...",
     "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\n...",
     "hostname": "lab-host-01",
     "agent_pubkey": "<base64 raw Ed25519 pubkey>"
   }
   ```

### Server-Side Signing

Server validates and signs the CSR:

1. **Token validation**: Lookup token hash in DB; check not redeemed and not expired. Return `410 Gone` if failed.
2. **CSR parsing**: Parse CSR PEM; extract public key (the new TLS keypair's public key).
3. **Signature verification**: Verify CSR signature using the agent's Ed25519 public key (to prove agent has the private key).
4. **Host identity creation**: Atomically:
   - Generate new `host_id` (UUID).
   - Create `Host` record with `agent_pubkey`, `enrolled_at=now()`, initial status `healthy`.
   - Redeem token: `UPDATE enrollment_tokens SET redeemed_at=now(), host_id=<new_id> WHERE token_hash=...`.
   - Emit audit entry: `action="host.enrolled"`.
5. **Leaf cert issuance**: Internal CA signs a new leaf certificate with:
   - **Subject CN**: `spiffe://hl_helper/host/<host_id>` (SPIFFE identity).
   - **SAN**: URI SAN `spiffe://hl_helper/host/<host_id>`.
   - **Public key**: From the agent's CSR (the new ECDSA P-256 key).
   - **TTL**: 7 days (configurable via `HL_CERT_TTL_DAYS`, default overriding legacy 24h from spec).
   - **Serial**: 20-byte random.
6. **Response**: Return CA chain (leaf + intermediate + root) plus gRPC endpoint metadata:
   ```json
   {
     "host_id": "host_a1b2c3d4...",
     "cert_pem": "-----BEGIN CERTIFICATE-----\n...",
     "ca_chain_pem": "-----BEGIN CERTIFICATE-----\n...",
     "ca_root_pem": "-----BEGIN CERTIFICATE-----\n...",
     "grpc_endpoint": "fleet.example.com:443"
   }
   ```

### Agent-Side Storage

Agent persists the issued certificate chain:

1. **TLS cert + key**: Write to `tls.crt`, `tls.key` (mode 0600 in 0700 dir).
2. **Signing key**: Already persisted during agent setup (not during enrollment; survives re-enrollment).
3. **CA root**: Persist `ca_root.pem` for future TLS verification.
4. **Pinned root**: Use root CA public key for all future TLS handshakes; never trust DNS/system CA store.

---

## Certificate Constraints & Internal CA

### Certificate Lifecycle

- **TTL**: 7 days by default (configurable via `HL_CERT_TTL_DAYS` at server startup).
- **Auto-renewal**: Agent initiates rotation at 50% TTL (approximately 3.5 days).
- **Per-cert serial**: 20-byte random value; logged and retained in `cert_revocations` table on rotation/revocation.

### Internal CA Structure

The server maintains a public-key infrastructure (PKI) for signing host certs:

| Key | Purpose | Storage | Rotation |
|---|---|---|---|
| Root CA (offline) | Trust anchor | Encrypted backup, never online | Yearly (manual) |
| Intermediate CA (signing) | Delegates leaf cert issuance | Encrypted disk, access controlled | Yearly (scheduled) |
| Server signing key (Ed25519) | Signs commands sent to agents | Encrypted disk, accessed at runtime | Yearly (scheduled) |

**Root Key Storage**: Determined by `FLEET_ROOT_KEY_SOURCE` setting:
- `file:<path>` — Root CA private key on disk (mode 0600), encrypted with Vault/KMS if available.
- `vault:<path>` — Root CA stored in HashiCorp Vault (enterprise deployments).
- `tpm2:<path>` — TPM2 module (if available on host).

**Intermediate CA Key**: By default, same storage backend as root (inheriting `FLEET_ROOT_KEY_SOURCE`). In production, keep offline and rotate periodically. Intermediate valid for ~1 year; signed leaf certs valid for ~7 days.

---

## Replay & Abuse Protection

### Single-Use Guarantee

Token consumption is atomic to prevent races:

```sql
UPDATE enrollment_tokens
SET redeemed_at = ?, host_id = ?
WHERE token_hash = ? AND redeemed_at IS NULL
RETURNING id;  -- rowcount validates atomicity
```

Concurrent redemption attempts will race; only one wins. The other receives HTTP 410 Gone.

### Rate Limiting

Two-level rate limiting applies:

1. **Per-IP burst limit**: 5 enrollments per IP within a 60-second window. Further attempts blocked with `429 Too Many Requests` + `Retry-After` header.
2. **Per-token expiry**: Token becomes invalid at TTL; no enrollment possible after expiry regardless of rate limit state.

### Audit Trail

Every enrollment attempt (success or failure) is logged:

- `action="host.enrolled"` — successful enrollment with `host_id`, `peer_ip`, `agent_hostname`.
- `action="host.enrollment_failed"` — failure with `reason` (expired, invalid token, CSR malformed, etc.).
- `action="enrollment_token_created"` — admin mints a token with `label`, `ttl_seconds`, `created_by_user_id`.
- `action="enrollment_token_revoked"` — admin revokes pending token with `token_id`, `reason`.

---

## Re-enrollment

### When Allowed

Re-enrollment (issuing a fresh host cert and replacing existing identity) is permitted in these scenarios:

1. **Automatic via signing-key recovery** (see [Key Rotation](key-rotation.md)): Agent presents a signed challenge; server validates the signature matches a known host's signing key and issues a new cert. **No token required.**
2. **Manual re-enrollment token**: Admin mints a fresh `purpose='reenroll'` token bound to a specific `host_id`. Operator runs `hl-agent reenroll --url ... --token ...` on the host. Similar flow to initial enrollment but reuses the original `host_id` if signing key matches, or creates a new host if signing key lost.

### Authorization

- **Automatic recovery**: Requires valid agent (able to sign challenge with original signing key).
- **Manual re-enrollment token**: Requires `host:enroll` permission (admin).
- **Decommission old host record**: On successful re-enrollment, the old host record is marked `decommissioned` and no longer receives commands; old cert is revoked in `cert_revocations` table.

### Preventing Abuse

1. **Signing key proof**: Recovery via challenge-response proves the agent has the original signing key. Prevents malicious hosts from re-enrolling a victim host.
2. **Rate limit**: Max 3 re-enrollments per 24 hours per host. Abuse flags and alerts on anomaly.
3. **Audit trail**: Every re-enrollment logged with original signing key fingerprint, new host_id (if applicable), and actor.

---

## Sequence Diagram: Initial Enrollment

```
Admin                 UI                    Server                    Agent
────                  ──                    ──────                    ─────
  │                   │                       │                        │
  ├─── mint token ─────→  POST /v1/enrollment-tokens (admin-required)  │
  │                   │                       │                        │
  │                   │  ◄─ plaintext token, ttl ───                   │
  │                   │    (returned ONCE)                             │
  │                   │                       │                        │
  │  (shares via chat/email) ──────────────────────→  curl install.sh │
  │                                            │       --token=hlb_... │
  │                                            │                        │
  │                                            │  ◄─ installer runs,   │
  │                                            │     gen keypair,      │
  │                                            │     builds CSR        │
  │                                            │                        │
  │                                            │  POST /v1/enroll ─────→
  │                                            │  {token, csr_pem,      │
  │                                            │   hostname, agent_key} │
  │                                            │                        │
  │                                            │  verify token hash     │
  │                                            │  parse CSR             │
  │                                            │  validate sig (agent_key)
  │                                            │  gen host_id (uuid)    │
  │                                            │  atomically redeem:    │
  │                                            │    update token        │
  │                                            │    create Host record  │
  │                                            │  sign cert (7d TTL)    │
  │                                            │  emit audit entry      │
  │                                            │                        │
  │                                            │  ◄─ cert_pem, chain ──
  │                                            │     {host_id,          │
  │                                            │      grpc_endpoint}    │
  │                                            │                        │
  │                                            │     write cert/key     │
  │                                            │     pin root CA        │
  │                                            │                        │
  │  (UI refreshes) ◄─ token disappears ──────────────────────────── │
  │  (host appears)    from pending list                              │
```

---

## Related

- [Transport](../architecture/transport.md) — TLS cert lifecycle, SPIFFE URIs
- [Key Rotation](key-rotation.md) — Auto-rotation at 50% TTL, re-enrollment recovery
- [Threat Model](../secure-dev/threat-model.md) — T7 (stolen bootstrap token), T1 (compromised host re-enrollment)
