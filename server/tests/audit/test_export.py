"""Tests for server.app.audit.export formatters."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from server.app.audit.export import (
    VALID_FORMATS,
    format_cef,
    format_entry,
    format_json,
    format_otlp,
    format_syslog,
    media_type_for,
)
from server.app.models.audit import AuditEntry


def _entry(**overrides) -> AuditEntry:
    defaults: dict = {
        "sequence": 7,
        "timestamp": datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        "actor": "u-1",
        "action": "approval.rejected",
        "subject": "approval-abc",
        "payload": {"reason": "no_thanks", "decision": "reject"},
        "prev_hash": b"\x00" * 32,
        "entry_hash": b"\x11" * 32,
    }
    defaults.update(overrides)
    return AuditEntry(**defaults)


def test_json_round_trip() -> None:
    line = format_json(_entry())
    parsed = json.loads(line)
    assert parsed["sequence"] == 7
    assert parsed["actor"] == "u-1"
    assert parsed["action"] == "approval.rejected"
    assert parsed["payload"]["reason"] == "no_thanks"
    assert parsed["entry_hash"] == "11" * 32
    assert line.endswith(b"\n")


def test_cef_shape() -> None:
    line = format_cef(_entry()).decode().rstrip()
    assert line.startswith("CEF:0|hl-helper|fleet|1|")
    assert "approval.rejected" in line
    assert "suser=u-1" in line
    assert "cs1Label=subject" in line
    assert "cn1Label=sequence" in line
    assert "cn1=7" in line


def test_cef_escapes_pipe_and_equals() -> None:
    line = format_cef(_entry(actor="u|=danger", subject="x=y|z")).decode()
    assert "u\\|\\=danger" in line
    assert "x\\=y\\|z" in line


def test_cef_severity_mapping() -> None:
    line_high = format_cef(_entry(action="rbac.denied")).decode()
    line_low = format_cef(_entry(action="role.created")).decode()
    assert "|7|" in line_high
    assert "|4|" in line_low


def test_syslog_rfc5424() -> None:
    line = format_syslog(_entry()).decode().rstrip()
    assert line.startswith("<134>1 2026-05-04T12:00:00+00:00 fleet hl-helper")
    assert 'seq="7"' in line
    assert 'actor="u-1"' in line
    assert 'action="approval.rejected"' in line
    assert '"reason":"no_thanks"' in line


def test_otlp_logrecord_shape() -> None:
    line = format_otlp(_entry())
    parsed = json.loads(line)
    assert parsed["severityText"] == "INFO"
    assert parsed["body"]["stringValue"] == "approval.rejected"
    keys = {a["key"] for a in parsed["attributes"]}
    assert keys == {
        "audit.sequence",
        "audit.actor",
        "audit.action",
        "audit.subject",
        "audit.payload",
        "audit.entry_hash",
    }


def test_format_entry_dispatch() -> None:
    e = _entry()
    for fmt in VALID_FORMATS:
        out = format_entry(e, fmt)
        assert out.endswith(b"\n")


def test_format_entry_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        format_entry(_entry(), "xml")


def test_media_types() -> None:
    assert media_type_for("json") == "application/x-ndjson"
    assert media_type_for("otlp") == "application/x-ndjson"
    assert "text/plain" in media_type_for("cef")
    assert "text/plain" in media_type_for("syslog")


def test_handles_naive_timestamp() -> None:
    e = _entry(timestamp=datetime(2026, 5, 4, 12, 0, 0))
    out = format_json(e)
    parsed = json.loads(out)
    assert parsed["timestamp"].endswith("+00:00")


def test_handles_null_subject() -> None:
    e = _entry(subject=None)
    js = json.loads(format_json(e))
    assert js["subject"] is None
    cef = format_cef(e).decode()
    assert "cs1=" in cef  # empty value still labeled
    sl = format_syslog(e).decode()
    assert 'subject=""' in sl
