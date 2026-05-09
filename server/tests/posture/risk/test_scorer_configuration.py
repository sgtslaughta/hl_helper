from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from server.app.posture.risk.scorers.configuration import ConfigurationScorer
from server.app.posture.risk.types import ScoreContext


@dataclass
class FakeFinding:
    rule: str
    severity: str
    title: str = ""
    summary: str = ""


def _ctx(findings, *, survey: dict | None = None):
    return ScoreContext(
        host=type("H", (), {"survey_at": datetime.now(timezone.utc)})(),
        advisories=[],
        findings=findings,
        survey=survey,
        metrics=None,
        now=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_no_findings_clean():
    sub = await ConfigurationScorer().score(_ctx([]))
    assert sub.score == 0


@pytest.mark.asyncio
async def test_one_high_finding_scores():
    sub = await ConfigurationScorer().score(
        _ctx([FakeFinding(rule="sshd_passwordauth", severity="high")])
    )
    assert 10 <= sub.score <= 14


@pytest.mark.asyncio
async def test_single_rule_capped_at_35():
    sub = await ConfigurationScorer().score(
        _ctx([
            FakeFinding(rule="sshd_passwordauth", severity="critical"),
            FakeFinding(rule="sshd_passwordauth", severity="critical"),
        ])
    )
    assert sub.score == 35


@pytest.mark.asyncio
async def test_missing_survey_lowers_confidence():
    sub = await ConfigurationScorer().score(_ctx([], survey=None))
    assert sub.confidence < 0.5
