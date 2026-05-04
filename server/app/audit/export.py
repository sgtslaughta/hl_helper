"""Audit export formatters: JSON, CEF, syslog, OTLP.

Each formatter is a pure function (entry -> bytes line) so the streaming
endpoint stays format-agnostic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from server.app.models.audit import AuditEntry

ExportFormat = str  # "json" | "cef" | "syslog" | "otlp"

VALID_FORMATS = ("json", "cef", "syslog", "otlp")

# CEF severity mapping per common action prefix
_CEF_SEVERITY = {
    "rbac.denied": 7,
    "approval.rejected": 6,
    "approval.approved": 5,
    "approval.requested": 3,
    "binding.deleted": 5,
    "binding.created": 4,
    "role.deleted": 7,
    "role.updated": 5,
    "role.created": 4,
    "auth.login.failed": 8,
    "auth.login": 3,
    "session.revoked": 5,
}


def _ts(entry: AuditEntry) -> datetime:
    ts = entry.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _entry_to_dict(entry: AuditEntry) -> dict[str, Any]:
    return {
        "sequence": entry.sequence,
        "timestamp": _ts(entry).isoformat(),
        "actor": entry.actor,
        "action": entry.action,
        "subject": entry.subject,
        "payload": entry.payload,
        "prev_hash": entry.prev_hash.hex(),
        "entry_hash": entry.entry_hash.hex(),
    }


def format_json(entry: AuditEntry) -> bytes:
    return json.dumps(_entry_to_dict(entry)).encode() + b"\n"


def _cef_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("=", "\\=").replace("\n", " ")


def format_cef(entry: AuditEntry, *, vendor: str = "hl-helper", product: str = "fleet", version: str = "1") -> bytes:
    """ArcSight CEF v0 format. CEF:0|Vendor|Product|Version|SignatureID|Name|Severity|Extension"""
    sev = _CEF_SEVERITY.get(entry.action, 4)
    name = _cef_escape(entry.action)
    sig = _cef_escape(entry.action)
    extensions = {
        "rt": int(_ts(entry).timestamp() * 1000),
        "suser": _cef_escape(entry.actor),
        "cs1Label": "subject",
        "cs1": _cef_escape(entry.subject or ""),
        "cn1Label": "sequence",
        "cn1": entry.sequence,
        "cs2Label": "payload",
        "cs2": _cef_escape(json.dumps(entry.payload, separators=(",", ":"))),
    }
    ext_str = " ".join(f"{k}={v}" for k, v in extensions.items() if v is not None)
    line = f"CEF:0|{vendor}|{product}|{version}|{sig}|{name}|{sev}|{ext_str}"
    return line.encode() + b"\n"


def format_syslog(entry: AuditEntry, *, hostname: str = "fleet", app: str = "hl-helper") -> bytes:
    """RFC 5424 syslog. Facility=local0(16), severity=info(6) -> PRI=134."""
    pri = 134
    ts_iso = _ts(entry).isoformat()
    sd = (
        f'[hl@0 seq="{entry.sequence}" actor="{entry.actor}" '
        f'action="{entry.action}" subject="{entry.subject or ""}"]'
    )
    msg = json.dumps(entry.payload, separators=(",", ":"))
    line = f"<{pri}>1 {ts_iso} {hostname} {app} - audit {sd} {msg}"
    return line.encode() + b"\n"


def format_otlp(entry: AuditEntry) -> bytes:
    """OTLP/JSON LogRecord shape (single record per line, NDJSON)."""
    record = {
        "timeUnixNano": int(_ts(entry).timestamp() * 1_000_000_000),
        "severityNumber": 9,  # INFO
        "severityText": "INFO",
        "body": {"stringValue": entry.action},
        "attributes": [
            {"key": "audit.sequence", "value": {"intValue": entry.sequence}},
            {"key": "audit.actor", "value": {"stringValue": entry.actor}},
            {"key": "audit.action", "value": {"stringValue": entry.action}},
            {"key": "audit.subject", "value": {"stringValue": entry.subject or ""}},
            {"key": "audit.payload", "value": {"stringValue": json.dumps(entry.payload)}},
            {"key": "audit.entry_hash", "value": {"stringValue": entry.entry_hash.hex()}},
        ],
    }
    return json.dumps(record).encode() + b"\n"


_FORMATTERS = {
    "json": format_json,
    "cef": format_cef,
    "syslog": format_syslog,
    "otlp": format_otlp,
}


def format_entry(entry: AuditEntry, fmt: ExportFormat) -> bytes:
    """Dispatch to formatter; raises ValueError on unknown format."""
    f = _FORMATTERS.get(fmt)
    if f is None:
        raise ValueError(f"unknown_export_format: {fmt}")
    return f(entry)


def media_type_for(fmt: ExportFormat) -> str:
    return {
        "json": "application/x-ndjson",
        "cef": "text/plain; charset=utf-8",
        "syslog": "text/plain; charset=utf-8",
        "otlp": "application/x-ndjson",
    }.get(fmt, "application/octet-stream")
