---
title: Key Management
status: stable
---

# Key Management

This document describes how hl_helper generates, stores, rotates, and secures cryptographic keys across the server and agents.

## Server keys

The server manages two critical key types: the **internal CA** (certificate issuance) and the **signing key** (command envelopes).

### Internal CA

The server runs a self-managed internal CA with a **root** and **intermediate** certificate chain.

#### Root CA

- **Algorithm**: Ed25519 (32-byte private key)
- **TTL**: 5 years (configurable via `FLEET_CA_TTL` env var)
- **Self-signed**: root signs itself
- **Storage**: `<data_dir>/ca/root.key` (file mode 0600) or external KMS/HSM (future)
- **Backup**: **critical** — must be backed up offline (encrypted) at install time. Without root key, all per-host certs become invalid; hosts unreachable.

#### Intermediate CA (Issuing CA)

- **Algorithm**: Ed25519 (32-byte private key)
- **TTL**: 1 year (configurable)
- **Issuer**: signed by root CA
- **Storage**: `<data_dir>/ca/int.key` (file mode 0600)
- **Rotation**: can be rotated without invalidating per-host certs (root stays the same)

#### Usage

- At server startup: load root + intermediate keys
- On enrollment: intermediate key signs per-host leaf certificate (Ed25519)
- For mutual TLS: grpcio presents leaf cert during handshake; agent verifies against pinned root

### Server signing key

A separate Ed25519 key dedicated to signing command envelopes, result verification, and audit checkpoints.

- **Algorithm**: Ed25519 (32-byte private key)
- **Use**: sign every `CommandEnvelope` + every `AuditEntry` + Merkle checkpoints
- **TTL**: manually rotated (recommended yearly)
- **Storage**: `<data_dir>/signing/current.key` (file mode 0600) or KMS/HSM
- **Backend abstraction**: `SigningBackend` interface supports multiple storage options:
  - `FileBackend` — keys on disk (v1.0 default)
  - `VaultBackend` — HashiCorp Vault Transit (future, C3)
  - `PKCS11Backend` — hardware security modules (future)
  - `KMSB ackenbackend` — AWS KMS / GCP Secret Manager / Azure Key Vault (future)

#### Rotation with grace period

Server signing key rotation uses a **grace period** (default 7 days) to allow in-flight commands to be verified:

1. Admin initiates rotation: `fleet signing-key rotate --grace 7d`
2. Server generates new Ed25519 key
3. Old key marked "retired" with expiry timestamp (now + 7d)
4. New key becomes "current"
5. All new commands signed with new key
6. Old keys retained in `<data_dir>/signing/anchors/retired-<timestamp>.pub` for verification of past entries
7. After grace expires, old key deleted

**Audit entry** on rotation:
```json
{
  "action": "server.signing_key_rotated",
  "actor": "admin-id",
  "data": {
    "previous_key_fp": "sha256:abc123...",
    "new_key_fp": "sha256:def456...",
    "grace_expires_at": "2026-05-09T10:00:00Z"
  }
}
```

#### Trust anchors

Agent downloads server's trust anchors (public keys) during enrollment:

```json
{
  "server_signing_anchors": [
    "-----BEGIN PUBLIC KEY-----\nMC4wBQYDK...\n-----END PUBLIC KEY-----",
    "-----BEGIN PUBLIC KEY-----\nMC4wBQYDK...\n-----END PUBLIC KEY-----"
  ]
}
```

Agent verifies every command signature against one of these public keys. Expired keys are replaced on next manifest update.

---

## Agent keys

Each enrolled host holds two Ed25519 keys plus one ECDSA P-256 key for TLS.

### Per-host signing key

- **Algorithm**: Ed25519 (32-byte private key)
- **Use**: sign every `ResultEnvelope`, heartbeat, and local audit entries
- **TTL**: indefinite (identity key; rotated manually or on full re-enrollment)
- **Storage options**:
  - **Filesystem** (default): `/var/lib/hl-agent/signing.key` (file mode 0600)
  - **TPM2** (optional, auto-detected): sealed under TPM primary key; sealed material stored at `/var/lib/hl-agent/signing.key.tpm`
  - Fallback: if TPM seal fails, falls back to filesystem (with audit entry)

### Per-host TLS key

- **Algorithm**: ECDSA P-256 (32-byte private key)
- **Use**: sign Certificate Signing Request (CSR) during enrollment; mTLS handshake with server
- **TTL**: 24 hours (per leaf cert TTL; key itself is identity, rotated when cert rotates)
- **Storage**: `/var/lib/hl-agent/tls.key` (file mode 0600, always filesystem — BoringSSL cannot use TPM-resident keys)
- **Renewal**: at 50% cert TTL (~12 hours), agent renews CSR + gets new leaf cert but keeps same TLS key

### Per-host leaf certificate

- **Algorithm**: ECDSA P-256 (public cert, signed by intermediate CA)
- **TTL**: 24 hours (configurable via `FLEET_CERT_TTL`)
- **SAN**: `spiffe://fleet/host/<uuid>` (URI), hostname, IPv4, IPv6
- **EKU**: clientAuth (TLS client authentication only)
- **Storage**: `/var/lib/hl-agent/certs/leaf.pem` (readable by agent)
- **Renewal**: agent renews by sending CSR to `/v1/certs/renew` (planned in v1.1)

### Why ECDSA P-256 for TLS, Ed25519 for signing?

BoringSSL (used by grpcio) does not reliably negotiate Ed25519 in the `signature_algorithms` extension of TLS 1.3 across all versions. ECDSA P-256 is universally supported and equally secure. Command signing remains Ed25519 because signatures are verified by application code (not TLS handshake), where we have full control.

---

## Secrets at rest

All sensitive data (admin tokens, OIDC client secrets, registry credentials, etc.) stored at rest is encrypted with AES-256-GCM.

### Encryption key hierarchy

```
[ Root Key ] (per-install, very high security)
    ↓
[ HKDF-derived data keys ] (per-secret, per-version)
    ↓
[ AES-256-GCM ciphertexts ]
```

### Root key sources (configurable)

Admin specifies root key backend via `FLEET_ROOT_KEY_SOURCE` at first startup (boot-only setting):

| Source | Storage | Use case | Pros | Cons |
|---|---|---|---|---|
| `file` | `/data/.keyring` (mode 0600) | single-server dev/lab | simple, no dependencies | key on disk |
| `passphrase` | admin enters at startup | air-gapped / offline | no key file | needs manual entry on restart |
| `tpm2` | hardware TPM2 on host | hardened single-server | key never leaves TPM | requires `/dev/tpmrm0` |
| `vault` | HashiCorp Vault KMS | HA / shared servers | external key store, rotate easily | requires Vault running (future C3) |
| `aws-kms` / `gcp-kms` / `azure-kv` | cloud KMS | managed cloud | external rotation, audit trail | cloud dependency (future C3) |

### Secret reference format

Secrets are referenced by a scheme:

```
secret://<backend>/<path>[#<field>]
```

Examples:
- `secret://local/smtp/password` — local backend, SMTP password
- `secret://vault/kv/data/fleet/smtp#password` — Vault backend, KV engine
- `secret://aws/arn:aws:secretsmanager:us-east-1:123456789:secret:fleet/smtp#password` — AWS Secrets Manager

### Local encrypted file backend

Default backend (v1.0):

- **Storage**: `/data/.secrets/` (directory mode 0700, files mode 0600)
- **Per-secret versioning**: each `put` writes `.v<N>.bin`; last 10 versions retained
- **Encryption**: AES-256-GCM with per-secret data key:
  ```
  data_key = HKDF-SHA256(
    ikm=root_key,
    salt=sha256(ref_path),
    info=ref_path || version,
    L=32
  )
  ciphertext = AES256GCM.encrypt(data_key, plaintext, aad=ref_path || version)
  ```
- **Rotation**: `put(ref, value)` increments version; marks old as "retired"; delete after 10 versions

### Cache and performance

- **In-memory cache**: 60-second TTL per ref (configurable)
- **Invalidation**: on `put`, `rotate`, or plugin request
- **Broker pattern**: most callers (SMTP send, registry auth, OIDC client) receive a `SecretHandle` and the broker performs the *use* internally (no plaintext exposure)

---

## Certificate lifecycle

### Per-host enrollment

1. Agent generates Ed25519 signing key (permanent) + ECDSA P-256 TLS key (24h)
2. Agent sends CSR to `/v1/enroll`
3. Server issues leaf cert (24h TTL) signed by intermediate CA
4. Agent stores cert chain (leaf + intermediate + root) locally

### Per-host renewal (planned v1.1)

- At 50% TTL (12 hours after issuance), agent sends new CSR to `/v1/certs/renew`
- Server issues new leaf cert with same TLS key
- Agent updates stored leaf cert
- Downtime: none (stream continues with old cert until new one loaded)

### Revocation

- Admin initiates: `DELETE /v1/hosts/{host_id}` (auth: admin token)
- Server:
  - Marks host as decommissioned
  - Closes active gRPC stream
  - Adds cert serial to in-memory CRL
  - Persists to DB for restart durability
- Agent:
  - Receives `Decommission` RPC (if stream still active)
  - Wipes keys + manifest
  - Disables systemd service
  - Writes decommission log
- Next enrollment: rejected (serial in CRL)

---

## TPM2 sealing (optional)

When available, agent can seal Ed25519 key inside TPM2 hardware.

### Sealed key structure

```
/var/lib/hl-agent/signing.key.tpm:
  - TPM2 public key (tpm2.pub)
  - TPM2 sealed private key blob (sealed.priv)
  - Encryption password (encrypted with hl-agent uid, gid, umask)
  - Unsealing handshake: decrypt password → pass to TPM2 → unseal blob → in-memory key
```

### Advantages

- Key never leaves TPM (even if disk is stolen)
- Resistant to cold-boot attacks
- Audit: TPM logs all key uses

### Limitations

- Kernel updates may invalidate PCR sealing policies (re-seal flow needed, planned in C4 update engine)
- TPM container sharing: if multiple containers share same TPM, all have equal access
- Requires tpm2-tools + BoringSSL support

---

## Rotation cadence

| Key | TTL | Rotation trigger | Procedure | Grace period |
|---|---|---|---|---|
| Root CA | 5 years | approaching expiry | re-generate + re-sign intermediate; old root archived | none — old root invalid |
| Intermediate CA | 1 year | approaching expiry | re-generate + re-sign by root; all per-host certs become invalid after expiry | 30 days (per-host certs still valid until expiry) |
| Per-host leaf cert | 24 hours | approaching expiry (at 50%) | agent sends CSR; server issues new cert | none (seamless renewal) |
| Server signing key | 1 year (manual) | admin initiates rotation | generate new key; old key retained in grace period (default 7d) | 7 days (commands signed by old key still verifiable) |
| Per-host signing key | indefinite (identity) | manual or full re-enrollment | `hl-agent rotate-signing-key`; new key hash-chained to old in audit | none — audit chain verifies continuity |

---

## Backup and recovery

### What to back up

- **Root CA key** + **root cert** (`<data_dir>/ca/root.key`, `root.crt`) — **critical**; back up offline encrypted
- **Intermediate CA key** + **cert** (`<data_dir>/ca/int.key`, `int.crt`) — restore intermediate if needed
- **Server signing key** (`<data_dir>/signing/current.key`) — restore to verify historic audit log
- **Database** (`<data_dir>/fleet.db` or external Postgres) — hosts, certs, tokens, audit log
- **Secrets backend** (`<data_dir>/.secrets/` for local backend, OR Vault snapshot for Vault backend)

### Backup frequency

- Weekly: root CA + signing key (encrypted, offline)
- Daily: database (encrypted, replicated to secondary if HA)
- On rotation: snapshot new signing key

### Recovery scenarios

| Scenario | Recovery | Downtime |
|---|---|---|
| Lost root CA key | Restore from offline backup; restart server | ~5 min |
| Lost intermediate CA key | Restore from backup; regenerate if backup stale | ~5 min; per-host certs still valid until expiry |
| Lost server signing key | Restore from backup; new key after TTL; old key needed for audit verification | varies (new key can be generated but audit chain breaks) |
| Lost database | Restore from backup; affected commands between backup + now are lost | ~15 min |
| Lost per-host key (agent compromised) | Decommission host; re-enroll with new token and key | ~2 min |
| Data dir corrupted | Restore entire `<data_dir>` from backup | ~15 min |

---

## Compliance notes

- **NIST SP 800-57 (Key Management)**: hl_helper follows recommendations for key generation (CSPRNG), key storage (encrypted at rest), rotation (annual signing key), and destruction (wipe on decommission).
- **FIPS 140-2 (future)**: integration with FIPS-approved KMS (Vault, AWS CloudHSM) available in C3.
- **BSI / ANSSI**: Ed25519 + ECDSA P-256 + AES-256-GCM approved for EU compliance.
- **HIPAA (future)**: field-level encryption + audit logging enable HIPAA BAA compliance when paired with Vault.

---

## Troubleshooting

### "Root CA key not found"

Symptom: Server won't start; log says `CA root.key missing`.

- Check file: `ls -la <data_dir>/ca/root.key`
- Restore from backup: `cp /offline/backup/root.key <data_dir>/ca/` + `systemctl restart fleet-server`

### Agent can't use TPM key

Symptom: agent logs show `TPM2 failed, falling back to filesystem`.

- Check TPM health: `tpm2_getcap properties-fixed`
- Check permissions: `ls -la /dev/tpmrm0`
- Re-seal: `hl-agent rotate-signing-key --seal-tpm`

### Audit chain broken after key rotation

Symptom: `fleet audit verify` reports gap between old + new signing keys.

- Expected: keys rotated with grace period; verification succeeds if anchor list includes retired keys
- Check anchors: `cat <data_dir>/signing/anchors/`
- If missing: restore from backup (anchors should be persisted alongside keys)

### Certificate expired, agent offline

Symptom: agent reconnects but cert is expired (not yet renewed).

- On host: `hl-agent rotate-cert` (forces immediate renewal)
- Or: agent will auto-renew on next connection (if clock is correct)

---

## References

- **C1 spec**: `docs/superpowers/specs/2026-05-02-hlh-c1-transport-design.md` (Cryptographic primitives section)
- **Threat model**: `docs/security/threat-model.md`
- **C3 spec**: `docs/superpowers/specs/2026-05-02-hlh-c3-auth-secrets-design.md` (Secrets Broker section)
- **Recovery guide**: `docs/security/recovery.md`
