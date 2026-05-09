"""Tests for ticker event publish helper."""

from __future__ import annotations

import asyncio

import pytest

from server.app.events.bus import Bus
from server.app.events.ticker import (
    TICKER_CHANNEL,
    format_advisory_sync,
    format_host_status,
    format_posture_scan,
    format_task_result,
    publish_ticker,
)


@pytest.mark.asyncio
async def test_publish_ticker_envelope_shape() -> None:
    """publish_ticker emits a stamped envelope on TICKER_CHANNEL."""
    bus = Bus()

    async def consumer():
        async for ev in bus.subscribe(TICKER_CHANNEL):
            return ev

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.01)

    await publish_ticker(
        bus,
        type="host",
        severity="ok",
        text="Host alpha online",
        link="/hosts/alpha",
        meta={"host_id": "alpha"},
    )

    ev = await asyncio.wait_for(task, timeout=1.0)
    p = ev.payload
    assert ev.channel == TICKER_CHANNEL
    assert p["v"] == 1
    assert p["type"] == "host"
    assert p["severity"] == "ok"
    assert p["text"] == "Host alpha online"
    assert p["link"] == "/hosts/alpha"
    assert p["meta"] == {"host_id": "alpha"}
    # id is uuid4 hex (32 chars) — just confirm presence + str
    assert isinstance(p["id"], str) and len(p["id"]) >= 16
    # ts is iso8601 utc
    assert isinstance(p["ts"], str) and p["ts"].endswith("+00:00")


@pytest.mark.asyncio
async def test_publish_ticker_omits_optional_when_absent() -> None:
    """link and meta are absent from payload if not supplied."""
    bus = Bus()

    async def consumer():
        async for ev in bus.subscribe(TICKER_CHANNEL):
            return ev

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.01)

    await publish_ticker(bus, type="system", severity="info", text="boot")
    ev = await asyncio.wait_for(task, timeout=1.0)
    assert "link" not in ev.payload
    assert "meta" not in ev.payload


def test_format_host_status_online() -> None:
    f = format_host_status(host_id="h1", hostname="alpha", online=True)
    assert f["type"] == "host"
    assert f["severity"] == "ok"
    assert "alpha" in f["text"]
    assert "online" in f["text"].lower()
    assert f["link"] == "/hosts/h1"
    assert f["meta"] == {"host_id": "h1"}


def test_format_host_status_offline() -> None:
    f = format_host_status(host_id="h1", hostname="alpha", online=False)
    assert f["severity"] == "warn"
    assert "offline" in f["text"].lower()


def test_format_advisory_sync_started() -> None:
    f = format_advisory_sync(feed="osv", phase="started")
    assert f["type"] == "advisory"
    assert f["severity"] == "info"
    assert "osv" in f["text"].lower()


def test_format_advisory_sync_completed() -> None:
    f = format_advisory_sync(feed="osv", phase="completed", count=42)
    assert f["severity"] == "ok"
    assert "42" in f["text"]


def test_format_advisory_sync_error() -> None:
    f = format_advisory_sync(feed="osv", phase="error", error="timeout")
    assert f["severity"] == "error"
    assert "timeout" in f["text"]


def test_format_posture_scan() -> None:
    f = format_posture_scan(
        host_id="h1", hostname="alpha", finding_count=3, max_severity="high"
    )
    assert f["type"] == "posture"
    assert f["severity"] == "warn"
    assert "alpha" in f["text"]
    assert "3" in f["text"]
    assert f["link"] == "/hosts/h1"


def test_format_posture_scan_no_findings() -> None:
    f = format_posture_scan(
        host_id="h1", hostname="alpha", finding_count=0, max_severity=None
    )
    assert f["severity"] == "ok"


def test_format_task_result_success() -> None:
    f = format_task_result(
        command_id="c1", host_id="h1", hostname="alpha", success=True
    )
    assert f["type"] == "task"
    assert f["severity"] == "ok"
    assert f["link"] == "/hosts/h1"


def test_format_task_result_failure() -> None:
    f = format_task_result(
        command_id="c1", host_id="h1", hostname="alpha", success=False, exit_code=2
    )
    assert f["severity"] == "error"
    assert "alpha" in f["text"]
