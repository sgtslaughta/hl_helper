"""Prometheus-compatible metrics for the fleet management server.

@brief Defines and registers all fleet metrics using a dedicated
       CollectorRegistry. Metric definitions are data-driven via
       ``_METRIC_DEFS`` to avoid repetition.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

_registry = CollectorRegistry()
_initialized = False

_MetricClass = type[Counter] | type[Gauge] | type[Histogram]

_METRIC_DEFS: list[tuple[str, _MetricClass, str, list[str]]] = [
    ("fleet_hosts_total", Gauge, "Current host count by status", ["status"]),
    ("fleet_host_advisory_unresolved", Gauge, "Unresolved host advisories by severity", ["severity"]),
    ("fleet_session_active", Gauge, "Number of active sessions", []),
    ("fleet_audit_chain_length", Gauge, "Current length of the audit chain", []),
    ("fleet_search_index_size", Gauge, "Document count per search index", ["index"]),
    ("fleet_agent_reconnects_total", Counter, "Total agent reconnection events", []),
    ("fleet_command_dispatched_total", Counter, "Commands dispatched by verb and risk level", ["verb", "risk"]),
    ("fleet_command_completed_total", Counter, "Commands completed by verb and result", ["verb", "result"]),
    ("fleet_advisory_total", Counter, "Total advisories issued by severity", ["severity"]),
    ("fleet_update_run_total", Counter, "Update runs completed by result", ["result"]),
    (
        "fleet_plugin_egress_requests_total",
        Counter,
        "Plugin egress request count by plugin and decision",
        ["plugin", "decision"],
    ),
    (
        "fleet_plugin_egress_bytes_total",
        Counter,
        "Plugin egress bytes by plugin and direction",
        ["plugin", "direction"],
    ),
    ("fleet_auth_failures_total", Counter, "Authentication failures by kind", ["kind"]),
    ("fleet_command_latency_seconds", Histogram, "Command execution latency in seconds", ["verb"]),
    ("fleet_update_run_duration_seconds", Histogram, "Update run duration in seconds", []),
    ("fleet_db_query_seconds", Histogram, "Database query duration in seconds", ["op"]),
]

# ---------------------------------------------------------------------------
# Module-level type annotations for IDE support and test access
# ---------------------------------------------------------------------------

fleet_hosts_total: Gauge
"""@brief Current host count by status."""

fleet_host_advisory_unresolved: Gauge
"""@brief Unresolved host advisories by severity."""

fleet_session_active: Gauge
"""@brief Number of active sessions."""

fleet_audit_chain_length: Gauge
"""@brief Current length of the audit chain."""

fleet_search_index_size: Gauge
"""@brief Document count per search index."""

fleet_agent_reconnects_total: Counter
"""@brief Total agent reconnection events."""

fleet_command_dispatched_total: Counter
"""@brief Commands dispatched by verb and risk level."""

fleet_command_completed_total: Counter
"""@brief Commands completed by verb and result."""

fleet_advisory_total: Counter
"""@brief Total advisories issued by severity."""

fleet_update_run_total: Counter
"""@brief Update runs completed by result."""

fleet_plugin_egress_requests_total: Counter
"""@brief Plugin egress request count by plugin and decision."""

fleet_plugin_egress_bytes_total: Counter
"""@brief Plugin egress bytes by plugin and direction."""

fleet_auth_failures_total: Counter
"""@brief Authentication failures by kind."""

fleet_command_latency_seconds: Histogram
"""@brief Command execution latency in seconds."""

fleet_update_run_duration_seconds: Histogram
"""@brief Update run duration in seconds."""

fleet_db_query_seconds: Histogram
"""@brief Database query duration in seconds."""


def _apply_metrics(registry: CollectorRegistry | None) -> None:
    """@brief Create metrics from _METRIC_DEFS and bind to module globals.

    @param registry Registry to register with, or None for unregistered stubs.
    """
    g = globals()
    for name, cls, desc, labels in _METRIC_DEFS:
        kwargs: dict[str, Any] = {"registry": registry}
        if labels:
            g[name] = cls(name, desc, labels, **kwargs)
        else:
            g[name] = cls(name, desc, **kwargs)


def get_registry() -> CollectorRegistry:
    """@brief Return the dedicated metrics registry.

    @return The CollectorRegistry used for all fleet metrics.
    """
    return _registry


def reset_registry() -> None:
    """@brief Destroy and recreate the registry, clearing all metrics.

    Intended for test isolation. After calling this, callers must call
    ``init_metrics()`` to re-register metrics.
    """
    global _registry, _initialized  # noqa: PLW0603
    _registry = CollectorRegistry()
    _initialized = False
    _apply_metrics(None)


def init_metrics() -> None:
    """@brief Register all fleet metrics on the dedicated registry.

    Safe to call multiple times; subsequent calls are no-ops.
    """
    global _initialized  # noqa: PLW0603
    if _initialized:
        return
    _initialized = True
    _apply_metrics(_registry)


_apply_metrics(None)
