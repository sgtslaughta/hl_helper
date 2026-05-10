---
title: Exposure
status: partial
---

# Exposure

!!! planned "Partially implemented"
    Agent runtime-exposure collection and server derivation shipped; per-interface net metrics in progress. Tracking spec: `docs/superpowers/specs/2026-05-09-runtime-exposure-and-net-iface-design.md`.

## Goal

Vulnerability scoring often treats all advisories equally regardless of whether the vulnerable package is actually running and exposed. The Exposure subsystem addresses two gaps: (1) per-advisory exposure tier (network-exposed, active process, installed-only, unknown) to weight vulnerability risk accordingly, and (2) per-interface network metrics (bandwidth, link state, errors) so operators can see which NICs are saturated, down, or erroring.

## Planned scope

- Agent collects runtime exposure (processes, listening sockets, established connections, services, kernel modules, loaded libraries, container exposure) on configurable schedule (default tied to posture scan cadence).
- Server derives per-advisory exposure tier and multiplier (NETWORK_EXPOSED ×2.0, ACTIVE ×1.5, INSTALLED_ONLY ×0.5, UNKNOWN ×1.0) to adjust CVE weight in risk scoring.
- Operators see exposure tier on advisory rows, evidence (e.g., "listening on 0.0.0.0:443") in advisory detail, and per-host exposure breakdown.
- Operator override of tier multipliers via settings.
- Heartbeat carries per-interface net metrics (rate, link state, errors, addresses)—lightweight (<1ms CPU, ~250 bytes wire per heartbeat).
- Hardware tab renders per-interface bandwidth strip with sparkline, link state, error counts.

## Architecture (planned)

Flow A (heavy, scheduled): Agent posture scan collects processes, listeners, connections, services, loaded libs, kmods, containers. Agent reverse-looks up file paths to packages (via `dpkg -S`, `rpm -qf`, `apk info -W`) and ships `RuntimeExposure` proto. Server derives `{host_id, advisory_id, tier, evidence, scanned_at}` rows and persists to `host_advisory_exposure` table. Tiers are computed via matching rules: loaded-lib match → ACTIVE, listener on non-loopback → NETWORK_EXPOSED, etc. Risk pipeline reads tiers and applies multiplier.

Flow B (light, every heartbeat): Agent samples `/proc/net/dev` (Linux) or `getifaddrs` (macOS) and deltas compute per-iface rx_bps / tx_bps / errors / link state. Shipped as `repeated NetInterface` on heartbeat. Server persists to `Host.metrics` JSON. UI Hardware tab renders per-iface strip with sparklines.

## User-facing (planned)

On advisory detail, a badge shows "NETWORK_EXPOSED" or "INSTALLED_ONLY" with tooltip explaining the multiplier ("CVSS 7.5 × 2.0 = 15.0 effective"). Evidence list shows "listening on 192.168.1.100:443 (nginx pid 1234)". On the host risk detail page, a sub-section shows exposure breakdown by tier (how many advisories in each category). On the Hardware tab, operators see a per-NIC bandwidth strip (current rate, sparkline over last hour), UP/DOWN status, error count, and assigned addresses.

## Open questions

- Cross-host correlation of connections (would require flow aggregation pipeline) is deferred to future spec.

## References

- Spec: `docs/superpowers/specs/2026-05-09-runtime-exposure-and-net-iface-design.md`
- Related: [Posture](/docs/_planned/posture.md), [Update Engine](/docs/_planned/update-engine.md)
