"""Prometheus-compatible metrics for the fleet management server.

@brief Defines and registers all fleet metrics using a dedicated
       CollectorRegistry to avoid test leakage and global state conflicts.
       Metrics are gated by the FLEET_METRICS_ENABLED setting.

All metric names are prefixed with ``fleet_`` and follow the naming
conventions in the C12 Observability design spec.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

_registry = CollectorRegistry()
_initialized = False

# ---------------------------------------------------------------------------
# Gauges
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

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

fleet_agent_reconnects_total: Counter
"""@brief Total agent reconnection events."""

fleet_command_dispatched_total: Counter
"""@brief Commands dispatched, labeled by verb and risk level."""

fleet_command_completed_total: Counter
"""@brief Commands completed, labeled by verb and result."""

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

# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------

fleet_command_latency_seconds: Histogram
"""@brief Command execution latency in seconds, labeled by verb."""

fleet_update_run_duration_seconds: Histogram
"""@brief Update run duration in seconds."""

fleet_db_query_seconds: Histogram
"""@brief Database query duration in seconds, labeled by operation."""


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
    _declare_module_stubs()


def init_metrics() -> None:
    """@brief Register all fleet metrics on the dedicated registry.

    Safe to call multiple times; subsequent calls are no-ops.
    """
    global _initialized  # noqa: PLW0603
    if _initialized:
        return
    _initialized = True
    _register_all()


def _declare_module_stubs() -> None:
    """@brief Set module-level metric references to a sentinel.

    After ``reset_registry()`` the old metric objects point to a dead
    registry.  Re-bind them so attribute access doesn't blow up before
    the next ``init_metrics()`` call.
    """
    global fleet_hosts_total, fleet_host_advisory_unresolved  # noqa: PLW0603
    global fleet_session_active, fleet_audit_chain_length  # noqa: PLW0603
    global fleet_search_index_size  # noqa: PLW0603
    global fleet_agent_reconnects_total, fleet_command_dispatched_total  # noqa: PLW0603
    global fleet_command_completed_total, fleet_advisory_total  # noqa: PLW0603
    global fleet_update_run_total, fleet_plugin_egress_requests_total  # noqa: PLW0603
    global fleet_plugin_egress_bytes_total, fleet_auth_failures_total  # noqa: PLW0603
    global fleet_command_latency_seconds, fleet_update_run_duration_seconds  # noqa: PLW0603
    global fleet_db_query_seconds  # noqa: PLW0603

    # Bind to fresh (empty-registry) placeholders so tests that call
    # reset_registry() then re-init work cleanly.
    fleet_hosts_total = Gauge(
        "fleet_hosts_total", "stub", ["status"], registry=None,
    )
    fleet_host_advisory_unresolved = Gauge(
        "fleet_host_advisory_unresolved", "stub", ["severity"], registry=None,
    )
    fleet_session_active = Gauge("fleet_session_active", "stub", registry=None)
    fleet_audit_chain_length = Gauge("fleet_audit_chain_length", "stub", registry=None)
    fleet_search_index_size = Gauge(
        "fleet_search_index_size", "stub", ["index"], registry=None,
    )
    fleet_agent_reconnects_total = Counter(
        "fleet_agent_reconnects_total", "stub", registry=None,
    )
    fleet_command_dispatched_total = Counter(
        "fleet_command_dispatched_total", "stub", ["verb", "risk"], registry=None,
    )
    fleet_command_completed_total = Counter(
        "fleet_command_completed_total", "stub", ["verb", "result"], registry=None,
    )
    fleet_advisory_total = Counter(
        "fleet_advisory_total", "stub", ["severity"], registry=None,
    )
    fleet_update_run_total = Counter(
        "fleet_update_run_total", "stub", ["result"], registry=None,
    )
    fleet_plugin_egress_requests_total = Counter(
        "fleet_plugin_egress_requests_total", "stub", ["plugin", "decision"], registry=None,
    )
    fleet_plugin_egress_bytes_total = Counter(
        "fleet_plugin_egress_bytes_total", "stub", ["plugin", "direction"], registry=None,
    )
    fleet_auth_failures_total = Counter(
        "fleet_auth_failures_total", "stub", ["kind"], registry=None,
    )
    fleet_command_latency_seconds = Histogram(
        "fleet_command_latency_seconds", "stub", ["verb"], registry=None,
    )
    fleet_update_run_duration_seconds = Histogram(
        "fleet_update_run_duration_seconds", "stub", registry=None,
    )
    fleet_db_query_seconds = Histogram(
        "fleet_db_query_seconds", "stub", ["op"], registry=None,
    )


def _register_all() -> None:
    """@brief Create and bind all metric objects to the current registry."""
    global fleet_hosts_total, fleet_host_advisory_unresolved  # noqa: PLW0603
    global fleet_session_active, fleet_audit_chain_length  # noqa: PLW0603
    global fleet_search_index_size  # noqa: PLW0603
    global fleet_agent_reconnects_total, fleet_command_dispatched_total  # noqa: PLW0603
    global fleet_command_completed_total, fleet_advisory_total  # noqa: PLW0603
    global fleet_update_run_total, fleet_plugin_egress_requests_total  # noqa: PLW0603
    global fleet_plugin_egress_bytes_total, fleet_auth_failures_total  # noqa: PLW0603
    global fleet_command_latency_seconds, fleet_update_run_duration_seconds  # noqa: PLW0603
    global fleet_db_query_seconds  # noqa: PLW0603

    reg = _registry

    fleet_hosts_total = Gauge(
        "fleet_hosts_total",
        "Current host count by status",
        ["status"],
        registry=reg,
    )
    fleet_host_advisory_unresolved = Gauge(
        "fleet_host_advisory_unresolved",
        "Unresolved host advisories by severity",
        ["severity"],
        registry=reg,
    )
    fleet_session_active = Gauge(
        "fleet_session_active",
        "Number of active sessions",
        registry=reg,
    )
    fleet_audit_chain_length = Gauge(
        "fleet_audit_chain_length",
        "Current length of the audit chain",
        registry=reg,
    )
    fleet_search_index_size = Gauge(
        "fleet_search_index_size",
        "Document count per search index",
        ["index"],
        registry=reg,
    )
    fleet_agent_reconnects_total = Counter(
        "fleet_agent_reconnects_total",
        "Total agent reconnection events",
        registry=reg,
    )
    fleet_command_dispatched_total = Counter(
        "fleet_command_dispatched_total",
        "Commands dispatched by verb and risk level",
        ["verb", "risk"],
        registry=reg,
    )
    fleet_command_completed_total = Counter(
        "fleet_command_completed_total",
        "Commands completed by verb and result",
        ["verb", "result"],
        registry=reg,
    )
    fleet_advisory_total = Counter(
        "fleet_advisory_total",
        "Total advisories issued by severity",
        ["severity"],
        registry=reg,
    )
    fleet_update_run_total = Counter(
        "fleet_update_run_total",
        "Update runs completed by result",
        ["result"],
        registry=reg,
    )
    fleet_plugin_egress_requests_total = Counter(
        "fleet_plugin_egress_requests_total",
        "Plugin egress request count by plugin and decision",
        ["plugin", "decision"],
        registry=reg,
    )
    fleet_plugin_egress_bytes_total = Counter(
        "fleet_plugin_egress_bytes_total",
        "Plugin egress bytes by plugin and direction",
        ["plugin", "direction"],
        registry=reg,
    )
    fleet_auth_failures_total = Counter(
        "fleet_auth_failures_total",
        "Authentication failures by kind",
        ["kind"],
        registry=reg,
    )
    fleet_command_latency_seconds = Histogram(
        "fleet_command_latency_seconds",
        "Command execution latency in seconds",
        ["verb"],
        registry=reg,
    )
    fleet_update_run_duration_seconds = Histogram(
        "fleet_update_run_duration_seconds",
        "Update run duration in seconds",
        registry=reg,
    )
    fleet_db_query_seconds = Histogram(
        "fleet_db_query_seconds",
        "Database query duration in seconds",
        ["op"],
        registry=reg,
    )


# Initialise stubs so imports don't crash before init_metrics() is called.
_declare_module_stubs()
