---
title: Observability & Metrics
status: planned
---

# Observability & Metrics

!!! planned "Not yet implemented"
    This subsystem is designed but not shipped. Tracking spec: `docs/superpowers/specs/2026-05-02-hlh-c12-observability-design.md`.

## Goal

Observability provides operational visibility into fleet posture, agent health, command throughput, plugin behavior, advisory pressure, and update success. Posture findings are centralized with severity, plain-English explanation, and fix link. Audit logs are retention-aligned and exportable. Optional OpenTelemetry and Prometheus exporters serve users with existing observability stacks.

## Planned scope

- Structured JSON logging (structlog) with configurable per-module levels; optional OpenTelemetry logs export.
- Metrics: Prometheus-compatible scrape endpoint (`/metrics`, admin-gated); counters/gauges/histograms for hosts, agent reconnects, commands, advisories, updates, plugins, auth, DB queries, audit chain length.
- Tracing: OpenTelemetry instrumentation across FastAPI, SQLAlchemy, httpx, grpcio; sampling policy configurable; exportable via OTLP gRPC/HTTP.
- Centralized `PostureFinding` model: each rule produces a finding with severity, title, summary, subject kind/id, fix-action URL, docs link, suppression state.
- Findings from all components (agent cert expiry, disabled auth, sudoers modified, advisor feeds stale, plugin failures, update failures, unsupported configs).
- Audit log with hash-chained entries (SHA-256 + signed Merkle checkpoints); searchable by actor, action, timestamp, subject; exportable as JSON / CEF / RFC5424 / OTLP.
- Optional outbound: OTel logs/metrics/traces, Prometheus remote-write, Loki, S3 archive.
- Plugin slot `obs.exporter` for custom exporters (Datadog, New Relic, etc.).

## Architecture (planned)

Logging uses structlog with a configurable set of sinks (stdout, OTel, files). All log events carry trace_id, span_id, request_id, user_id, host_id where relevant. Sensitive fields (passwords, tokens, keys) are redacted by a configurable allowlist. Metrics are Prometheus counter/gauge/histogram types collected internally; when enabled, `/metrics` endpoint exposes in Prometheus text format. Tracing instruments entry points (FastAPI handlers, gRPC calls, DB queries) and propagates context via trace-id headers (W3C, jaeger, b3).

Posture findings are produced by agents (cert expiry, heartbeat staleness), the server (advisory feed sync failures, config audit), and plugins (plugin startup failures, capability violations). Each finding has a stable id (hash of subject+rule) and can be suppressed per-host or globally with reason and expiry. An audit recompute job every 15 minutes sweeps stale findings.

The audit chain is a hash-linked log where each entry includes parent hash, creating tamper-detection properties. Operator can export audit tail and verify the chain offline. Archival to S3 (optional) includes signature so historical audit is verifiable.

## User-facing (planned)

A Posture tab aggregates findings from all sources, sortable by severity, age, or subject. Each finding shows title, summary, subject (host/user/plugin/setting/global), fix-action button (deep-link), docs link, suppression state, and first/last-seen times. Administrators can suppress findings per-host or globally with required reason. An Audit page shows log entries filtered by actor/action/timestamp/subject; entries are searchable via full-text index. Export button generates JSON, CEF, or RFC5424 format. A Metrics page (if enabled) shows fleet dashboard: host status distribution, advisory trends, update success rate, agent health histogram, command latency percentiles.

## Open questions

- OTel exporter plugin SDK (Datadog, New Relic, etc.) deferred to implementation plan.

## References

- Spec: `docs/superpowers/specs/2026-05-02-hlh-c12-observability-design.md`
- Related: [Posture](./posture.md), [Plugins](./plugins.md)
