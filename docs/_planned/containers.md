---
title: Container Management
status: planned
---

# Container Management

!!! planned "Not yet implemented"
    This subsystem is designed but not shipped. Tracking spec: `docs/superpowers/specs/2026-05-02-hlh-c7-docker-mgmt-design.md`.

## Goal

Container fleet (media stacks, dashboards, Vaultwarden, Home Assistant, Immich) needs safe, auditable, flexible updates. Container Management discovers Docker and Podman stacks, detects upstream updates by digest (not tag), applies strategies (recreate, in-place, blue-green), gates on healthchecks and vulnerability scans, and verifies signatures—all safely, with audit trail and rollback.

## Planned scope

- Docker + Podman + compose stack discovery via host-side compose enumeration; no server-side storage of compose files.
- Upstream update detection by digest (handles `:latest` correctly); multi-arch support via host architecture.
- Update strategies: recreate, in-place, blue-green, pre-pull-only, manual; per-container/stack configurable via labels and settings.
- Healthcheck-gated rollouts with automatic rollback on health probe failure.
- Cosign keyless OIDC + key-based + Notary v2 signature verification (warn/block/require modes).
- Trivy or Grype scan on pull; gate on new criticals per policy.
- Watchtower label compatibility for migration path.
- Registry credentials via secrets broker (never plaintext on agent); short-lived bearer tokens.
- Air-gap-friendly via optional server-side registry cache and pull proxy.

## Architecture (planned)

Agent discovers compose files via inotify watch (or cadence scan) on admin-configurable paths. Per compose file, it parses service list and image refs. Container inventory (`docker ps -a` / `podman ps -a`) is reported as deltas. Server tracks digest per image and polls registry manifest HEAD at configurable interval (6h jittered) to detect upstream updates. Admin picks a container and confirms update; server constructs an update command with chosen strategy, signs it, ships it to agent. Agent pre-flight checks (snapshot, disk space, image signature verify, scan for new criticals), applies the strategy (recreate = pull-stop-rm-run, blue-green = start-new-wait-healthy-swap-stop-old), post-flight (healthcheck, compare drift, rollback if needed).

Registry auth is mediated: agent requests `RegistryAuth(host)` → server resolves secret → returns short-lived bearer token (via registry token-service or server-side credential exchange). For air-gap, agent requests image blobs from server; server pulls upstream once, caches on disk (LRU), streams to agent.

## User-facing (planned)

Operators see a Containers tab listing all stacks and standalone containers. Each shows image ref, current digest, latest-available digest, strategy, last-update status, and healthcheck result. A "Check for updates" button polls registries; an "Update now" button applies the chosen strategy. Update history shows digest changes, rollback events, and scan results. Settings page controls per-registry signature policy, scan gating, healthcheck timeout, and update strategy defaults. Drift detection alerts operators when a running config differs from the managed baseline.

## Open questions

- Kubernetes integration is deferred to v1.x plugin; read-only watch possible but not in this spec.

## References

- Spec: `docs/superpowers/specs/2026-05-02-hlh-c7-docker-mgmt-design.md`
- Related: [Update Engine](/docs/_planned/update-engine.md), [Plugins](/docs/_planned/plugins.md)
