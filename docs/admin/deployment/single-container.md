---
title: Single Container Quickstart
status: stable
---

# Single Container Quickstart

Deploy hl_helper in a single container (Docker or Podman) for development, testing, or small homelabs. Data persists to a volume; TLS is handled by the application or a reverse proxy.

---

## Prerequisites

- **Docker** 20.10+ or **Podman** 4.0+
- **Open ports**: 
  - `3000` — Web UI (HTTP)
  - `8000` — Control plane API (HTTP/gRPC)
  - `50051` — gRPC ingress for agents (TLS required)
- **Storage**: 1 GB minimum for database + advisory cache
- **Network**: Agents must reach server on port 50051 over TLS

---

## Quick Start (One-Line)

```bash
docker run -d \
  --name hl_helper \
  --restart unless-stopped \
  -p 3000:3000 \
  -p 8000:8000 \
  -p 50051:50051 \
  -v hl_helper_data:/app/data \
  -e FLEET_ADMIN_TOKEN="$(openssl rand -base64 32)" \
  -e FLEET_COOKIE_SECURE=false \
  ghcr.io/hlhelper/hl_helper:latest
```

**TBD**: Confirm exact image name (`ghcr.io/hlhelper/hl_helper`). Update once image is published to container registry.

Then:
1. Open http://localhost:3000 in your browser
2. Log in with token printed in logs: `docker logs hl_helper | grep "token="`
3. Proceed to [Enroll a Host](./enroll-host.md)

---

## Docker Compose Example

For a reproducible, documented setup:

```yaml
version: '3.8'

services:
  hl_helper:
    image: ghcr.io/hlhelper/hl_helper:latest
    container_name: hl_helper
    restart: unless-stopped
    ports:
      - "3000:3000"    # Web UI
      - "8000:8000"    # Control plane API
      - "50051:50051"  # gRPC agent ingress (TLS)
    environment:
      FLEET_DATA_DIR: /app/data
      FLEET_DB_URL: sqlite+aiosqlite:////app/data/fleet.db
      FLEET_ADMIN_TOKEN: ${ADMIN_TOKEN:-changeme-insecure-dev-only}
      FLEET_COOKIE_SECURE: ${COOKIE_SECURE:-false}
      FLEET_LOG_LEVEL: info
    volumes:
      - hl_helper_data:/app/data
    healthcheck:
      test: [ "CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/openapi.json', timeout=5)" ]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

volumes:
  hl_helper_data:
    driver: local
```

Start: `docker compose up -d`

Check status: `docker compose ps` or `docker logs hl_helper`

---

## Environment Variables

**Required:**

| Var | Example | Notes |
|---|---|---|
| `FLEET_ADMIN_TOKEN` | `sk-abc123...` | Bootstrap token for first login. Set securely; rotate after first use. |

**Recommended:**

| Var | Default | Notes |
|---|---|---|
| `FLEET_DATA_DIR` | `/app/data` | Mount point for database, CA keys, signing keys. Must be writable. |
| `FLEET_LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error`. Increase for troubleshooting. |
| `FLEET_COOKIE_SECURE` | `true` | Set `false` for dev/HTTP; `true` for production HTTPS. |

**Optional (Advanced):**

| Var | Default | Notes |
|---|---|---|
| `FLEET_DB_URL` | `sqlite+aiosqlite:////app/data/fleet.db` | SQLite default. Use `postgresql://...` for Postgres (HA deployments). |
| `FLEET_ENROLLMENT_TOKEN_TTL` | `900` | Bootstrap token lifetime in seconds (default 15 min). |
| `HL_CERT_TTL_DAYS` | `7` | Agent TLS certificate TTL in days. |
| `FLEET_ROOT_KEY_SOURCE` | `file:/app/data/ca/root.key` | CA root key storage. Options: `file:`, `vault:`, `tpm2:`. |

For full reference, see `server/app/settings/config.py` in the repository.

---

## Volume Layout

hl_helper stores persistent data under `/app/data`:

```
/app/data/
├── fleet.db              # SQLite database (host records, audit log, approvals, etc.)
├── ca/
│   ├── root.key          # Root CA private key (encrypted, if using KMS)
│   ├── root.crt          # Root CA certificate
│   ├── intermediate.key  # Intermediate CA key (for signing agent certs)
│   └── intermediate.crt
├── signing/
│   ├── current.key       # Server signing key (Ed25519, for command envelopes)
│   ├── anchors/          # Retired signing keys (with grace period)
│   └── archive/          # Old keys (backup)
├── advisories/           # Downloaded CVE/advisory data (OSV, NVD, USN, etc.)
├── audit/
│   ├── checkpoints/      # Merkle checkpoint signatures
│   └── exports/          # Audit log exports (NDJSON, CSV)
└── settings.json         # Optional config overrides
```

**Backup**: Mount `/app/data` to persistent storage; back up daily. See [HA Topology: Disaster Recovery](../operations/ha-topology.md#backup-and-disaster-recovery).

---

## Exposed Ports

| Port | Protocol | Purpose | Notes |
|---|---|---|---|
| 3000 | HTTP/WSS | Web UI + WebSocket | Serve via reverse proxy for HTTPS |
| 8000 | HTTP | FastAPI control plane | `/v1/` REST endpoints, OpenAPI docs |
| 50051 | gRPC (TLS) | Agent ingress | mTLS 1.3 only; agents initiate connection |

---

## TLS & HTTPS

### Development (HTTP only)

For local testing:

```bash
docker run -d \
  --name hl_helper \
  -p 3000:3000 -p 8000:8000 -p 50051:50051 \
  -e FLEET_ADMIN_TOKEN=dev-token \
  -e FLEET_COOKIE_SECURE=false \
  -v hl_helper_data:/app/data \
  ghcr.io/hlhelper/hl_helper:latest
```

Agent connections will fail (mTLS required on 50051). For testing agents, use a reverse proxy or tunnel.

### Production (HTTPS + TLS)

Place hl_helper behind a reverse proxy (Caddy, nginx) that terminates TLS:

#### Caddy (Recommended)

```caddy
https://fleet.example.com {
  reverse_proxy localhost:8000 {
    header_uri X-Forwarded-Proto https
    header_uri X-Forwarded-For {http.request.remote}
  }
}

https://fleet.example.com:50051 {
  reverse_proxy localhost:50051 h2c
}
```

Then agents connect to `fleet.example.com:50051` (TLS handled by Caddy).

#### nginx

```nginx
upstream fleet_api {
  server localhost:8000;
}

upstream fleet_grpc {
  server localhost:50051 max_fails=3 fail_timeout=10s;
}

server {
  listen 443 ssl http2;
  server_name fleet.example.com;

  ssl_certificate /etc/ssl/certs/fleet.crt;
  ssl_certificate_key /etc/ssl/private/fleet.key;

  location / {
    proxy_pass http://fleet_api;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
  }
}

server {
  listen 50051 ssl http2;
  server_name fleet.example.com;

  ssl_certificate /etc/ssl/certs/fleet.crt;
  ssl_certificate_key /etc/ssl/private/fleet.key;

  location / {
    grpc_pass grpc://fleet_grpc;
  }
}
```

### Self-Signed Certs (Testing)

For internal networks:

```bash
# Generate self-signed cert valid for 365 days
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=fleet.local"

# Use with Caddy or nginx as above
```

Agents must be configured to trust the self-signed root:

```bash
hl-agent enroll \
  --server https://fleet.local:50051 \
  --token hlb_xxx \
  --ca-file /path/to/ca.pem
```

---

## First Run: Bootstrap Admin

On first startup, hl_helper generates a bootstrap token and prints it to logs:

```bash
docker logs hl_helper 2>&1 | grep "token="
# Output: Admin token (one-time use): token=hlb_abc123...
```

Use this token to log in via UI or CLI:

```bash
curl -H "Authorization: Bearer hlb_abc123..." http://localhost:8000/v1/hosts
```

**Important**: Change or rotate the token immediately after first login. Do not commit to version control or logs.

---

## Health Check & Readiness

hl_helper exposes a health endpoint for orchestration (Docker Compose, Kubernetes):

```bash
# Readiness (app is booted, DB is accessible)
curl http://localhost:8000/v1/health

# Output (200 OK):
# { "status": "healthy", "uptime_seconds": 123 }
```

If it returns 5xx, check logs: `docker logs hl_helper`

---

## Upgrade

1. **Backup data**:
   ```bash
   docker exec hl_helper tar czf /app/data/backup-$(date +%s).tar.gz -C /app/data .
   docker cp hl_helper:/app/data/backup-*.tar.gz ./
   ```

2. **Pull new image**:
   ```bash
   docker pull ghcr.io/hlhelper/hl_helper:latest
   ```

3. **Stop and remove**:
   ```bash
   docker stop hl_helper
   docker rm hl_helper
   ```

4. **Apply database migrations** (automatic):
   Container startup runs `alembic upgrade head` to migrate schema.

5. **Restart**:
   ```bash
   # Re-run the docker run command, or docker compose up
   docker compose up -d
   ```

6. **Verify**:
   ```bash
   docker logs hl_helper | grep "Alembic version"
   curl http://localhost:8000/v1/health
   ```

---

## Troubleshooting

### Server won't start: "CA root.key not found"

The container crashed before initializing keys. Check permissions on the volume:

```bash
docker exec hl_helper ls -la /app/data/ca/
# Should exist; if not, volume mount is broken or permissions are wrong.
```

**Fix**: Ensure volume is mounted and writable:

```bash
docker inspect hl_helper | grep -A5 Mounts
# Check "Source" and "Destination"; both should be present and readable.
```

### Agents can't connect: "TLS handshake failed"

1. **Check if port 50051 is reachable**:
   ```bash
   telnet fleet.example.com 50051
   # Should not timeout
   ```

2. **Check server logs for TLS errors**:
   ```bash
   docker logs hl_helper | grep -i "tls\|cert"
   ```

3. **Verify agent is using correct server address and TLS**:
   ```bash
   hl-agent status | grep -i "server\|cert"
   ```

4. **Confirm reverse proxy is not stripping TLS**:
   - Agents need direct mTLS to port 50051
   - Proxy must pass through TLS unchanged (not terminate it a second time)

### High memory usage

Advisory feeds (NVD, OSV, etc.) are cached in memory. First startup can use 500 MB+. If sustained >1 GB:

```bash
docker stats hl_helper
# If RSS is growing, there may be a memory leak. File a bug report.
```

Temporarily reduce feeds:

```bash
-e FLEET_ADVISORY_FEEDS="nvd,osv"  # Default loads all; this is minimal
```

### Database locked: "database is locked"

SQLite has limited concurrency. If you have many concurrent API clients:

```bash
docker logs hl_helper | grep "database is locked"
```

**Workaround**: Upgrade to Postgres:

```bash
-e FLEET_DB_URL="postgresql://user:pass@postgres:5432/fleet"
```

See [Postgres setup](../operations/ha-topology.md#multi-replica-read-scaling-supported).

---

## Next Steps

1. **Enroll agents**: [Enroll a Host](./enroll-host.md)
2. **Set up HTTPS**: Use Caddy or nginx as a reverse proxy
3. **Backup strategy**: [Disaster Recovery](../operations/ha-topology.md#backup-and-disaster-recovery)
4. **Scale to HA**: [HA Topology](../operations/ha-topology.md)

---

## References

- [Enrollment Flow](../../developer/design/enrollment.md)
- [Transport & Certs](../../developer/architecture/transport.md)
- [HA Topology & Scaling](../operations/ha-topology.md)
