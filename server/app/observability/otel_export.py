"""OTLP export configuration for the fleet server.

Manages lifecycle of OpenTelemetry exporters for traces, metrics, and logs.
When ``FLEET_OTEL_ENDPOINT`` is unset (``config`` is ``None``), exports are
disabled and no external calls are made (privacy by default).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import (
    OTLPLogExporter as HTTPOTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter as HTTPOTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HTTPOTLPSpanExporter,
)

#: Setuptools-style entry-point name reserved for OTLP/export plugins.
OBS_EXPORTER_ENTRYPOINT_NAME: str = "obs.exporter"

_obs_exporter_plugins: list[Callable[[ExportConfig], ExporterSet | None]] = []


def register_obs_exporter_plugin(
    factory: Callable[[ExportConfig], ExporterSet | None],
) -> None:
    """@brief Register a factory for the ``obs.exporter`` plugin slot.

    Factories run before the built-in OTLP path. If a factory returns a
    non-``None`` :class:`ExporterSet`, that value is used and default OTLP
    exporters are not constructed.

    @param factory Callable accepting :class:`ExportConfig` and returning
        exporters or ``None`` to fall through to defaults.
    """
    _obs_exporter_plugins.insert(0, factory)


def _clear_obs_exporter_plugins_for_tests() -> None:
    """@brief Remove all registered export plugins (test helper)."""
    _obs_exporter_plugins.clear()


@dataclass(frozen=True)
class ExportConfig:
    """@brief Configuration for OTLP export.

    @param endpoint OTLP collector target. For ``grpc``, ``host:port``. For
        ``http``, base URL including scheme (e.g. ``http://h:4318/``).
    @param headers Authentication headers (e.g. Bearer tokens).
    @param protocol Transport protocol: ``grpc`` or ``http``.
    @param insecure When True and protocol is ``grpc``, use plaintext gRPC.
    @raises ValueError If ``endpoint`` or ``protocol`` are inconsistent or invalid.
    """

    endpoint: str
    headers: dict[str, str] = field(default_factory=dict)
    protocol: str = "grpc"
    insecure: bool = False

    def __post_init__(self) -> None:
        """@brief Validate endpoint/protocol consistency after construction.

        @raises ValueError If protocol is unsupported or endpoint format mismatches.
        """
        if self.protocol not in ("grpc", "http"):
            raise ValueError(f"unsupported protocol {self.protocol!r}")
        if self.protocol == "grpc":
            tgt = self.endpoint.strip()
            if not tgt or "://" in tgt:
                raise ValueError("gRPC endpoint must be host:port without a URL scheme")
        else:
            parsed = urlparse(self.endpoint)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("HTTP OTLP endpoint must be an http(s) URL with authority")

    @staticmethod
    def from_settings(
        endpoint: str,
        headers: dict[str, str] | None = None,
    ) -> ExportConfig:
        """@brief Build :class:`ExportConfig` from settings values.

        Auto-detects protocol: ``grpc`` if ``endpoint`` starts with
        ``grpc://``, otherwise ``http``.

        @param endpoint Raw endpoint string from fleet settings.
        @param headers Optional header dict (e.g. decoded secret ref).
        @return Validated immutable export configuration.
        @raises ValueError When ``endpoint`` is empty or not a supported URL shape.
        """
        raw = endpoint.strip()
        if not raw:
            raise ValueError("otel endpoint must be non-empty")
        hdr = dict(headers) if headers else {}
        if raw.startswith("grpc://"):
            target = raw.removeprefix("grpc://").strip()
            if not target:
                raise ValueError("grpc:// endpoint missing host")
            return ExportConfig(
                endpoint=target,
                headers=hdr,
                protocol="grpc",
                insecure=False,
            )
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("HTTP OTLP endpoint must start with http:// or https://")
        normalized = raw if raw.endswith("/") else raw + "/"
        return ExportConfig(endpoint=normalized, headers=hdr, protocol="http", insecure=False)


@dataclass
class ExporterSet:
    """@brief Container for active OTLP exporters.

    @param trace_exporter Span exporter instance, or ``None`` if traces are disabled.
    @param metric_exporter Metric exporter instance, or ``None`` if metrics are disabled.
    @param log_exporter Log exporter instance, or ``None`` if log export is disabled.
    """

    trace_exporter: Any = None
    metric_exporter: Any = None
    log_exporter: Any = None


def _shutdown_maybe(exporter: Any) -> None:
    """@brief Shut down a single exporter if it is not None and has a shutdown method.

    @param exporter Exporter instance or ``None``.
    """
    if exporter is None:
        return
    shutdown = getattr(exporter, "shutdown", None)
    if callable(shutdown):
        shutdown()


def build_exporters(config: ExportConfig | None) -> ExporterSet:
    """@brief Build OTLP exporters based on ``config``.

    Consults registered :func:`register_obs_exporter_plugin` factories first.
    When none return a result, constructs gRPC or HTTP OTLP exporters from
    ``config``.

    @param config Export configuration, or ``None`` to disable export.
    @return :class:`ExporterSet` with configured exporters, or empty when
        ``config`` is ``None``.
    @raises ValueError Propagated from invalid :class:`ExportConfig`.
    """
    if config is None:
        return ExporterSet()

    for factory in list(_obs_exporter_plugins):
        custom = factory(config)
        if custom is not None:
            return custom

    if config.protocol == "grpc":
        common_kwargs: dict[str, Any] = {
            "endpoint": config.endpoint,
            "headers": config.headers or None,
        }
        if config.insecure:
            common_kwargs["insecure"] = True
        return ExporterSet(
            trace_exporter=OTLPSpanExporter(**common_kwargs),
            metric_exporter=OTLPMetricExporter(**common_kwargs),
            log_exporter=OTLPLogExporter(**common_kwargs),
        )

    http_kwargs: dict[str, Any] = {
        "endpoint": config.endpoint,
        "headers": config.headers or None,
    }
    return ExporterSet(
        trace_exporter=HTTPOTLPSpanExporter(**http_kwargs),
        metric_exporter=HTTPOTLPMetricExporter(**http_kwargs),
        log_exporter=HTTPOTLPLogExporter(**http_kwargs),
    )


def shutdown_exporters(exporters: ExporterSet) -> None:
    """@brief Gracefully shut down all active exporters in ``exporters``.

    @param exporters Exporter set to shut down. Safe when fields are ``None``.
    """
    _shutdown_maybe(exporters.trace_exporter)
    _shutdown_maybe(exporters.metric_exporter)
    _shutdown_maybe(exporters.log_exporter)
