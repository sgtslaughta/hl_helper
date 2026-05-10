---
title: Activity Logs
status: stable
---

# Activity Logs

Search, filter, and analyze activity logs from all managed hosts. HL Helper provides two views: a per-host Activity tab and the centralized Logs Hub.

## Activity Tab

Each host detail page includes an **Activity** tab showing recent events on that host:

- **Live tail** — new events stream in real-time as they occur
- **Search & filter** — narrow by level, category, or free-text message
- **Outcome glyph** — success (✓), failure (✗), or unknown (—)
- **Duration** — elapsed time for operations (e.g., task execution)
- **JSON detail** — click any row to inspect full event details

### Features

- **Auto-scroll** — toggle to follow new events or pause to inspect older ones
- **Level badges** — DEBUG, INFO, WARN, ERROR, CRITICAL with color coding
- **Relative timestamps** — hover for absolute ISO time
- **Pagination** — paginate through historical events (no cursor pagination on per-host view yet)

## Logs Hub

The centralized **Logs Hub** (`/logs`) provides advanced search and analytics across all hosts:

- **Filter rail** — time range, hosts (comma-separated), level, categories, free-text search
- **Timeline histogram** — 60-bar density view; errors highlighted in red
- **Results table** — sortable columns (TS, host, level, action, outcome, message)
- **Facets panel** — top-5 buckets per facet (category, host, action, etc.)
- **Detail drawer** — click any row to open side panel with full JSON + copy button

### Policy Overrides

Temporarily increase log verbosity for debugging:

```bash
curl -X POST http://localhost:8080/v1/logs/policy/host/my-host/temp \
  -H "Content-Type: application/json" \
  -d '{
    "level": "debug",
    "categories": ["task", "plugin"],
    "ttl_s": 300
  }'
```

The agent applies the override on the next heartbeat. After TTL expires, reverts to default policy.

## Retention

- **Hot storage** — 30 days in PostgreSQL, available via REST API
- **Archive** — older logs written to NDJSON files (S3 or local disk)
- **Query job** — use `/v1/logs/archive/query` to search archived logs (returns job_id)

Retention windows are configurable per scope (global, tag, host) via policy docs.

## Related

- [Agent Logging Design](../../_planned/2026-05-10-agent-logging-design.md) — technical architecture
- [Logging API](../api/logs.md) — REST endpoints and WebSocket formats
