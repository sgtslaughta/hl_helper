---
title: Power Controls
status: planned
---

# Power Controls

!!! planned "Not yet implemented"
    This subsystem is designed but not shipped. Tracking spec: `docs/superpowers/specs/2026-05-02-hlh-c10-power-design.md`.

## Goal

Power operations are high-blast-radius. Every reboot and shutdown must be signed, gated by approval policy, and audited. Wake-on-LAN must work on offline hosts. Power events emit outbound webhooks for external automation; inbound webhooks (signed) can request power actions subject to RBAC.

## Planned scope

- Agent-mediated reboot/shutdown via signed `Reboot` / `Shutdown` envelopes; approval-gated per policy.
- Wake-on-LAN for offline hosts (server sends magic packet UDP9; optionally SecureOn password).
- Power events emit outbound webhooks (`host.power.requested`, `host.power.completed`, `host.power.failed`) with HMAC-SHA256 signing.
- Inbound webhooks (signed) can trigger power actions; subject to RBAC and approval policy.
- IPMI/Redfish/Kasa/Shelly/Tasmota/PDU vendors as verified-registry plugins.
- Pre-reboot hooks: drain services, notify, run plugin hooks.
- Post-reboot verification: agent reconnection wait with timeout; mark degraded if missed.

## Architecture (planned)

Reboot and shutdown are regular commands: dispatcher signs them, ships to agent, agent acknowledges and schedules via `shutdown -r` or `systemctl reboot`. Wake-on-LAN is server-side only (no agent needed); server sends magic packet UDP9 to configured broadcast subnets and verifies host returns within timeout (180s default). Power events are published to a webhook dispatcher which invokes registered outbound endpoints with signed HMAC payload. Inbound webhooks go through the same dispatcher/RBAC/approval flow as UI-initiated commands.

Plugin slot `power.execute` allows vendors (IPMI, Redfish, Kasa, Shelly, Tasmota, APC/Eaton PDU) to extend support for BMC and smart-PDU operations without core changes. Each plugin declares egress allowlist and secret refs (creds).

## User-facing (planned)

On the host overview, a Power section shows current power state, last-seen timestamp, and action buttons: Reboot, Shutdown, Wake-on-LAN (if offline and WOL configured). Clicking an action opens a confirmation dialog with reason field. For high-risk operations (reboot), approval may be required before execution. Power history shows past reboots, shutdowns, and their reasons (mapped to update runs or admin actions). Settings page controls reboot delay (for maintenance window), approval policy per operation, and WOL broadcast subnet config.

## Open questions

- BMC credential rotation and auto-discovery (Redfish endpoint enumeration) deferred to implementation plan.

## References

- Spec: `docs/superpowers/specs/2026-05-02-hlh-c10-power-design.md`
- Related: [Update Engine](/docs/_planned/update-engine.md), [Plugins](/docs/_planned/plugins.md)
