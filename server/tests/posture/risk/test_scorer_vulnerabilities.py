"""Vulnerabilities scorer tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from server.app.posture.risk.scorers.vulnerabilities import (
    VulnerabilitiesScorer,
)
from server.app.posture.risk.types import ScoreContext


@dataclass
class FakeAdv:
    advisory_id: str
    severity: str
    kev: bool
    epss: float
    package: str = "openssl"
    status: str = "open"


def _ctx(advisories, *, has_inventory: bool = True):
    return ScoreContext(
        host=type("H", (), {"id": "h1", "survey_at": datetime.now(timezone.utc)})(),
        advisories=advisories,
        findings=[],
        survey={"packages": ["openssl"]} if has_inventory else None,
        metrics=None,
        now=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_no_advisories_clean():
    sc = VulnerabilitiesScorer()
    sub = await sc.score(_ctx([]))
    assert sub.score == 0
    assert sub.confidence > 0


@pytest.mark.asyncio
async def test_four_high_no_kev_no_epss_is_moderate():
    sc = VulnerabilitiesScorer()
    advs = [FakeAdv(f"CVE-{i}", "high", False, 0.0) for i in range(4)]
    sub = await sc.score(_ctx(advs))
    assert 24 <= sub.score <= 32


@pytest.mark.asyncio
async def test_kev_critical_with_high_epss_is_high_or_severe():
    sc = VulnerabilitiesScorer()
    sub = await sc.score(_ctx([FakeAdv("CVE-X", "critical", True, 0.9)]))
    assert 75 <= sub.score <= 90


@pytest.mark.asyncio
async def test_unknown_severity_does_not_score():
    sc = VulnerabilitiesScorer()
    sub = await sc.score(_ctx([FakeAdv("CVE-Y", "unknown", False, 0.0)]))
    assert sub.score == 0


@pytest.mark.asyncio
async def test_missing_inventory_lowers_confidence():
    sc = VulnerabilitiesScorer()
    sub = await sc.score(_ctx([], has_inventory=False))
    assert sub.confidence < 0.5
