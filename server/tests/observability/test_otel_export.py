"""Tests for OTLP export configuration and exporter lifecycle."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from server.app.observability import otel_export


@pytest.fixture(autouse=True)
def _clear_exporter_plugins() -> Generator[None, None, None]:
    """Ensure plugin registry does not leak between tests."""
    otel_export._clear_obs_exporter_plugins_for_tests()  # noqa: SLF001
    yield
    otel_export._clear_obs_exporter_plugins_for_tests()  # noqa: SLF001


def test_build_exporters_none_returns_empty() -> None:
    """When ``config`` is ``None``, no exporters are created."""
    result = otel_export.build_exporters(None)
    assert result.trace_exporter is None
    assert result.metric_exporter is None
    assert result.log_exporter is None


def test_build_exporters_creates_trace_metrics_logs() -> None:
    """With a valid HTTP endpoint, trace, metric, and log exporters are built."""
    cfg = otel_export.ExportConfig.from_settings("http://127.0.0.1:4318/")
    out = otel_export.build_exporters(cfg)
    assert out.trace_exporter is not None
    assert out.metric_exporter is not None
    assert out.log_exporter is not None


def test_headers_passed_to_http_exporters() -> None:
    """Authentication headers are forwarded to OTLP HTTP exporters."""
    hdrs = {"Authorization": "Bearer secret"}
    cfg = otel_export.ExportConfig.from_settings("http://127.0.0.1:4318/", hdrs)
    with (
        patch(
            "server.app.observability.otel_export.HTTPOTLPSpanExporter",
        ) as m_trace,
        patch(
            "server.app.observability.otel_export.HTTPOTLPMetricExporter",
        ) as m_metric,
        patch(
            "server.app.observability.otel_export.HTTPOTLPLogExporter",
        ) as m_log,
    ):
        otel_export.build_exporters(cfg)
    for m in (m_trace, m_metric, m_log):
        m.assert_called_once()
        assert m.call_args.kwargs.get("headers") == hdrs


def test_export_config_rejects_invalid_endpoints() -> None:
    """``ExportConfig.from_settings`` rejects malformed endpoint URLs."""
    with pytest.raises(ValueError):
        otel_export.ExportConfig.from_settings("")
    with pytest.raises(ValueError):
        otel_export.ExportConfig.from_settings("   ")
    with pytest.raises(ValueError):
        otel_export.ExportConfig.from_settings("grpc://")
    with pytest.raises(ValueError):
        otel_export.ExportConfig.from_settings("ftp://bad.example/v1/traces")


def test_export_config_post_init_validates_protocol() -> None:
    """Direct ``ExportConfig`` construction must match protocol and URL shape."""
    with pytest.raises(ValueError):
        otel_export.ExportConfig(endpoint="not-a-url", protocol="http")
    with pytest.raises(ValueError):
        otel_export.ExportConfig(endpoint="http://h/", protocol="grpc")


def test_shutdown_empty_exporters_noop() -> None:
    """``shutdown_exporters`` is safe when no exporters are active."""
    otel_export.shutdown_exporters(otel_export.ExporterSet())


def test_grpc_vs_http_exporter_selection() -> None:
    """``grpc://`` uses gRPC exporter classes; otherwise HTTP exporters are used."""
    grpc_cfg = otel_export.ExportConfig.from_settings("grpc://127.0.0.1:4317")
    with (
        patch("server.app.observability.otel_export.OTLPSpanExporter") as m_gs,
        patch("server.app.observability.otel_export.OTLPMetricExporter") as m_gm,
        patch("server.app.observability.otel_export.OTLPLogExporter") as m_gl,
        patch("server.app.observability.otel_export.HTTPOTLPSpanExporter") as m_hs,
        patch("server.app.observability.otel_export.HTTPOTLPMetricExporter") as m_hm,
        patch("server.app.observability.otel_export.HTTPOTLPLogExporter") as m_hl,
    ):
        otel_export.build_exporters(grpc_cfg)
    assert m_gs.called and m_gm.called and m_gl.called
    assert not m_hs.called and not m_hm.called and not m_hl.called

    http_cfg = otel_export.ExportConfig.from_settings("http://127.0.0.1:4318/")
    with (
        patch("server.app.observability.otel_export.OTLPSpanExporter") as m_gs2,
        patch("server.app.observability.otel_export.OTLPMetricExporter") as m_gm2,
        patch("server.app.observability.otel_export.OTLPLogExporter") as m_gl2,
        patch("server.app.observability.otel_export.HTTPOTLPSpanExporter") as m_hs2,
        patch("server.app.observability.otel_export.HTTPOTLPMetricExporter") as m_hm2,
        patch("server.app.observability.otel_export.HTTPOTLPLogExporter") as m_hl2,
    ):
        otel_export.build_exporters(http_cfg)
    assert m_hs2.called and m_hm2.called and m_hl2.called
    assert not m_gs2.called and not m_gm2.called and not m_gl2.called


def test_build_shutdown_lifecycle() -> None:
    """Building exporters and shutting them down completes without error."""
    cfg = otel_export.ExportConfig.from_settings("http://127.0.0.1:4318/")
    exporters = otel_export.build_exporters(cfg)
    otel_export.shutdown_exporters(exporters)


def test_obs_exporter_plugin_can_short_circuit() -> None:
    """The ``obs.exporter`` slot can replace default OTLP construction."""

    def plugin(_cfg: otel_export.ExportConfig) -> otel_export.ExporterSet | None:
        return otel_export.ExporterSet(
            trace_exporter=MagicMock(),
            metric_exporter=None,
            log_exporter=None,
        )

    otel_export.register_obs_exporter_plugin(plugin)
    cfg = otel_export.ExportConfig.from_settings("http://127.0.0.1:4318/")
    with (
        patch("server.app.observability.otel_export.HTTPOTLPSpanExporter") as m_hs,
        patch("server.app.observability.otel_export.HTTPOTLPMetricExporter") as m_hm,
        patch("server.app.observability.otel_export.HTTPOTLPLogExporter") as m_hl,
    ):
        out = otel_export.build_exporters(cfg)
    assert not m_hs.called and not m_hm.called and not m_hl.called
    assert out.trace_exporter is not None
    assert out.metric_exporter is None
    assert out.log_exporter is None
    otel_export.shutdown_exporters(out)
