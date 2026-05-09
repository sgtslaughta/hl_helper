---
title: Enrollment
status: stable
---

# Enrollment

This document describes how hosts securely enroll with the hl_helper control plane for the first time.

## Bootstrap token

The enrollment process begins with a **bootstrap token** — a single-use, time-limited credential that grants a single host the right to request its own TLS certificate from the server.

### Token format and lifetime

- **Format**: `hlb_<256 bits of base32 entropy>` (approximately 50 characters)
- **Entropy**: 256 bits (2^256 possible tokens)
- **TTL**: 15 minutes from issuance (configurable via `FLEET_BOOTSTRAP_TOKEN_TTL`)
- **Single-use**: token is marked consumed atomically in the database after first successful redemption
- **Storage**: hashed at rest with SHA-256; plaintext shown to admin exactly once during token generation

### Token generation (admin side)

1. Admin clicks **"Enroll Host"** in the UI
2. Server generates a cryptographically random 256-bit token
3. Server hashes token with SHA-256 and persists hash to `BootstrapToken` table:
   ```
   id, token_hash, created_by, created_at, ttl_at, consumed_at=NULL, scope="enroll"
   ```
4. UI displays token in a one-liner shell command (shown once, not stored)
5. Optional: admin downloads QR code or JSON snippet for automation

### Token rate limiting

- **Per-IP**: 5 burst, ~0.5/second sustained (token Semaphore)
- **Per-token**: exactly once (atomic SQL `UPDATE ... WHERE consumed_at IS NULL`)
- **Behavior on limit**: HTTP 429 Too Many Requests; audit logged

---

## CSR flow (host side)

### Phase 1: Key generation

On the target host, the install script runs `hl-agent enroll`:

1. **Detect TPM**: Check for `/dev/tpmrm0` + run `tpm2_getcap properties-fixed`. If present and healthy, ask user via prompt or `FLEET_USE_TPM=1` env var.
2. **Generate keypairs**:
   - Ed25519 **signing key** (32 bytes) — used to sign all command results + heartbeats
   - ECDSA P-256 **TLS key** (32 bytes) — used for mTLS handshake
   - If TPM available: seal signing key into TPM2 primary key under owner hierarchy; persist only sealed material + TPM handle to `/var/lib/hl-agent/signing.key.tpm`
   - If no TPM or `--allow-fs-keys`: persist keys as files at `/var/lib/hl-agent/{signing,tls}.key` (mode 0600)
3. **Extract public keys**: Derive public key material from private keys for CSR

### Phase 2: CSR construction

```
POST /v1/enroll
Host: <FLEET_PUBLIC_URL>
Authorization: Bearer hlb_<token>
Content-Type: application/json

{
  "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\n...\n-----END CERTIFICATE REQUEST-----",
  "signing_pubkey_pem": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
  "facts": {
    "hostname": "myhost",
    "os": "debian",
    "os_version": "12.0",
    "arch": "amd64",
    "kernel_version": "6.1.38",
    "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
    "ipv4": "192.168.1.100",
    "ipv6": "fd00::1",
    "agent_version": "0.0.1"
  }
}
```

- **CSR**: PKCS#10 format, signed by the private TLS key, contains:
  - Subject: `CN=<hostname>`
  - SAN (Subject Alternative Name): hostname, IPv4, IPv6 (non-SPIFFE; leaf cert will have SPIFFE URI SAN added by server)
  - Public key: ECDSA P-256 TLS key
- **Signing pubkey**: Ed25519 public key in PEM format — server stores fingerprint + raw bytes for result signature verification
- **Facts**: host introspection (OS, kernel, arch, network config, agent version)

### Phase 3: Server issuance

Server validates the request:

1. **Token check**:
   - Token exists in `BootstrapToken` table
   - Not yet consumed (`consumed_at IS NULL`)
   - Not expired (`NOW < ttl_at`)
   - Return 410 Gone if any check fails; audit log attempt

2. **CSR validation**:
   - CSR signature is cryptographically valid
   - CSR public key matches the provided signing pubkey (prevents key-swap attacks)
   - Hostname is sane (alphanumeric + hyphens, ≤63 chars)
   - SAN matches hostname + IP facts

3. **Certificate issuance**:
   - Issue X.509 leaf certificate signed by internal CA intermediate
   - EKU: `clientAuth` (TLS client only)
   - SAN: `spiffe://fleet/host/<host_uuid>` (URI), plus hostname + IPv4/IPv6 DNS names
   - Validity: 24 hours from now (TTL configurable via `FLEET_CERT_TTL`)
   - Serial: random, tracked for revocation

4. **Manifest generation**:
   - Server generates per-host capability manifest (JSON, signed with server signing key)
   - Lists allowed command types (e.g., `pkg_update`, `get_facts`, `reboot`, `shell_exec`)
   - Per-command config (e.g., pkg update classes, reboot delay cap)
   - Expires slightly before cert expiry

5. **Atomically mark token consumed**:
   ```sql
   UPDATE BootstrapToken
   SET consumed_at = NOW(), used_for_host_id = <host_uuid>
   WHERE id = <token_id> AND consumed_at IS NULL
   ```
   (Prevents race if two enroll requests arrive simultaneously with same token)

6. **Audit log entry** (hash-chained):
   ```
   actor: "system" (server-initiated)
   action: "enrollment.completed"
   subject: <host_uuid>
   data: {
     "ip_address": "192.168.1.100",
     "hostname": "myhost",
     "os": "debian",
     "signing_pubkey_fp": "sha256:<hex>",
     "cert_serial": "0x<hex>",
     "enrolled_by": <admin_id or "bootstrap">
   }
   ```

### Phase 4: Response

Server returns HTTP 201 Created:

```json
{
  "host_id": "abcd-1234-efgh-5678",
  "cert_chain_pem": "-----BEGIN CERTIFICATE-----\n<leaf>\n-----END CERTIFICATE-----\n-----BEGIN CERTIFICATE-----\n<intermediate>\n-----END CERTIFICATE-----\n-----BEGIN CERTIFICATE-----\n<root>\n-----END CERTIFICATE-----",
  "server_signing_anchors": [
    "-----BEGIN PUBLIC KEY-----\n<current Ed25519 signing key>\n-----END PUBLIC KEY-----",
    "-----BEGIN PUBLIC KEY-----\n<retired anchor if within grace period>\n-----END PUBLIC KEY-----"
  ],
  "manifest": {
    "allowed_actions": ["pkg_update", "get_facts", "reboot"],
    "max_risk_level": "HIGH",
    "expires_at": "2026-05-03T10:00:00Z",
    "signature": "<base64 Ed25519 signature>"
  },
  "agent_config": {
    "server_url": "grpc.hl-helper.local:8444",
    "heartbeat_interval_seconds": 30,
    "cert_renewal_percent": 50,
    "outbox_max_bytes": 104857600
  }
}
```

---

## Agent-side persistence

After receiving the enrollment response, the agent persists:

1. **Certificates**: `/var/lib/hl-agent/certs/leaf.pem`, `intermediate.pem`, `root.pem`
2. **Server signing anchors**: `/var/lib/hl-agent/server_trust_anchors.json` (list of PEM-encoded keys)
3. **Manifest**: `/var/lib/hl-agent/manifest.json` (persisted + signature verified on load)
4. **Agent config**: `/var/lib/hl-agent/config.json` (server URL, heartbeat interval, renewal threshold)
5. **Enrollment metadata**: `/var/lib/hl-agent/enrollment.json` (timestamp, IP at enrollment, admin ID)

All files owned by `hl-agent:hl-agent`, mode 0600 (read/write by agent only).

### Service enablement

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hl-agent.service
```

Agent starts automatically and establishes initial gRPC connection to server.

---

## Failure modes and diagnostics

| Failure | HTTP Status | Message | Audit | Resolution |
|---|---|---|---|---|
| Token not found | 404 Not Found | `Token not found or expired` | `enrollment.token_not_found` | Re-mint token |
| Token already consumed | 410 Gone | `Token already redeemed` | `enrollment.token_reused` | Decommission host, enroll again with new token |
| Token expired | 410 Gone | `Token expired <ttl_at>` | `enrollment.token_expired` | Re-mint token |
| CSR signature invalid | 400 Bad Request | `CSR signature verification failed` | `enrollment.bad_csr` | Re-run enroll on host |
| CSR public key mismatch | 400 Bad Request | `CSR key does not match signing pubkey` | `enrollment.key_mismatch` | Re-run enroll on host |
| Hostname not matching facts | 400 Bad Request | `Hostname SAN does not match facts` | `enrollment.hostname_mismatch` | Fix hostname, re-run enroll |
| CA fingerprint mismatch | (client-side, abort) | `Server CA fingerprint does not match (expected <FP>, got <FP>)` | (none, never sent) | Verify `FLEET_CA_FP` environment variable; compare against server's `/data/ca/root.crt` |
| Outbound proxy needed | (client-side diagnostic) | `Agent port appears to require proxy configuration. Set FLEET_AGENT_PROXY=http://proxy:port` | (none) | Configure proxy, re-run enroll |
| TLS termination on agent port | (client-side diagnostic) | `Agent port 8444 appears to be proxy-terminated (mTLS handshake failed). Use TCP passthrough; see docs.` | (none) | Reconfigure reverse proxy for agent port |
| Distro unsupported | (install script exit) | `Distro not supported: <distro>. Manual install: https://docs.hl-helper.local/install-manual` | (none) | Manual install or request distro support |
| TPM unusable | (enrollment interactive prompt or exit) | `TPM detected but /dev/tpmrm0 not accessible. Use --allow-fs-keys to store keys on filesystem.` | `enrollment.tpm_fallback_used` | Retry with `--allow-fs-keys` or fix TPM access |

---

## Rate limiting and abuse prevention

- **Per-IP token limit**: 5 concurrent mints, 1 per 2 seconds sustained
- **Per-token redemption**: exactly 1 (atomic DB)
- **Concurrent enrollment on same host_id**: last one wins (host record updated, old certs revoked)
- **Enrollment on IP with 5+ failed attempts**: HTTP 429 for 15 minutes

---

## Cert rotation (planned v1.1)

At enrollment, leaf cert is valid for 24 hours. Agent proactively renews at 50% TTL (12 hours) via:

```
POST /v1/certs/renew
Authorization: <mTLS>
{
  "current_cert_pem": "<PEM>",
  "csr_pem": "<new CSR, same TLS key>"
}
```

This keeps cert fresh without requiring re-enrollment. During rotation period, both old + new certs are valid (prevents connection hiccups).

---

## Decommission

To permanently remove a host:

**From admin UI** (admin-only):
1. Navigate to host page
2. Click **"Decommission"**
3. Confirm (two-factor prompt if MFA enabled)
4. Server issues `Decommission` RPC to agent over gRPC stream
5. Agent:
   - Securely wipes all keys + certs + manifest
   - Disables systemd service
   - Writes `/var/lib/hl-agent/decommission.log` with timestamp + admin ID + reason
   - Exits cleanly
6. Server removes host record + invalidates cert in CRL

**From host CLI** (emergency):
```bash
sudo systemctl stop hl-agent
sudo /usr/local/bin/hl-agent decommission --force
# removes /var/lib/hl-agent/* and systemd service
```

---

## Security properties

- **One-time use**: bootstrap token consumed atomically; reuse is cryptographically impossible (not just policy-based)
- **Expiry enforcement**: 15-min TTL is checked on every redemption attempt; no clock-skew grace (or minimal configurable grace)
- **No privilege escalation via token**: token grants only the right to request a cert; it does not grant any command-execution capability
- **Replay protection**: CSR is signed by agent, preventing token+CSR theft from being reusable
- **Audit trail**: every enrollment logged (hash-chained); tampering detected
- **Rate limiting**: token minting and redemption both gated to prevent brute-force

---

## Troubleshooting

### Agent not connecting after enrollment

1. Check enrollment config: `cat /var/lib/hl-agent/config.json` — verify server URL and port
2. Verify network reachability: `curl -v https://<server>:8444/` (should fail with TLS handshake, not connection refused)
3. Check cert validity: `openssl x509 -in /var/lib/hl-agent/certs/leaf.pem -noout -text`
4. View agent logs: `sudo journalctl -u hl-agent -f`
5. Verify server signing anchors: `cat /var/lib/hl-agent/server_trust_anchors.json` — should contain at least one Ed25519 key

### Certificate expired

Agent auto-renews before expiry. If cert is already expired:
```bash
sudo systemctl stop hl-agent
sudo /usr/local/bin/hl-agent rotate-cert
sudo systemctl start hl-agent
```

### "Token already redeemed" on second attempt

Enrollment succeeded on first attempt; token was consumed. Run decommission + re-enroll with a new token.

---

## References

- **C1 spec**: `docs/superpowers/specs/2026-05-02-hlh-c1-transport-design.md` (Enrollment Flow section)
- **Threat model**: `docs/security/threat-model.md` (T7: Stolen bootstrap token)
- **Key management**: `docs/security/key-management.md`
- **Agent privilege model**: `docs/security/agent-privilege-model.md`
