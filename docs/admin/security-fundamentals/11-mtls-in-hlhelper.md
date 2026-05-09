---
title: mTLS in hl_helper
status: stable
---

# mTLS in hl_helper

This page explains how hl_helper uses TLS to encrypt and authenticate communication between the control plane (your management server) and agents (the software on each host you manage).

## The Big Picture

Every command and result flows through an encrypted, authenticated mTLS tunnel:

```
Control Plane (FastAPI + mTLS Server)
         ↓ mTLS 1.3 (signed, encrypted)
Agent (Go binary + mTLS Client)
```

Both sides have certificates that prove their identity. If either side is missing a valid certificate, the connection is refused at the TLS layer — no command is even evaluated.

## Certificate Architecture

### Internal CA

When you first set up hl_helper, a special Certificate Authority (CA) is created inside your data directory:

```
<data_dir>/
  ├── ca/
  │   ├── root.key         # Root CA private key (encrypted, backed up offline)
  │   ├── root.crt         # Root CA certificate
  │   ├── intermediate.key # Intermediate CA private key
  │   └── intermediate.crt # Intermediate CA certificate
```

**Root CA**: The ultimate source of trust. The private key is encrypted at rest and should be backed up offline (not on the server). It is only used during setup and key rotation emergencies.

**Intermediate CA**: Used to sign all host certificates. The private key lives on the server and is used constantly (every 12 hours when hosts renew certs). It is valid for 1 year.

### Per-Host Short-Lived Certificates

Each enrolled agent gets a **leaf certificate** that:
- Is valid for **7 days** (configurable via `HL_CERT_TTL_DAYS`).
- Has the subject `CN=spiffe://hl_helper/host/<host_id>` where `<host_id>` is a unique identifier (e.g., `host_abc123def456`).
- Uses ECDSA P-256 encryption (a modern, well-tested algorithm).
- Is signed by the Intermediate CA.

The agent's private key corresponding to this certificate is stored in `/var/lib/hl-agent/tls.key` with restrictive permissions (`mode 0600`).

## The Enrollment Process (TLS Side)

When a new host enrolls for the first time:

1. The installer generates a fresh ECDSA P-256 key pair (public + private) on the host.
2. The installer creates a **Certificate Signing Request (CSR)** — a bundle that says "Here's my public key; please sign it."
3. The CSR is sent to the server along with a one-time bootstrap token.
4. The server verifies the token is valid and hasn't been used before.
5. The server signs the CSR with the Intermediate CA key, issuing a 7-day certificate.
6. The certificate and CA chain are returned to the agent.
7. The agent stores the certificate and private key at `/var/lib/hl-agent/tls.{crt,key}`.

**Why CSR instead of pre-shared keys**: The agent generates its own key locally (the server never touches the private key). This means the server doesn't need to securely transmit keys to every host — the CSR proves the agent has the private key without the server ever seeing it.

## Automatic Certificate Rotation

Certificates expire in 7 days. To avoid service interruptions, renewal happens automatically at **50% TTL** — roughly after 3.5 days.

### How Rotation Works

1. **Agent detects approaching expiry**: The agent wakes up periodically and checks its certificate's `Not After` timestamp. When only 50% of the TTL remains, it starts the rotation process.

2. **Generate new key and CSR**: The agent generates a brand-new ECDSA P-256 key pair and creates a new CSR (similar to enrollment).

3. **Request new certificate**: The agent sends a `CertRotateRequest` over the authenticated gRPC stream to the server. The request includes:
   - The new CSR (with the new public key)
   - A signature proving the agent still has the old private key

4. **Server signs the new cert**: The server validates:
   - The request came from an authenticated host (mTLS handshake succeeded).
   - The signature on the CSR is valid (using the agent's Ed25519 signing key, which is separate).
   - The new public key is different from the old one (no key reuse).

5. **Server issues new cert**: A new 7-day certificate is issued and returned to the agent.

6. **Agent installs new cert**: The agent atomically replaces the old cert with the new one (writes to a temp file, then renames to ensure no partial state).

7. **Connection refresh**: The agent tears down the old gRPC connection and reconnects using the new certificate. In-flight commands on the old connection continue normally (TLS allows this).

8. **Revocation of old cert**: The server records the old certificate serial in the revocation list so that if it's compromised, the server can immediately reject any new connections using it.

### Rotation Jitter

To avoid a "thundering herd" where all agents renew at exactly the same moment, hl_helper adds random jitter (±10% of remaining TTL) to the rotation time. This spreads renewals over several hours.

## Signing Keys (Separate from TLS)

There are two Ed25519 signing keys in the system. They are **not** the same as the TLS certificates:

### Server Signing Key

The server (control plane) signs every command envelope before sending it to an agent.

- **Storage**: Encrypted at rest in `<data_dir>/signing/current.key`.
- **Rotation**: Yearly (manual or scheduled).
- **Trust distribution**: The server publishes the public key in a "trust anchor list" that agents download and cache.

Agents verify every command with the server's public key. This means even if an attacker intercepts the mTLS connection, they cannot forge a command unless they also have the server's signing key.

### Agent Signing Key

Each agent signs every result (command output) before returning it to the server.

- **Storage**: Encrypted at rest in `/var/lib/hl-agent/signing.key`.
- **Rotation**: Server-initiated (the server sends a `Decommission` message asking the agent to generate a new key).
- **Key uniqueness**: Every agent has its own signing key; the server maintains a per-host mapping.

The server verifies every result using the per-host public key. This means even if a host is compromised, the attacker cannot forge results for other hosts.

## Cipher Suite Pinning

hl_helper enforces exactly **two** TLS cipher suites for all connections:

- `TLS_AES_256_GCM_SHA384` (uses AES-256 and GCM authentication)
- `TLS_CHACHA20_POLY1305_SHA256` (uses ChaCha20-Poly1305)

Both are modern, well-audited, and provide 256-bit security. Older, weaker ciphers (DES, RC4, etc.) are never negotiated.

This is enforced via the `GRPC_SSL_CIPHER_SUITES` environment variable that controls the gRPC library.

## Failure Modes and Recovery

| Scenario | What Happens | Recovery |
|---|---|---|
| **Certificate expires** | Agent cannot reconnect (TLS handshake fails) | Automatic rotation prevents this; if it fails, the host becomes offline and must be re-enrolled. |
| **Certificate is compromised** | Attacker can impersonate that host to the server | Add the cert serial to the revocation list; the server rejects new connections from that cert. Old commands stay valid but no new commands are accepted. |
| **Agent's TLS key is lost** (disk corruption, VM snapshot) | Agent cannot connect (doesn't have the private key) | Re-enroll the host with a new bootstrap token. The agent generates a new key pair. |
| **Server's signing key is compromised** | Attacker can forge commands | Rotate the signing key immediately (yearly default, can be done manually). During the 7-day grace window, both old and new keys are trusted. New commands use the new key. |
| **Intermediate CA key is compromised** | Attacker can sign fake certificates for any host | Offline recovery required (see runbooks). Revoke all certificates and re-issue from a fresh CA key. |

## Operator Concerns

### Monitoring Certificate Expiry

hl_helper logs certificate expiry events. Monitor for:

```
certificate expires in 1 day: host_abc123
```

Usually this is automatic and no action is needed. But if you see:

```
certificate rotation failed for host_abc123
```

Check the agent logs on that host. It might have lost network connectivity or disk space.

### Custom Server Certificates

By default, hl_helper generates self-signed certificates for the server (the control plane's web UI and gRPC endpoint). You can replace this with a certificate from your CA:

1. Obtain a certificate for the server hostname/domain.
2. Replace `<data_dir>/server.crt` and `<data_dir>/server.key`.
3. Restart the server.

Agents trust the server CA chain you configured during setup, so as long as the new server cert is signed by a trusted CA, agents will accept it.

## Related Pages

- [Enrollment](./enrollment.md) — Detailed enrollment flow
- [Key Management](./key-management.md) — Protecting private keys
- [Transport Architecture](../../developer/architecture/transport.md) — Deep dive into the protocol
