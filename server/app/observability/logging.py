"""Structured logging configuration for the fleet server.

Configures structlog with JSON rendering, sensitive-field redaction,
and optional OpenTelemetry log context injection.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, cast

import structlog
from opentelemetry import trace
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from structlog.stdlib import ProcessorFormatter
from structlog.typing import EventDict, Processor

_REDACT_FIELDS_ACTIVE: frozenset[str]
_STDOUT_HANDLER: logging.Handler | None = None
_OTEL_LOG_HANDLER: LoggingHandler | None = None
_OTEL_LOG_PROVIDER: LoggerProvider | None = None
_HANDLER_TAG = "_fleet_obs_handler"

#: Canonical keys whose values are replaced with ``***`` at the log sink.
REDACT_FIELDS: frozenset[str] = frozenset({
    "password",
    "token",
    "secret",
    "authorization",
    "cookie",
    "api_key",
    "private_key",
    "secrets_root_key_b64",
    "vault_token",
    "admin_token",
    "session_signing_key_ref",
})

_REDACT_FIELDS_ACTIVE = REDACT_FIELDS


def _level_from_name(name: str) -> int:
    """@brief Map a log level name to the stdlib numeric level.

    @param name Level string (e.g. ``info``, ``warning``), case-insensitive.
    @return ``logging`` level constant.
    @raises ValueError If ``name`` is not a recognized log level.
    """
    n = name.upper()
    if n == "WARN":
        n = "WARNING"
    mapping = logging.getLevelNamesMapping()
    if n not in mapping:
        msg = f"unknown log level: {name!r}"
        raise ValueError(msg)
    return mapping[n]


def _normalize_redact_fields(fields: frozenset[str] | None) -> frozenset[str]:
    """@brief Resolve the active redaction field set.

    @param fields Caller override, or ``None`` for ``REDACT_FIELDS``.
    @return Frozenset of lowercase field names used for matching.
    """
    base = REDACT_FIELDS if fields is None else fields
    return frozenset(f.lower() for f in base)


def add_trace_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """@brief structlog processor: inject trace_id and span_id from OTel context.

    @param logger Wrapped stdlib logger (unused).
    @param method_name Log method name (unused).
    @param event_dict Mutable event dictionary for the log record.
    @return Updated ``event_dict`` with ``trace_id`` and ``span_id`` strings.
    """
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    else:
        event_dict.setdefault("trace_id", "")
        event_dict.setdefault("span_id", "")
    return event_dict


def redact_sensitive(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """@brief structlog processor: replace values for sensitive field names with '***'.

    @param logger Wrapped logger (unused).
    @param method_name Log method name (unused).
    @param event_dict Mutable structlog event dictionary.
    @return ``event_dict`` with redacted top-level keys.
    """
    for key in list(event_dict.keys()):
        if key.startswith("_"):
            continue
        lk = key.lower() if isinstance(key, str) else str(key).lower()
        if lk in _REDACT_FIELDS_ACTIVE:
            event_dict[key] = "***"
    return event_dict


def _remove_fleet_handlers(root: logging.Logger) -> None:
    """@brief Drop handlers previously registered by this module."""
    global _STDOUT_HANDLER, _OTEL_LOG_HANDLER, _OTEL_LOG_PROVIDER
    for h in list(root.handlers):
        if getattr(h, _HANDLER_TAG, False):
            root.removeHandler(h)
    if _OTEL_LOG_PROVIDER is not None:
        _OTEL_LOG_PROVIDER.shutdown()
    _STDOUT_HANDLER = None
    _OTEL_LOG_HANDLER = None
    _OTEL_LOG_PROVIDER = None


def _maybe_attach_otel_logs(
    root: logging.Logger,
    otel_endpoint: str,
    *,
    insecure: bool = False,
    headers: dict[str, str] | None = None,
) -> None:
    """@brief Optionally export logs via OTLP when an endpoint is configured.

    @param root Root stdlib logger to attach the OTLP handler to.
    @param otel_endpoint OTLP gRPC collector endpoint (``host:port``).
    @param insecure When True, use plaintext gRPC (no TLS). Default False.
    @param headers Optional authentication headers for the exporter.
    """
    global _OTEL_LOG_HANDLER, _OTEL_LOG_PROVIDER
    try:
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
            OTLPLogExporter,
        )
    except ImportError:
        return
    exporter = OTLPLogExporter(
        endpoint=otel_endpoint, insecure=insecure, headers=headers,
    )
    _OTEL_LOG_PROVIDER = LoggerProvider()
    _OTEL_LOG_PROVIDER.add_log_record_processor(BatchLogRecordProcessor(exporter))
    _OTEL_LOG_HANDLER = LoggingHandler(logger_provider=_OTEL_LOG_PROVIDER)
    setattr(_OTEL_LOG_HANDLER, _HANDLER_TAG, True)
    root.addHandler(_OTEL_LOG_HANDLER)


def configure_logging(
    *,
    log_level: str = "info",
    module_levels: dict[str, str] | None = None,
    redact_fields: frozenset[str] | None = None,
    otel_endpoint: str | None = None,
    otel_insecure: bool = False,
    otel_headers: dict[str, str] | None = None,
) -> None:
    """@brief Configure structlog for JSON output with redaction and per-module levels.

    @param log_level Default (root) log level name, e.g. ``info`` or ``warning``.
    @param module_levels Optional map of logger name to level for overrides.
    @param redact_fields Optional override of fields redacted at the sink.
    @param otel_endpoint When set, attach an OTLP log exporter to the root logger.
    @param otel_insecure When True, use plaintext gRPC for OTLP log export.
    @param otel_headers Optional authentication headers for OTLP log exporter.
    @raises ValueError If ``log_level`` or any value in ``module_levels`` is invalid.
    """
    global _REDACT_FIELDS_ACTIVE, _STDOUT_HANDLER
    root = logging.getLogger()
    _remove_fleet_handlers(root)
    structlog.reset_defaults()

    _REDACT_FIELDS_ACTIVE = _normalize_redact_fields(redact_fields)

    root.setLevel(_level_from_name(log_level))
    if module_levels:
        for name, lvl in module_levels.items():
            logging.getLogger(name).setLevel(_level_from_name(lvl))

    pre_chain: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        add_trace_context,
        redact_sensitive,
        ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=pre_chain,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = ProcessorFormatter(
        foreign_pre_chain=pre_chain,
        processors=[
            ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    _STDOUT_HANDLER = logging.StreamHandler(sys.stdout)
    _STDOUT_HANDLER.setFormatter(formatter)
    setattr(_STDOUT_HANDLER, _HANDLER_TAG, True)
    root.addHandler(_STDOUT_HANDLER)

    if otel_endpoint:
        _maybe_attach_otel_logs(
            root, otel_endpoint, insecure=otel_insecure, headers=otel_headers,
        )


def get_logger(name: str) -> structlog.BoundLogger:
    """@brief Return a bound structlog logger for the given module name.

    @param name Usually ``__name__`` of the calling module.
    @return Configured stdlib-backed structlog logger.
    """
    return cast(structlog.BoundLogger, structlog.get_logger(name))


def _reset_logging_internal() -> None:
    """@brief Tear down configuration (for tests).

    Removes fleet handlers, shuts down OTLP logging, and resets structlog defaults.
    """
    root = logging.getLogger()
    _remove_fleet_handlers(root)
    structlog.reset_defaults()
    root.setLevel(logging.WARNING)
