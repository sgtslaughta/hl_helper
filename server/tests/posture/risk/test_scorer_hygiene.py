from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from server.app.posture.risk.scorers.hygiene import HygieneScorer
from server.app.posture.risk.types import ScoreContext


@dataclass
class FakeHost:
    enrolled_at: datetime
    last_seen_at: datetime | None = None
    heartbeat_interval_s: int = 60
    cert_expires_at: datetime | None = None
    agent_version: str | None = "1.0.0"
    agent_update_status: str = "ok"
    sleeping: bool = False
    latest_release_version: str | None = "1.0.0"


def _ctx(host: FakeHost):
    return ScoreContext(
        host=host,
        advisories=[],
        findings=[],
        survey=None,
        metrics={"latest_agent_release": host.latest_release_version},
        now=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_healthy_recent_host_clean():
    now = datetime.now(timezone.utc)
    host = FakeHost(
        enrolled_at=now - timedelta(days=10),
        last_seen_at=now - timedelta(seconds=30),
        cert_expires_at=now + timedelta(days=180),
    )
    sub = await HygieneScorer().score(_ctx(host))
    assert sub.score == 0


@pytest.mark.asyncio
async def test_never_heartbeated_old_enroll_scores_25():
    now = datetime.now(timezone.utc)
    host = FakeHost(
        enrolled_at=now - timedelta(hours=2),
        last_seen_at=None,
        cert_expires_at=now + timedelta(days=180),
    )
    sub = await HygieneScorer().score(_ctx(host))
    assert sub.score == 25


@pytest.mark.asyncio
async def test_cert_expiring_soon_scores_40():
    now = datetime.now(timezone.utc)
    host = FakeHost(
        enrolled_at=now - timedelta(days=10),
        last_seen_at=now - timedelta(seconds=30),
        cert_expires_at=now + timedelta(days=3),
    )
    sub = await HygieneScorer().score(_ctx(host))
    assert sub.score == 40


@pytest.mark.asyncio
async def test_agent_version_drift():
    now = datetime.now(timezone.utc)
    host = FakeHost(
        enrolled_at=now - timedelta(days=10),
        last_seen_at=now - timedelta(seconds=30),
        cert_expires_at=now + timedelta(days=180),
        agent_version="1.0.0",
        latest_release_version="1.3.0",
    )
    sub = await HygieneScorer().score(_ctx(host))
    assert sub.score == 24
