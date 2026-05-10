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
    # Without explicit exposure rows, scorer applies Unknown=0.6 multiplier
    # (tune commit 8b279fb). Range scaled from prior 24..32 baseline.
    assert 14 <= sub.score <= 22


@pytest.mark.asyncio
async def test_kev_critical_with_high_epss_is_high_or_severe():
    sc = VulnerabilitiesScorer()
    sub = await sc.score(_ctx([FakeAdv("CVE-X", "critical", True, 0.9)]))
    # Range scaled for Unknown=0.6 default (tune commit 8b279fb).
    assert 55 <= sub.score <= 75


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
