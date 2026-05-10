---
title: Update Engine
status: planned
---

# Update Engine

!!! planned "Not yet implemented"
    This subsystem is designed but not shipped. Tracking spec: `docs/superpowers/specs/2026-05-02-hlh-c4-update-engine-design.md`.

## Goal

The Update Engine is the brain that turns "patch this group on Tuesdays at 03:00, ask before kernel jumps" into orchestrated, signed, audited work executed by agents across heterogeneous distros and language ecosystems. It turns "13 hosts are vulnerable to CVE-X right now" into a safe, rollout-managed patch campaign.

## Planned scope

- Declarative `PkgUpdate` command spec; multi-distro support (tier-1: apt/dnf/pacman; tier-2: zypper/apk/xbps/nix; tier-3: snap/flatpak/homebrew/nix-env/pipx/cargo/npm-g/asdf/mise).
- Advisory ingest from OSV, GHSA, NVD, distro security trackers, language ecosystem feeds; server-side agent-reported state matching.
- Safe-by-default rollouts: dry-run, snapshots, change-class policies, staged rings, health gates, automatic rollback.
- Live-patch awareness; reboot policy with detect-and-prompt and per-class breaking-change policy.
- Distro release upgrades supported but never automatic; multi-checkpoint guarded workflow.
- Every action signed, audited, transparent.

## Architecture (planned)

The server hosts an advisory ingest pipeline (feeds, normalization, filtering) and a matcher that correlates advisories with host inventory (reported by agents). An `UpdatePolicy` template per group specifies filters (CVE, class, severity), per-class policies (approve/block), and safety settings (snapshots, health probes, rollback). The dispatcher composes per-host envelopes from the template and group/host overrides, signs them, and ships them to agents over the gRPC bridge.

On the agent side, a PM provider registry (15+ package managers) detects the host's PM stack and translates the declarative spec into native commands. A change classifier runs dry-run output and categorizes each package update (routine, feature, kernel major, dist-upgrade, etc.) so the policy engine on the server can gate approval. If approved, pre-flight checks (snapshots, disk space, PM locks, signature verification) run, then apply, then post-flight (health probe, reboot detection, rollback on surprise, service restart, plugin hooks).

## User-facing (planned)

Operators see an Advisory page with CVE details, affected hosts, and a "patch this" button that previews the rollout plan. They can view or override the policy per group (e.g., "always approve kernel patches" → "require approval for kernel patches"). During a rollout, they monitor ring health (success %, automated pauses on threshold breach). Post-patch, they see audit entries for every host and can inspect why a host rolled back if it did.

## Open questions

- Release upgrade retry and cleanup strategy if a host partly succeeds but fails mid-flow (deferred to implementation plan).

## References

- Spec: `docs/superpowers/specs/2026-05-02-hlh-c4-update-engine-design.md`
- Related: [Exposure](/docs/_planned/exposure.md), [Posture](/docs/_planned/posture.md)
