"""Tests for centralized structlog JSON logging with redaction and levels."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any, cast

import pytest
from opentelemetry import context as otel_context
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    set_span_in_context,
)

from server.app.observability import logging as obs_logging


@pytest.fixture(autouse=True)
def _reset_structlog_and_logging() -> Generator[None, None, None]:
    """Ensure each test starts and ends with a clean logging configuration."""
    obs_logging._reset_logging_internal()  # noqa: SLF001
    yield
    obs_logging._reset_logging_internal()  # noqa: SLF001


def _last_json_line(out: str) -> dict[str, Any]:
    """@brief Parse the last non-empty line of captured output as JSON."""
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    assert lines, "expected at least one log line"
    return cast(dict[str, Any], json.loads(lines[-1]))


def test_json_shape_includes_core_fields(capsys: pytest.CaptureFixture[str]) -> None:
    """JSON logs include ts, level, event, and trace_id keys."""
    obs_logging.configure_logging(log_level="info")
    log = obs_logging.get_logger("server.tests.observability.shape")
    log.info("hello_world", request_id="r1")
    out = capsys.readouterr().out
    row = _last_json_line(out)
    assert "ts" in row
    assert row["level"] == "info"
    assert row["event"] == "hello_world"
    assert "trace_id" in row
    assert row["request_id"] == "r1"


def test_sensitive_fields_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    """Values for redaction keys are replaced with '***' in JSON output."""
    obs_logging.configure_logging(log_level="info")
    log = obs_logging.get_logger("server.tests.observability.redact")
    log.info("auth_attempt", password="hunter2", token="abc", safe="ok")
    row = _last_json_line(capsys.readouterr().out)
    assert row["password"] == "***"
    assert row["token"] == "***"
    assert row["safe"] == "ok"


def test_trace_id_from_otel_context(capsys: pytest.CaptureFixture[str]) -> None:
    """trace_id and span_id reflect the active OpenTelemetry span."""
    obs_logging.configure_logging(log_level="info")
    log = obs_logging.get_logger("server.tests.observability.trace")
    trace_num = 0x1234567890ABCDEF1234567890ABCDEF
    span_num = 0xFEDCBA0987654321
    span_ctx = SpanContext(
        trace_id=trace_num,
        span_id=span_num,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    span = NonRecordingSpan(span_ctx)
    token = otel_context.attach(set_span_in_context(span))
    try:
        log.info("in_span")
    finally:
        otel_context.detach(token)
    row = _last_json_line(capsys.readouterr().out)
    assert row["event"] == "in_span"
    assert row["trace_id"] == format(trace_num, "032x")
    assert row["span_id"] == format(span_num, "016x")


def test_global_warning_suppresses_info(capsys: pytest.CaptureFixture[str]) -> None:
    """When the root log level is warning, info events are not emitted."""
    obs_logging.configure_logging(log_level="warning")
    log = obs_logging.get_logger("server.tests.observability.levels")
    log.info("quiet")
    log.warning("loud")
    out = capsys.readouterr().out
    assert "quiet" not in out
    row = _last_json_line(out)
    assert row["event"] == "loud"
    assert row["level"] == "warning"


def test_module_level_override(capsys: pytest.CaptureFixture[str]) -> None:
    """A named module logger can log at info while the global level is warning."""
    mod = "server.tests.observability.module_override"
    obs_logging.configure_logging(log_level="warning", module_levels={mod: "info"})
    log = obs_logging.get_logger(mod)
    log.info("module_info_ok")
    row = _last_json_line(capsys.readouterr().out)
    assert row["event"] == "module_info_ok"
    assert row["level"] == "info"
