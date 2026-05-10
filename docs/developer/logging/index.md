---
title: Agent Logging
status: stable
---

# Agent Logging System

The agent emits structured activity logs using the ECS (Elastic Common Schema) standard, piggybacked on heartbeat frames with built-in compression and deduplication.

## Emit API

Agent plugins and core components emit logs by calling the Go logging API:

```go
// Log interface signature
type Logger interface {
	Log(ctx context.Context, level string, action string, opts ...LogOption) error
}

// Usage example
logger.Log(ctx, "info", "task.exec.completed",
	WithCategory("task"),
	WithOutcome("success"),
	WithMessage("Task finished successfully"),
	WithDuration(time.Second * 5),
	WithDetail("rc", 0),
)
```

### Log Levels

- `debug` — detailed diagnostic info (sampled by default)
- `info` — normal operations (user-facing events)
- `warn` — warnings, potential issues (always emitted)
- `error` — failures, exceptions (always emitted)
- `critical` — severe errors, security incidents (always emitted)

### ECS Field Map

Core fields emitted by all logs:

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `@timestamp` | ISO 8601 | `2026-05-10T22:15:03Z` | Event time |
| `host.name` | string | `prod-web-01` | FQDN or instance ID |
| `agent.id` | string | `a1b2c3d4e5f6` | Agent UUID |
| `agent.version` | string | `1.2.3` | Agent release version |
| `event.action` | string | `task.exec.completed` | Hierarchical action name |
| `event.category` | string | `task` | Plugin category (registered) |
| `event.outcome` | enum | `success`, `failure`, `unknown` | Operation result |
| `event.duration` | nanoseconds | `1843000000` | Elapsed time (int64) |
| `message` | string | `Task finished successfully` | Human-readable summary |
| `log.level` | enum | `info` | DEBUG, INFO, WARN, ERROR, CRITICAL |
| `error.code` | string | `EACCES` | Application error code |
| `error.message` | string | `Permission denied` | Error summary |
| `error.stack_trace` | string | `at fn() in file.go:42` | Stack trace (optional) |

Additional fields passed via `WithDetail()` are placed in a `details` map (JSON object).

## Plugin Category Registration

Plugins must register their log categories at initialization:

```go
// In plugin's Setup() function
plugin.RegisterCategory("my-category", &CategoryMeta{
	Description: "Custom plugin events",
	DefaultLevel: "info",
	SampleRate: 1.0, // 1 = 100% (no sampling)
})

// Then emit logs in that category
logger.Log(ctx, "info", "my-category.action",
	WithCategory("my-category"),
	WithMessage("Something happened"),
)
```

### Categories

Common built-in categories:

- `host` — enrollment, heartbeat health, disconnection
- `task` — task execution (start, progress, completion, failure)
- `plugin` — plugin lifecycle (load, unload, error)
- `transport` — gRPC connection, authentication events
- `system` — host OS events (boot, shutdown, policy change)

## Redactor & Sink Plugins

Logs pass through redaction and sink chains before transmission:

### Redactor Slots

```go
type Redactor interface {
	Redact(row *LogRow) error
}

// Example: strip secrets from message
plugin.RegisterRedactor(func(row *LogRow) error {
	if strings.Contains(row.Message, "password") {
		row.Message = "[REDACTED]"
	}
	return nil
})
```

### Sink Slots

```go
type Sink interface {
	Write(ctx context.Context, rows []*LogRow) error
}

// Example: send errors to syslog
plugin.RegisterSink(func(ctx context.Context, rows []*LogRow) error {
	for _, row := range rows {
		if row.Level == "error" || row.Level == "critical" {
			syslog.Println(row.Message)
		}
	}
	return nil
})
```

Sinks are called **before** server transmission, enabling local-first filtering and alternate backends.

## Heartbeat Piggyback

Logs are batched and sent with heartbeat frames (max 64 KB per frame):

1. Agent emits log → stored in in-memory ring buffer
2. Heartbeat timer fires (~5s) → drain buffer, compress with gzip, include in frame
3. On ERROR/CRITICAL → flush immediately (off-cycle)
4. Server receives frame → validate, redact, dedup, broadcast to subscribers

Compression is transparent to plugins.

## Related

- [Activity Logs User Guide](../../user-guide/logs/index.md) — end-user reference
- [Logging Design Spec](../../_planned/2026-05-10-agent-logging-design.md) — system architecture & retention
- [Logs REST API](../api/logs.md) — server endpoints
