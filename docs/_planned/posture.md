---
title: Posture
status: partial
---

# Posture

!!! planned "Partially implemented"
    Core data model and findings system shipped; advanced risk aggregation and plugin scorers in progress. Tracking spec: `docs/superpowers/specs/2026-05-09-posture-risk-aggregator-design.md`.

## Goal

Posture aggregates multi-pillar signals—vulnerabilities, misconfigurations, identity & access, and operational hygiene—into a single 0–100 score with per-pillar breakdown and a confidence model that reflects what we actually know. The score is honest about gaps; a brand-new host with no scans yet is reported as "unknown" rather than falsely reassuring. Operators see not just the number but the drivers (which CVEs matter most, which config rules are firing) and can tune pillar weights without redeploying.

## Planned scope

- Multi-pillar risk aggregation with four builtin scorers (vulnerabilities, configuration, identity, hygiene) plus plugin slot for custom scorers (exposure, compliance).
- Confidence model: data_present × freshness × coverage so missing signals reduce confidence, not inflate the score.
- Calm-by-default level mapping (0=minimal, 1–15=stable, 16–35=moderate, 36–55=elevated, 56–75=high, 76–100=severe).
- Per-host `host_risk` table storing score, level, per-pillar breakdown, computed timestamp, inputs hash.
- Automatic recompute on advisory match, finding change, agent update, cert renewal, or periodic (15-min) sweep.
- API endpoints for reading risk, triggering recompute, and admin override of pillar weights.
- UI host overview gauge powered by `/v1/hosts/{id}/risk`; hover panel showing per-pillar bars and confidence dots; detail page with driver list and coverage notes.

## Architecture (planned)

A plugin protocol (`PostureScorer`) defines the interface: each scorer reports a `SubScore` with numeric score, confidence (0–1), drivers (top contributors), and coverage notes. The aggregator loads registered scorers at startup, runs each against a `ScoreContext` (host record, advisories, findings, survey, agent state) within a timeout, and blends them: `Σ(score · weight · confidence) / Σ(weight · confidence)`. A debounce window prevents thrashing; an `inputs_hash` short-circuits identical recomputes. A floor guard ensures a single confirmed hot pillar (score ≥70, confidence ≥0.7) cannot be masked by a quiet majority.

Each pillar applies its own saturation curve (e.g., vulnerabilities use a log-like shape, configuration caps noisy rules at 35). Hysteresis prevents level flapping on borderline scores. Every recompute is audit-logged with the trigger reason and inputs hash so changes are traceable.

## User-facing (planned)

On the host overview, operators see a gauge needle, a big risk number, and a plain-English level label (e.g., "Moderate — review"). Hovering shows per-pillar bars, each with a confidence dot: full (fresh data), half (older data), empty (missing data). Clicking opens the risk detail page with sortable pillar breakdown, per-driver evidence links, coverage gaps, and a recompute button. A disclaimer explains what the model does and doesn't see (no firewall, EDR, network exposure modeling), and a Settings page lets admins adjust pillar weights and preview the effect on selected hosts.

## Open questions

- Phase 2 items (90-day history sparkline, network exposure scorer data source, compliance scorer ruleset) are deferred.

## References

- Spec: `docs/superpowers/specs/2026-05-09-posture-risk-aggregator-design.md`
- Related: [Exposure](./exposure.md), [Observability](./observability.md)
