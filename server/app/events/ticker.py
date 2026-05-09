"""System message ticker — normalized event envelope + thin publish helper.

All ticker events flow through a single channel (``TICKER_CHANNEL``) so the
WebUI only has to subscribe once. Producers call ``publish_ticker(...)`` or
build payloads via the ``format_*`` helpers for common cases.

Envelope schema (v1)::

    {
        "v": 1,
        "id": "<uuid4 hex>",
        "ts": "<iso8601 utc>",
        "type": "host" | "advisory" | "posture" | "task" | "audit" | "system",
        "severity": "info" | "warn" | "error" | "ok",
        "text": "<short single-line summary>",
        "link": "<optional internal route>",
        "meta": { ... optional type-specific keys ... }
    }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict
from uuid import uuid4

from server.app.events.bus import Bus, Event

TICKER_CHANNEL = "ticker"
TICKER_SCHEMA_VERSION = 1

TickerType = Literal["host", "advisory", "posture", "task", "audit", "system"]
TickerSeverity = Literal["info", "warn", "error", "ok"]


class TickerEvent(TypedDict, total=False):
    """JSON-serializable ticker envelope (see module docstring)."""

    v: int
    id: str
    ts: str
    type: TickerType
    severity: TickerSeverity
    text: str
    link: str
    meta: dict[str, Any]


def make_ticker_payload(
    *,
    type: TickerType,
    severity: TickerSeverity,
    text: str,
    link: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ticker envelope (sync). Use with publish_after_commit."""
    payload: TickerEvent = {
        "v": TICKER_SCHEMA_VERSION,
        "id": uuid4().hex,
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": type,
        "severity": severity,
        "text": text,
    }
    if link is not None:
        payload["link"] = link
    if meta is not None:
        payload["meta"] = meta
    return dict(payload)


async def publish_ticker(
    bus: Bus,
    *,
    type: TickerType,
    severity: TickerSeverity,
    text: str,
    link: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Event:
    """Publish a ticker event on TICKER_CHANNEL with a stamped envelope."""
    return await bus.publish(
        TICKER_CHANNEL,
        make_ticker_payload(
            type=type,
            severity=severity,
            text=text,
            link=link,
            meta=meta,
        ),
    )


# ---- format_* helpers (return partial envelope, caller passes to publish) ----


def format_host_status(*, host_id: str, hostname: str, online: bool) -> TickerEvent:
    """Format a host online/offline transition message."""
    if online:
        return {
            "type": "host",
            "severity": "ok",
            "text": f"Host {hostname} online",
            "link": f"/hosts/{host_id}",
            "meta": {"host_id": host_id},
        }
    return {
        "type": "host",
        "severity": "warn",
        "text": f"Host {hostname} offline",
        "link": f"/hosts/{host_id}",
        "meta": {"host_id": host_id},
    }


def format_advisory_sync(
    *,
    feed: str,
    phase: Literal["started", "completed", "error"],
    count: int | None = None,
    error: str | None = None,
) -> TickerEvent:
    """Format an advisory feed sync lifecycle message."""
    if phase == "started":
        return {
            "type": "advisory",
            "severity": "info",
            "text": f"Advisory sync {feed} started",
            "meta": {"feed": feed, "phase": "started"},
        }
    if phase == "completed":
        n = count if count is not None else 0
        return {
            "type": "advisory",
            "severity": "ok",
            "text": f"Advisory sync {feed} completed ({n} records)",
            "meta": {"feed": feed, "phase": "completed", "count": n},
        }
    return {
        "type": "advisory",
        "severity": "error",
        "text": f"Advisory sync {feed} error: {error or 'unknown'}",
        "meta": {"feed": feed, "phase": "error", "error": error or "unknown"},
    }


def format_posture_scan(
    *,
    host_id: str,
    hostname: str,
    finding_count: int,
    max_severity: str | None,
) -> TickerEvent:
    """Format a posture scan completion message."""
    sev: TickerSeverity
    if finding_count == 0:
        sev = "ok"
    elif max_severity in ("critical", "high"):
        sev = "error" if max_severity == "critical" else "warn"
    else:
        sev = "info"
    return {
        "type": "posture",
        "severity": sev,
        "text": f"Posture scan {hostname} complete ({finding_count} findings)",
        "link": f"/hosts/{host_id}",
        "meta": {
            "host_id": host_id,
            "finding_count": finding_count,
            "max_severity": max_severity,
        },
    }


def format_task_result(
    *,
    command_id: str,
    host_id: str,
    hostname: str,
    success: bool,
    exit_code: int | None = None,
) -> TickerEvent:
    """Format a task/command result message."""
    if success:
        return {
            "type": "task",
            "severity": "ok",
            "text": f"Task on {hostname} succeeded",
            "link": f"/hosts/{host_id}",
            "meta": {"command_id": command_id, "host_id": host_id, "exit_code": exit_code},
        }
    return {
        "type": "task",
        "severity": "error",
        "text": f"Task on {hostname} failed (exit {exit_code if exit_code is not None else '?'})",
        "link": f"/hosts/{host_id}",
        "meta": {"command_id": command_id, "host_id": host_id, "exit_code": exit_code},
    }
