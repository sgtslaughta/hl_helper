---
title: Enroll a Host
status: stable
---

# Enroll a Host

Host enrollment is the zero-trust process of bringing a new agent into the fleet. It uses a short-lived bootstrap token and mTLS certificate signing to establish a secure identity.

---

## Prerequisites

- **hl_helper server** running and accessible (see [Single Container Quickstart](./single-container.md))
- **Agent binary** installed on the target host (see [Agent Installation](./agent-install.md))
- **Network access**: Host can reach server on port 50051 (gRPC, TLS required)
- **Admin token** for minting bootstrap tokens

---

## Step 1: Generate Bootstrap Token (Admin)

In the hl_helper UI or API, create a one-time bootstrap token.

### Via UI

1. Log in to hl_helper (`http://localhost:3000`)
2. Go to **Settings** → **Enrollment** → **New Token**
3. (Optional) Add a label (e.g., "lab-host-01") for tracking
4. Set TTL (default 15 minutes)
5. Click **Generate**
6. **Copy the token** (displayed once; never shown again)
   ```
   hlb_a1b2c3d4e5f6g7h8ijklmnopqrstuvwxyz...
   ```

### Via CLI

```bash
curl -X POST http://localhost:8000/v1/enrollment-tokens \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "lab-host-01",
    "ttl_seconds": 900
  }' | jq .token
```

Response:
```json
{
  "token": "hlb_a1b2c3d4e5f6g7h8ijklmnopqrstuvwxyz",
  "ttl_seconds": 900,
  "expires_at": "2026-05-09T14:45:00Z"
}
```

---

## Step 2: Install Agent (Target Host)

See [Agent Installation](./agent-install.md) for per-distro instructions.

Quick start (most distros):

```bash
curl -fsSL https://fleet.example.com/install.sh | sudo bash
```

This installs the `hl-agent` binary and systemd service.

**TBD**: Verify exact install script URL. Confirm it's served from `/install.sh` endpoint.

---

## Step 3: Enroll Agent (Target Host)

Once the agent is installed, run the enroll command:

```bash
sudo hl-agent enroll \
  --server https://fleet.example.com:50051 \
  --token hlb_a1b2c3d4e5f6g7h8ijklmnopqrstuvwxyz
```

### What happens during enrollment:

1. **CSR Generation**: Agent generates a fresh ECDSA P-256 keypair in memory
2. **Token Validation**: Server verifies the token exists, is not expired, and is not yet redeemed
3. **Signature Verification**: Server checks that the CSR was signed by the agent's Ed25519 signing key
4. **Host Identity**: Server creates a new host record with a unique `host_id`
5. **Certificate Issuance**: Server signs a new TLS certificate (7-day TTL) and returns it
6. **Token Redemption**: Token is marked as redeemed (single-use guarantee)
7. **Agent Storage**: Agent persists the cert/key and starts the systemd service

### Enrollment output (success):

```
[INFO] Starting enrollment...
[INFO] Generated CSR with public key: <fingerprint>
[INFO] Connecting to fleet.example.com:50051...
[INFO] Received certificate: host_xyz <expires 2026-05-16>
[INFO] Installed TLS credentials
[INFO] Registered with fleet
[INFO] Enrollment complete. Status: healthy
```

### Enrollment output (failure):

```
[ERROR] Token expired or invalid (HTTP 410)
[ERROR] Token not found (HTTP 404)
[ERROR] CSR signature verification failed
[ERROR] Cannot reach server (network error)
[ERROR] TLS handshake failed (self-signed cert not trusted)
```

---

## Step 4: Verify Enrollment (Admin)

In the UI or CLI, check that the host appears in the fleet.

### Via UI

1. Go to **Hosts** → **Fleet**
2. New host should appear with:
   - Status: **Healthy** (green)
   - Last heartbeat: **Now** or **a few seconds ago**
   - Cert expiry: **7 days from now**

### Via CLI

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/hosts | jq '.[]'
```

Response:
```json
{
  "host_id": "host_a1b2c3d4e5f6g7h8",
  "hostname": "lab-host-01",
  "status": "healthy",
  "cert_expires_at": "2026-05-16T14:30:00Z",
  "last_heartbeat": "2026-05-09T14:30:30Z",
  "agent_version": "0.1.0",
  "capabilities": ["package_update", "system_info", "reboot"]
}
```

---

## Step 5: Confirm Connectivity (Agent)

On the target host, verify the agent is running and connected:

```bash
sudo systemctl status hl-agent
# ● hl-agent.service - HL Helper Agent
#   Loaded: loaded (/etc/systemd/system/hl-agent.service; enabled; ...)
#   Active: active (running) since 2026-05-09 14:30:30 UTC; 1s ago

sudo journalctl -u hl-agent -n 20
# [INFO] Agent started (version 0.1.0)
# [INFO] Loaded CA cert from /var/lib/hl-agent/ca_root.pem
# [INFO] Dialing fleet.example.com:50051...
# [INFO] TLS handshake successful (cert valid until 2026-05-16)
# [INFO] Stream opened; sending initial heartbeat...
# [INFO] Heartbeat accepted; host_id=host_a1b2c3d4e5f6g7h8
```

---

## Troubleshooting

### Enrollment Timeout

**Symptom**: `Cannot reach server (timeout after 30s)`

**Causes**:
- Server is not running
- Network path is blocked (firewall, NAT)
- Hostname does not resolve

**Fix**:
```bash
# Test connectivity
ping fleet.example.com
nc -zv fleet.example.com 50051  # should succeed

# Check agent logs
sudo journalctl -u hl-agent | grep -i "error\|dial"
```

### Token Expired

**Symptom**: `Token expired or invalid (HTTP 410)`

**Causes**:
- TTL elapsed before agent could enroll
- Token was already redeemed by another host
- Token was explicitly revoked

**Fix**:
```bash
# Generate a fresh token with longer TTL
curl -X POST http://localhost:8000/v1/enrollment-tokens \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"ttl_seconds": 3600}'  # 1 hour

# Re-run enroll command with new token
```

### TLS Handshake Failed

**Symptom**: `TLS handshake failed: certificate verify failed`

**Causes**:
- CA certificate not trusted (likely self-signed cert on server)
- Server certificate is invalid or expired

**Fix** (if using self-signed cert):
```bash
# Copy server's CA cert to agent
scp admin@fleet.local:/path/to/ca.pem /tmp/fleet_ca.pem

# Enroll with explicit CA file
sudo hl-agent enroll \
  --server https://fleet.local:50051 \
  --token hlb_xxx \
  --ca-file /tmp/fleet_ca.pem
```

Or skip verification (dev only; NOT recommended):
```bash
# This is insecure; use only for testing
sudo hl-agent enroll \
  --server https://fleet.local:50051 \
  --token hlb_xxx \
  --insecure-skip-verify
```

### CSR Signature Verification Failed

**Symptom**: `CSR signature verification failed (HTTP 400)`

**Causes**:
- Agent's signing key was lost or corrupted
- Very rare; indicates local keystore corruption

**Fix**:
```bash
# Wipe agent keystore and try again
sudo rm -rf /var/lib/hl-agent/signing.key
sudo systemctl restart hl-agent
sudo hl-agent enroll --server ... --token ...
```

### Host Appears in UI but Agent is Offline

**Symptom**: Host shows in UI but status is "offline" or no recent heartbeat

**Causes**:
- Agent process crashed after enrollment
- Network became unreachable after enrollment succeeded
- Systemd service is disabled or failed

**Fix**:
```bash
# Check if agent is running
sudo systemctl status hl-agent

# If not, restart
sudo systemctl restart hl-agent

# Check logs
sudo journalctl -u hl-agent -n 50 --no-pager
```

### Enrollment Sequence Diagram

```
Admin                    UI/API                 Server                  Agent
────                     ──────                 ──────                  ─────
  │                        │                       │                     │
  ├─── mint token ────────→│                       │                     │
  │                        │  POST /v1/enrollment-tokens                 │
  │                        ├──────────────────────→│                     │
  │                        │                       │                     │
  │                        │  ◄─ token (hlb_...) ──                      │
  │◄───────────────────────│                       │                     │
  │  (token copied)        │                       │                     │
  │                                                │                     │
  │  (shares out-of-band) ────────────────────────────────────────→     │
  │                                                │                 curl enroll
  │                                                │                 --token=hlb_...
  │                                                │                     │
  │                                                │  POST /v1/enroll   │
  │                                                │◄────────────────────
  │                                                │  {token, csr_pem,  │
  │                                                │   hostname,        │
  │                                                │   agent_pubkey}    │
  │                                                │                    │
  │                                                ├─ verify token hash │
  │                                                ├─ parse CSR        │
  │                                                ├─ verify CSR sig   │
  │                                                ├─ gen host_id      │
  │                                                ├─ atomically       │
  │                                                │  redeem token      │
  │                                                │  create Host       │
  │                                                ├─ sign cert (7d)   │
  │                                                │                    │
  │                                                │  ◄─ cert_pem ──────
  │                                                │     {host_id,      │
  │                                                │      grpc_endpoint} │
  │                                                │                    │
  │                                                │  write cert+key    │
  │  (token disappears)                           │  start service     │
  │◄─── refresh UI ────────────────────────────────                    │
  │  (host appears)                                │  heartbeat ────────→
  │                                                │                    │
  │                                                │  ◄─ heartbeat ack ──
```

---

## Certificate Rotation

Agent TLS certificates are automatically rotated before expiry:

- **TTL**: 7 days (default)
- **Rotation trigger**: At 50% TTL (~3.5 days) with ±10% jitter
- **Grace window**: Old certificate remains valid during transition

No admin action is required. See [Key Rotation](../../developer/design/key-rotation.md) for details.

---

## Re-enrollment (Lost Agent)

If an agent's keys are lost (disk failure, OS wipe):

1. On the target host, wipe old keys:
   ```bash
   sudo rm -rf /var/lib/hl-agent/
   sudo systemctl stop hl-agent
   ```

2. Generate a new bootstrap token (same process as Step 1)

3. Re-enroll (same process as Step 3)

The host will receive a new `host_id` and certificate. Old host record can be decommissioned.

---

## References

- [Enrollment Design](../../developer/design/enrollment.md) — Technical specification
- [Agent Installation](./agent-install.md) — Per-distro setup
- [Key Rotation](../../developer/design/key-rotation.md) — Certificate lifecycle
- [Key Compromise Recovery](../runbooks/key-compromise-recovery.md) — Incident response
