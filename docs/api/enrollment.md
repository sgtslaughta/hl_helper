# Enrollment API Reference

REST API for host enrollment, install-script delivery, and host management. Auto-generated companion: `openapi.json` (full schema).

**Base URL:** `https://<server>/v1`
**Auth:** Bearer token (`FLEET_ADMIN_TOKEN`) for admin endpoints. Bootstrap tokens (`hlb_*`) consumed once for enrollment.

---

## `POST /v1/enroll`

Redeem a one-time bootstrap token; server signs the agent CSR and returns CA chain + cert + endpoint metadata.

**Request body** (`application/json`):
```json
{
  "token": "hlb_a1b2c3d4...",
  "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\n...",
  "hostname": "host-01.lan",
  "agent_pubkey": "<base64 raw Ed25519 pubkey>"
}
```

**Responses:**
- `200 OK` — `{ "host_id": "...", "cert_chain_pem": "...", "ca_chain_pem": "...", "grpc_endpoint": "host:443" }`
- `400 Bad Request` — malformed CSR or pubkey
- `410 Gone` — token expired or already redeemed (audit-logged)
- `429 Too Many Requests` — IP-level rate limit hit

**Audit:** redeem success/failure logged with `action="enrollment.redeem"` and chain-hash continuity.

**Atomicity:** redemption uses `UPDATE ... WHERE redeemed_at IS NULL` returning rowcount; concurrent attempts cannot race.

---

## `POST /v1/hosts/{host_id}:revoke`

Admin-only. Revokes the host's leaf cert (CRL hot-reload), terminates active gRPC streams, marks host quarantined.

**Auth:** `Authorization: Bearer <FLEET_ADMIN_TOKEN>`
**Response:** `204 No Content`
**Audit:** `action="host.revoke"`.

---

## `GET /v1/hosts`

Admin-only. Lists hosts with `id`, `hostname`, `enrolled_at`, `last_seen_at`, `revoked_at`, `quarantined`.

---

## `GET /install.sh`

Returns POSIX install script with `X-Install-Signature` header (Ed25519 over body).

**Query params:** `token=<hlb_*>`, `server=<host>`, `grpc_endpoint=<host:port>`.
**Diagnostics:** script aborts early with clear `gRPC port unreachable` message if `nc -z` fails on `grpc_endpoint` (catches reverse-proxies that strip HTTP/2).

---

## Error format (RFC 9457 problem+JSON)

```json
{
  "type": "/errors/<slug>",
  "title": "...",
  "status": 410,
  "detail": "...",
  "instance": "/v1/enroll",
  "trace_id": "..."
}
```

---

## Rate limiting

In-memory token bucket per source IP. Headers on response:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `Retry-After` (on 429)

Window + burst configurable via `FLEET_RATE_LIMIT_*` settings.

---

## Generated artifacts

- `docs/api/openapi.json` — full OpenAPI 3.1 spec dumped from FastAPI app.
- `docs/api/grpc.md` — agent-bridge gRPC service docs (protoc-gen-doc).

Regenerate:
```sh
.venv/bin/python -c 'import json; from server.app.api.app import create_app; print(json.dumps(create_app().openapi(), indent=2))' > docs/api/openapi.json
protoc --proto_path=proto --doc_out=docs/api --doc_opt=markdown,grpc.md proto/fleet/v1/*.proto
```
