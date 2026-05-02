# hl_helper — Homelab Helper

Self-hosted, security-focused fleet manager for Linux/Unix homelabs.

> **Status:** pre-alpha. Architecture locked. C1 (Transport, Enrollment, Agent Core) — server-side foundation complete; gRPC bridge + Go agent next. Full design in `docs/superpowers/`.

---

## What it is

One control plane for many Linux/Unix hosts. Pulls together fleet update management, container ops, terminal access, power control, and observability into a single self-hosted application.

Designed for the gap between **toy auto-updaters** (Watchtower) and **enterprise tools** (Spacewalk, Foreman, Satellite). Beginner-friendly to run, hardened enough that a compromised host cannot pivot to the control plane.

---

## Why

Existing options force a tradeoff:

| Tool | Issue |
|---|---|
| Watchtower / unattended-upgrades | No verification, no audit, no rollback, no fleet view |
| Ansible / Salt | DIY everything; no UI; no pre-built update flow |
| Spacewalk / Foreman / Katello | Complex, single-distro-leaning, enterprise install footprint |
| Cockpit | Per-host UI, no fleet model |

**hl_helper:** signed commands, sandboxed plugins, multi-distro updates, hash-chained audit, modern UI, single-container default, hardened upgrade path.

---

## Features

### Transport + agent
- Go agent, single static binary, multi-arch (amd64/arm64/armv7).
- mTLS 1.3 with per-host short-lived certs (24 h TTL, SPIFFE-style URI SAN).
- Ed25519 server signing key — separate from TLS — signs every command.
- Per-host Ed25519 agent key signs every result.
- Replay protection: monotonic sequence + nonce LRU + NTP-skew clamp, persisted SQLite-backed.
- Bootstrap-token enroll (one-time, base32 with `hlb_` prefix); CSR-signed by internal CA.
- Optional SSH-only fallback for hosts where an agent isn't desired.

### Auth + RBAC
- Bootstrap token + local accounts (Argon2id) + OIDC/OAuth (Authelia, Authentik, Keycloak, GitHub, GitLab, Google, MS).
- WebAuthn / passkeys, TOTP, recovery codes.
- Role × scope RBAC; optional Cedar policy plugin for advanced cases.
- Capability tokens (biscuit-auth) on every command — host + action + resource + expiry.

### Update engine
- **Tier-1 native:** apt, dnf, pacman.
- **Tier-2 native:** zypper, apk, xbps, nix.
- **Third-party:** snap, flatpak, homebrew, nix-env, pipx, cargo, npm-g, asdf, mise.
- Advisory feeds: OSV, GHSA, NVD, USN, RHSA, Arch, Alpine, PyPA, RustSec, Go-vulndb, etc. EPSS + KEV ranking.
- Breaking-change classifier with approval gate.
- Per-host snapshot/rollback where supported (zfs, btrfs, livepatch).

### Container management
- Docker + rootless Podman discovery via host-side compose enumeration.
- Registry poll by digest, cosign signature verify, Trivy/Grype scan.
- Strategies: recreate, in-place, blue-green, pre-pull.
- Watchtower label compat.
- Docker-socket-proxy by default (no raw socket exposure).

### Plugins
- OCI artifact bundles, cosign-signed manifests, capability allowlist.
- Two-tier marketplace: project Verified + Community + user-added registries.
- Sandboxed runtime: bwrap default, rootless-podman recommended, optional WASM.
- Brokered secrets, proxied egress, declared capabilities.
- SDKs: Go, Python, TypeScript (Rust planned).

### Notifications
- Built-in: SMTP, Webhook (HMAC), Discord, Slack, Telegram, ntfy, Gotify, Pushover, Apprise, Matrix.
- Multi-source config (UI > env > file > defaults), per-key scope and lock indicators.

### Power
- Agent-tunneled reboot/shutdown (signed + approval-gated).
- Wake-on-LAN.
- Outbound webhook events; inbound webhook triggers.
- IPMI / Redfish / PDU as plugins.

### Terminal + file transfer
- Browser PTY tunneled through agent gRPC; SSH-CA fallback.
- xterm.js with WebGL, sixel, Nerd Fonts.
- Tabs, splits, broadcast, asciicast recording (hash-chained).
- Dual-pane file transfer (SCP/SFTP-equivalent) over agent.

### UI
- Next.js 15 App Router + React 19 + TypeScript strict.
- Blueprint Ops aesthetic — cyber-industrial chrome + mission-control density.
- Real data only (no decorative dummy elements).
- shadcn/Radix, TanStack Table + Query, cmdk, Framer Motion, uPlot.
- Embedded MeiliSearch for full-text across logs, hosts, audit, advisories.
- PWA + reverse-proxy aware.
- Light/dark, WCAG 2.2 AA target.

### Observability + posture
- structlog JSON to stdout; optional OTel logs/metrics/traces export.
- Prometheus-compatible `/metrics` (gated, admin-only).
- Centralized `PostureFinding` model with severity + plain-English summary + fix link.
- Hash-chained audit log (SHA-256 + signed Merkle checkpoints), exportable as JSON / CEF / RFC5424 / OTLP.

### Packaging
- **Tier 0** — single container, `docker run` to working install in <5 min, no Docker socket needed.
- **Tier 1** — hardened compose: Postgres + Redis + Caddy + Docker-socket-proxy.
- **Tier 2** — power user: Vault, MinIO, OTel collector, rootless Podman runtime.
- **Tier 3** — HA: multi-replica + external Postgres + Redis + S3 + KMS.
- Unraid Community Apps template with sane defaults + warning toggles.
- Image: distroless-friendly, multi-arch, cosign-signed, SBOM (CycloneDX + SPDX), Trivy/Grype gated.

---

## Security model (cross-cutting)

1. **Server has no unilateral root** on hosts. Agent enforces capability manifest; signed commands required; high-risk gated by approval policy.
2. **Agent is outbound-only and read-only on server state.** Cannot enumerate other hosts, cannot mutate server records.
3. **Plugins are isolated processes** with declared capabilities, brokered secrets, proxied egress, signed bundles.
4. **UI is never trusted.** All authorization decisions server-side.
5. **Cryptography:** mTLS 1.3 (TLS_AES_256_GCM_SHA384 + TLS_CHACHA20_POLY1305_SHA256 only), Ed25519 signing, biscuit capability tokens, hash-chained audit, AES-256-GCM secrets at rest with optional Vault.

User-facing transparency is a feature, not a footnote: every action carries plain-English Security Notes; first-run wizard explains the threat model in 5 screens; audit log is user-visible, filterable, exportable, hash-chain-verifiable.

Full threat model: `docs/superpowers/specs/2026-05-02-hlh-c1-transport-design.md` and per-component design docs.

---

## Architecture

```
[ Web UI (Next.js 15) ] ─WSS─ [ FastAPI control plane ] ─gRPC bidi mTLS─ [ Go agent ]
                                       │
                                       ├── SQLite (default) / Postgres (optional)
                                       ├── Plugin host (bwrap / rootless-podman / WASM)
                                       ├── Audit chain + Merkle checkpoints
                                       ├── MeiliSearch (embedded) for full-text
                                       └── Optional: Vault, Redis, OTel collector
```

| Layer | Choice |
|---|---|
| Server | Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2, structlog, grpcio |
| Agent | Go 1.23, grpc-go, ed25519, BoltDB outbox, distro-specific PM bindings |
| DB | SQLite (WAL) default; Postgres 16 optional |
| Realtime | gRPC bidi (agent ↔ server) + WSS (UI ↔ server); asyncio pub/sub default; Redis Streams optional |
| Auth | authlib (OIDC), argon2-cffi, webauthn-py, pyotp, biscuit-auth |
| Secrets | local AES-256-GCM keyring; hvac (Vault); Bitwarden / 1Password / Infisical / cloud KMS as plugins |
| Container | Distroless-friendly, multi-stage, multi-arch; cosign + SBOM + Trivy/Grype gated |

---

## Roadmap

12 components, dependency-ordered. Each has a locked design spec + implementation plan in `docs/superpowers/`.

| # | Component | Status |
|---|---|---|
| C1 | Transport, enrollment, agent core | **In progress** — server-side complete (138 tests); gRPC bridge + Go agent next |
| C2 | Control-plane API, RBAC, audit | Spec + plan complete |
| C3 | Auth + secrets broker | Spec + plan complete |
| C4 | Update engine (multi-PM) | Spec + plan complete |
| C5 | Web UI | Spec + plan complete |
| C6 | Plugin system + marketplace | Spec + plan complete |
| C7 | Docker / container management | Spec + plan complete |
| C8 | Notifications + integrations | Spec + plan complete |
| C9 | Terminal + file transfer | Spec + plan complete |
| C10 | Power controls (reboot, WOL, IPMI) | Spec + plan complete |
| C11 | Packaging + Unraid template | Spec + plan complete |
| C12 | Observability + metrics + posture | Spec + plan complete |

Build order: **C1 → C2 → C3 → (C4 ‖ C8 ‖ C10) → C7 → C9 → C6 → C5 → C11 → C12.**

### C1 progress

- [x] Repo skeleton + CI
- [x] Protobuf wire format (CommandEnvelope, ResultEnvelope, AgentBridge)
- [x] Internal CA (Ed25519, SPIFFE SAN, 24 h TTL)
- [x] Server signing backend (rotation + grace + GC)
- [x] Command envelope sign/verify + canonical bytes
- [x] Persistent replay-protection store (SQLite WAL, NTP-skew clamp)
- [x] Capability tokens (biscuit, scope + expiry)
- [x] Hash-chained audit log + Merkle checkpoints (in-memory + SQL-backed)
- [x] Multi-source settings (env > file > default, scope + redaction)
- [x] SQLAlchemy models + Alembic baseline migration
- [x] Enrollment service + `/v1/enroll` endpoint (atomic redeem, rate-limited, `hlb_` token format)
- [ ] gRPC server scaffold (mTLS 1.3 with cipher pin, SPIFFE peer-cert extractor)
- [ ] AgentBridge.Stream + per-host command queue + dispatcher + resume
- [ ] Per-host result signature verifier
- [ ] Revocation (`DELETE /v1/hosts/{id}` + stream tear-down + CRL)
- [ ] Install script (`/install.sh` + signature)
- [ ] Go agent (CLI, file/TPM2 keystore, BoltDB outbox, transport, exec runner, decommission)
- [ ] Packaging (systemd unit, per-distro sudoers, multi-arch image)
- [ ] Threat-model E2E suite

---

## Repository layout

```
hl_helper/
├── server/                 FastAPI control plane
│   ├── app/
│   │   ├── api/            REST + WS routes
│   │   ├── grpc/           agent-facing gRPC (generated _pb)
│   │   ├── auth/           OIDC, local, MFA, RBAC, capability tokens
│   │   ├── audit/          hash-chained log (in-memory + SQL)
│   │   ├── crypto/         CA, signing backend, envelope, replay store
│   │   ├── enrollment/     bootstrap token + CSR sign
│   │   ├── models/         SQLAlchemy
│   │   ├── migrations/     Alembic
│   │   └── settings/       Pydantic settings (multi-source)
│   └── tests/
├── agent/                  Go agent (skeleton — code coming)
├── proto/                  shared protobuf (agent ↔ server)
├── webui/                  Next.js 15 App Router (planned)
├── plugin-sdk/             Go / Python / TS SDKs (planned)
├── docs/
│   └── superpowers/
│       ├── specs/          12 design specs
│       └── plans/          12 implementation plans
├── deploy/                 Dockerfile + compose tiers + Unraid (planned)
└── tools/                  build, sign, sbom (planned)
```

---

## Development

Requires Python 3.12, Go 1.23, Docker (for buf + integration tests).

```bash
# Clone
git clone git@gitlab.com:richardsoto1010/hl_helper.git
cd hl_helper

# Python venv
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'

# Generate protobuf bindings (one-time)
.venv/bin/python -m grpc_tools.protoc \
  -I proto \
  --python_out=server/app/grpc/_pb \
  --grpc_python_out=server/app/grpc/_pb \
  --pyi_out=server/app/grpc/_pb \
  proto/fleet/v1/*.proto

# Apply migrations
.venv/bin/alembic upgrade head

# Run tests
.venv/bin/pytest server/tests/ -v

# Lint + type check
.venv/bin/ruff check server/
.venv/bin/mypy server/app/

# Proto lint (requires Docker)
docker run --rm -v $(pwd)/proto:/workspace -w /workspace bufbuild/buf:latest lint
```

---

## License

TBD.

---

## Contributing

Pre-alpha — interfaces in flux. Watch the C1 progress checklist above. Issues + design discussion welcome via GitLab issues.

Specs and plans live under `docs/superpowers/`. Major changes start with a brainstorming pass against the relevant component spec, not directly with code.
