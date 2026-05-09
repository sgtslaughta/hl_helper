from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from server.app.posture.risk.scorers.identity import IdentityScorer
from server.app.posture.risk.types import ScoreContext


@dataclass
class FakeFinding:
    rule: str
    severity: str


def _ctx(findings):
    return ScoreContext(
        host=type("H", (), {})(),
        advisories=[],
        findings=findings,
        survey=None,
        metrics=None,
        now=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_no_findings_clean():
    sub = await IdentityScorer().score(_ctx([]))
    assert sub.score == 0
    assert sub.confidence == 1.0


@pytest.mark.asyncio
async def test_one_low_finding_baseline_floor_5():
    sub = await IdentityScorer().score(
        _ctx([FakeFinding(rule="stale_pending_approvals", severity="low")])
    )
    assert sub.score == 5


@pytest.mark.asyncio
async def test_critical_finding_climbs():
    sub = await IdentityScorer().score(
        _ctx([FakeFinding(rule="no_owner_account", severity="critical")])
    )
    assert 22 <= sub.score <= 30
