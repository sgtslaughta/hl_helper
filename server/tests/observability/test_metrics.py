"""Tests for the fleet Prometheus metrics module.

@brief Validates metric registration, counter/gauge/histogram operations,
       label conformance, and registry reset behavior.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from server.app.observability import metrics as mod


EXPECTED_METRICS: list[str] = [
    "fleet_hosts_total",
    "fleet_agent_reconnects_total",
    "fleet_command_dispatched_total",
    "fleet_command_completed_total",
    "fleet_command_latency_seconds",
    "fleet_advisory_total",
    "fleet_host_advisory_unresolved",
    "fleet_update_run_total",
    "fleet_update_run_duration_seconds",
    "fleet_plugin_egress_requests_total",
    "fleet_plugin_egress_bytes_total",
    "fleet_auth_failures_total",
    "fleet_session_active",
    "fleet_db_query_seconds",
    "fleet_audit_chain_length",
    "fleet_search_index_size",
]

EXPECTED_LABELS: dict[str, tuple[str, ...]] = {
    "fleet_hosts_total": ("status",),
    "fleet_agent_reconnects_total": (),
    "fleet_command_dispatched_total": ("verb", "risk"),
    "fleet_command_completed_total": ("verb", "result"),
    "fleet_command_latency_seconds": ("verb",),
    "fleet_advisory_total": ("severity",),
    "fleet_host_advisory_unresolved": ("severity",),
    "fleet_update_run_total": ("result",),
    "fleet_update_run_duration_seconds": (),
    "fleet_plugin_egress_requests_total": ("plugin", "decision"),
    "fleet_plugin_egress_bytes_total": ("plugin", "direction"),
    "fleet_auth_failures_total": ("kind",),
    "fleet_session_active": (),
    "fleet_db_query_seconds": ("op",),
    "fleet_audit_chain_length": (),
    "fleet_search_index_size": ("index",),
}


@pytest.fixture(autouse=True)
def _clean_registry() -> Generator[None, None, None]:
    """@brief Reset the metrics registry before and after each test."""
    mod.reset_registry()
    mod.init_metrics()
    yield
    mod.reset_registry()


def _scraped_text() -> str:
    """@brief Scrape the registry and return the raw text output."""
    from prometheus_client import generate_latest

    return generate_latest(mod.get_registry()).decode("utf-8")


def _scraped_names() -> set[str]:
    """@brief Scrape the registry and return metric family names.

    Counter families in the Prometheus parser omit ``_total`` and add
    a ``_created`` family, so we reconstruct the canonical names by
    checking the raw text for ``# HELP <name>`` lines.
    """
    output = _scraped_text()
    names: set[str] = set()
    for line in output.splitlines():
        if line.startswith("# HELP "):
            name = line.split()[2]
            names.add(name)
    return names


class TestMetricRegistration:
    """@brief All 16 spec metrics must be present in the registry."""

    def test_all_metrics_registered(self) -> None:
        """@brief Every expected metric name appears in the scraped output."""
        names = _scraped_names()
        for name in EXPECTED_METRICS:
            assert name in names, f"metric {name!r} not found in registry"

    def test_metric_count(self) -> None:
        """@brief Exactly 16 fleet_ metrics are registered (excluding _created)."""
        names = {
            n for n in _scraped_names()
            if n.startswith("fleet_") and not n.endswith("_created")
        }
        assert len(names) == 16


class TestCounterOperations:
    """@brief Counter increment must reflect in the scraped output."""

    def test_counter_increment(self) -> None:
        """@brief Incrementing a counter increases its value by 1."""
        mod.fleet_agent_reconnects_total.inc()
        mod.fleet_agent_reconnects_total.inc()
        assert mod.fleet_agent_reconnects_total._value.get() == 2.0  # noqa: SLF001

    def test_labeled_counter_increment(self) -> None:
        """@brief Incrementing a labeled counter with specific labels works."""
        mod.fleet_command_dispatched_total.labels(verb="reboot", risk="high").inc()
        val = mod.fleet_command_dispatched_total.labels(
            verb="reboot", risk="high"
        )._value.get()  # noqa: SLF001
        assert val == 1.0


class TestGaugeOperations:
    """@brief Gauge set / inc / dec must update correctly."""

    def test_gauge_set(self) -> None:
        """@brief Setting a gauge reflects the value."""
        mod.fleet_session_active.set(42)
        assert mod.fleet_session_active._value.get() == 42.0  # noqa: SLF001

    def test_gauge_inc_dec(self) -> None:
        """@brief Inc and dec modify the gauge value additively."""
        mod.fleet_session_active.set(10)
        mod.fleet_session_active.inc()
        mod.fleet_session_active.dec(3)
        assert mod.fleet_session_active._value.get() == 8.0  # noqa: SLF001

    def test_labeled_gauge(self) -> None:
        """@brief Labeled gauge set and retrieval works."""
        mod.fleet_hosts_total.labels(status="online").set(5)
        val = mod.fleet_hosts_total.labels(status="online")._value.get()  # noqa: SLF001
        assert val == 5.0


class TestHistogramOperations:
    """@brief Histogram observe must record values."""

    def test_histogram_observe(self) -> None:
        """@brief Observing a value creates a count and sum."""
        mod.fleet_command_latency_seconds.labels(verb="reboot").observe(0.5)
        mod.fleet_command_latency_seconds.labels(verb="reboot").observe(1.5)

        from prometheus_client import generate_latest

        output = generate_latest(mod.get_registry()).decode("utf-8")
        assert "fleet_command_latency_seconds_count" in output
        assert "fleet_command_latency_seconds_sum" in output

    def test_unlabeled_histogram(self) -> None:
        """@brief Unlabeled histogram observe works."""
        mod.fleet_update_run_duration_seconds.observe(12.3)
        from prometheus_client import generate_latest

        output = generate_latest(mod.get_registry()).decode("utf-8")
        assert "fleet_update_run_duration_seconds_count" in output


class TestRegistryReset:
    """@brief reset_registry must clear all metric state."""

    def test_reset_clears_metrics(self) -> None:
        """@brief After reset, re-scrape shows no fleet_ metrics until re-init."""
        mod.fleet_session_active.set(99)
        mod.reset_registry()
        from prometheus_client import generate_latest

        output = generate_latest(mod.get_registry()).decode("utf-8")
        fleet_lines = [
            ln for ln in output.splitlines()
            if ln.startswith("# HELP fleet_")
        ]
        assert len(fleet_lines) == 0

    def test_reinit_after_reset(self) -> None:
        """@brief Re-initializing after reset restores all metrics."""
        mod.reset_registry()
        mod.init_metrics()
        names = _scraped_names()
        for name in EXPECTED_METRICS:
            assert name in names


class TestLabelConformance:
    """@brief Verify label names match spec to prevent high-cardinality drift."""

    def test_label_names_match_spec(self) -> None:
        """@brief Each metric's label names match the expected set exactly."""
        for name, expected_labels in EXPECTED_LABELS.items():
            metric_obj = getattr(mod, name)
            actual = tuple(metric_obj._labelnames)  # noqa: SLF001
            assert actual == expected_labels, (
                f"{name}: labels {actual} != expected {expected_labels}"
            )

    def test_no_host_id_labels(self) -> None:
        """@brief No metric has a 'host_id' label (high-cardinality guard)."""
        for name in EXPECTED_METRICS:
            metric_obj = getattr(mod, name)
            assert "host_id" not in metric_obj._labelnames, (  # noqa: SLF001
                f"{name} has forbidden high-cardinality label 'host_id'"
            )
