"""Tests for vulnerabilities scorer with exposure tier multipliers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from unittest.mock import MagicMock


def _ctx(host_id="h-1", advisories=None, exposures=None, multipliers=None, now=None):
    """Construct a ScoreContext-shaped object for the scorer."""
    ctx = MagicMock()
    ctx.host_id = host_id
    ctx.advisories = advisories or []  # list of {id, severity}
    ctx.host_advisory_exposure = exposures or []  # list of model rows
    ctx.now = now or datetime.now(timezone.utc)
    ctx.scan_interval_seconds = 6 * 3600  # 6h default
    ctx.exposure_multipliers = multipliers or {
        "NETWORK_EXPOSED": 2.0, "ACTIVE": 1.5, "INSTALLED_ONLY": 0.5, "UNKNOWN": 1.0,
    }
    return ctx


def _exposure(advisory_id, tier, scanned_at):
    obj = MagicMock()
    obj.advisory_id = advisory_id
    obj.exposure_tier = tier
    obj.scanned_at = scanned_at
    return obj


def test_score_applies_network_exposed_multiplier():
    from server.app.posture.risk.scorers.vulnerabilities import _apply_exposure_weight

    base = 10.0
    weighted = _apply_exposure_weight(
        base=base, tier="NETWORK_EXPOSED",
        multipliers={"NETWORK_EXPOSED": 2.0, "ACTIVE": 1.5, "INSTALLED_ONLY": 0.5, "UNKNOWN": 1.0},
    )
    assert weighted == 20.0


def test_score_applies_active_multiplier():
    from server.app.posture.risk.scorers.vulnerabilities import _apply_exposure_weight

    weighted = _apply_exposure_weight(
        base=10.0, tier="ACTIVE",
        multipliers={"NETWORK_EXPOSED": 2.0, "ACTIVE": 1.5, "INSTALLED_ONLY": 0.5, "UNKNOWN": 1.0},
    )
    assert weighted == 15.0


def test_score_applies_installed_only_multiplier():
    from server.app.posture.risk.scorers.vulnerabilities import _apply_exposure_weight

    weighted = _apply_exposure_weight(
        base=10.0, tier="INSTALLED_ONLY",
        multipliers={"NETWORK_EXPOSED": 2.0, "ACTIVE": 1.5, "INSTALLED_ONLY": 0.5, "UNKNOWN": 1.0},
    )
    assert weighted == 5.0


def test_score_unknown_when_no_exposure_row():
    from server.app.posture.risk.scorers.vulnerabilities import _resolve_tier

    now = datetime.now(timezone.utc)
    tier = _resolve_tier(
        advisory_id="CVE-1",
        exposures=[],
        now=now,
        scan_interval_seconds=6 * 3600,
    )
    assert tier == "UNKNOWN"


def test_score_unknown_when_exposure_stale():
    """Stale = older than 2× scan interval."""
    from server.app.posture.risk.scorers.vulnerabilities import _resolve_tier

    now = datetime.now(timezone.utc)
    stale = now - timedelta(seconds=2 * 6 * 3600 + 1)
    exp = _exposure("CVE-1", "ACTIVE", stale)
    tier = _resolve_tier(
        advisory_id="CVE-1",
        exposures=[exp],
        now=now,
        scan_interval_seconds=6 * 3600,
    )
    assert tier == "UNKNOWN"


def test_score_uses_fresh_tier():
    from server.app.posture.risk.scorers.vulnerabilities import _resolve_tier

    now = datetime.now(timezone.utc)
    fresh = now - timedelta(minutes=10)
    exp = _exposure("CVE-1", "NETWORK_EXPOSED", fresh)
    tier = _resolve_tier(
        advisory_id="CVE-1",
        exposures=[exp],
        now=now,
        scan_interval_seconds=6 * 3600,
    )
    assert tier == "NETWORK_EXPOSED"
