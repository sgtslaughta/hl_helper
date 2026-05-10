---
title: Plugin System
status: planned
---

# Plugin System

!!! planned "Not yet implemented"
    This subsystem is designed but not shipped. Tracking spec: `docs/superpowers/specs/2026-05-02-hlh-c6-plugin-system-design.md`.

## Goal

Plugins are the extensibility seam: notification backends, secrets stores, advisory feeds, MFA methods, power controls (IPMI/Redfish/smart-PDU), RBAC engines, observability exporters, discovery integrations—all without touching core. The same trust model that isolates plugins from the control plane also produces verifiable supply-chain artifacts (signed bundles, SBOMs, reproducible builds) used both by third-party authors and ~40 official plugins.

## Planned scope

- OCI artifact bundles (Dockerfile-less) with cosign-signed manifests and capability allowlist; runtime types: binary (Go), Python venv, Node, JVM jar, WASM.
- Two-tier marketplace: project-Verified (audited, signed, official), Community (signed but unsupported), user-added (air-gap).
- Sandboxed runtime: bubblewrap (bwrap) default with seccomp+cgroup limits; rootless Podman recommended; optional WASM for compute-heavy pure-logic plugins.
- Capability model: declared in manifest (e.g., `outbound.https: ["*.example.com"]`, `secrets.request: ["secret://*/registries/*"]`, `hooks: ["update.pre", "update.post"]`); enforced server-side.
- Brokered secrets: plugin requests secret via UDS RPC → server validates against manifest pattern → returns handle; for outbound calls, server injects auth header without secret leaving server.
- Proxied egress: all HTTP/HTTPS outbound via server egress proxy; URL and rate-limit checked per plugin; SSRF prevention; audit-logged.
- Plugin SDK (Go, Python, TypeScript, Rust planned) with typed RPC stubs, lifecycle hooks, event subscriptions, plugin-local namespaced KV storage.
- Plugin-local Alembic schema migrations (isolated from core DB).
- ~40 official plugins: notifications (SMTP, Webhook, Discord, Slack, Telegram, ntfy, Gotify, Pushover, Apprise, Matrix), secrets (Vault, Bitwarden, 1Password, Infisical, cloud KMS), advisory feeds (Snyk, Mend.io, Tidelift, WPScan, VulnCheck), power (IPMI, Redfish, Kasa, Shelly, Tasmota, APC/Eaton PDU), observability export (Datadog, New Relic, Splunk), RBAC (Cedar policy engine).

## Architecture (planned)

Plugins are OCI artifacts signed with cosign (keyless OIDC primary, key-based fallback). On install, the artifact is pulled from a marketplace registry, signature verified, manifest extracted, and capability allowlist loaded into the plugin record. At runtime, the sandbox manager (bwrap or rootless-podman) launches the plugin binary/venv/container in an isolated namespace with only capabilities declared. Plugin process connects via UDS socket to server and calls gRPC services: `Heartbeat` (keep-alive), `SubscribeEvents` (to listen for triggers), `HookFired` (lifecycle points like `update.pre`), `Invoke` (admin-triggered actions), `EgressRequest` (HTTP proxy), `SecretsGet`/`SecretsSet` (secrets broker), `StorageGet`/`StoragePut` (plugin KV), `Log` (send logs back to server).

All calls are authenticated by UDS peer creds + manifest capability check. A misbehaving or slow plugin is sandboxed: if it hangs, only its sandbox is affected; if it requests an egress URL outside its allowlist, the proxy denies it and logs a security finding. Plugin crashes are surfaced as posture findings. Dynamic hooks are registered at startup so the manifest is canonical (no hidden side effects).

## User-facing (planned)

A Plugins page lists installed plugins with their manifest (name, description, version, icon, capabilities summary in plain English, resource limits, last-check status). A "Browse Marketplace" button opens a modal to search and filter by category (notifications, secrets, power, etc.). Each marketplace entry shows description, version, capability summary, risk badge (Verified, Community, or custom registry), author, reviews (if any), and an Install button. On install, a confirmation dialog shows required capabilities ("Can send HTTP requests to *.example.com", "Can read secrets matching secret://*/registries/*") so users understand what they're allowing. An uninstall button removes the plugin with a confirmation prompt. Admins can upload custom plugins (OCI tar + signature) or point to a custom registry.

## Open questions

- Marketplace review process and author reputation model deferred to implementation plan; official plugins reviewed by core team.

## References

- Spec: `docs/superpowers/specs/2026-05-02-hlh-c6-plugin-system-design.md`
- Related: [Power Controls](./power.md), [Update Engine](./update-engine.md), [Observability](./observability.md)
