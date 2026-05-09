"""Vulnerabilities pillar scorer.

Inputs: open host advisories (severity, KEV, EPSS).
Curve: per-advisory base × (1 + 4·KEV + 3·EPSS), summed, then
saturating (1 - exp(-Σ/50)) × 100.

See spec section 'Per-pillar scoring rules'.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from server.app.posture.risk.types import Driver, ScoreContext, SubScore


def _aware(dt: datetime | None) -> datetime | None:
    """Coerce a naive datetime to UTC-aware. SQLite drops tz info on
    DateTime(timezone=True) columns; treat naive values as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

_BASE: dict[str, float] = {
    "critical": 12.0,
    "high": 4.0,
    "medium": 1.2,
    "low": 0.3,
    "unknown": 0.0,
}

_DECAY_DENOM = 50.0

DEFAULT_EXPOSURE_MULTIPLIERS = {
    "NETWORK_EXPOSED": 2.0,
    "ACTIVE": 1.5,
    "INSTALLED_ONLY": 0.5,
    "UNKNOWN": 1.0,
}


def _resolve_tier(
    *,
    advisory_id: str,
    exposures: list,
    now: datetime,
    scan_interval_seconds: int,
) -> str:
    """Find the tier for `advisory_id`. Stale exposures (>2× interval) → UNKNOWN."""
    cutoff = now - timedelta(seconds=2 * scan_interval_seconds)
    for e in exposures:
        if getattr(e, "advisory_id", None) != advisory_id:
            continue
        scanned = getattr(e, "scanned_at", None)
        if scanned is None:
            continue
        if scanned.tzinfo is None:
            scanned = scanned.replace(tzinfo=timezone.utc)
        if scanned < cutoff:
            return "UNKNOWN"
        return getattr(e, "exposure_tier", "UNKNOWN")
    return "UNKNOWN"


def _apply_exposure_weight(*, base: float, tier: str, multipliers: dict[str, float]) -> float:
    return base * multipliers.get(tier, 1.0)


class VulnerabilitiesScorer:
    name = "vulnerabilities"
    label = "Vulnerabilities"
    description = (
        "Open advisories matched against the host's package inventory. "
        "Severity is multiplied by exploitation signals (CISA KEV + EPSS). "
        "Does NOT see whether the vulnerable code path is reachable, "
        "exposed, or guarded by compensating controls."
    )
    weight_default = 0.30
    enabled_by_default = True

    async def score(self, ctx: ScoreContext) -> SubScore:
        advs = [a for a in ctx.advisories if getattr(a, "status", "open") == "open"]

        contributions: list[tuple[float, Any]] = []
        raw = 0.0
        for a in advs:
            sev = (getattr(a, "severity", "") or "unknown").lower()
            base = _BASE.get(sev, 0.0)
            if base == 0.0:
                continue
            epss = max(0.0, min(1.0, float(getattr(a, "epss", 0.0) or 0.0)))
            kev = bool(getattr(a, "kev", False))
            mult = 1.0 + (4.0 if kev else 0.0) + 3.0 * epss
            c = base * mult
            raw += c
            contributions.append((c, a))

        score = (1.0 - math.exp(-raw / _DECAY_DENOM)) * 100.0 if raw > 0 else 0.0

        drivers = [
            Driver(
                label=f"{getattr(a, 'package', '?')} — {getattr(a, 'advisory_id', '')}",
                contrib=round(c, 2),
                href=f"/advisories/{getattr(a, 'advisory_id', '')}",
            )
            for c, a in sorted(contributions, key=lambda x: -x[0])[:3]
        ]

        # Confidence from inventory presence + survey freshness.
        has_inventory = bool(
            ctx.survey and isinstance(ctx.survey, dict) and ctx.survey.get("packages")
        )
        survey_at = _aware(getattr(ctx.host, "survey_at", None))
        now = _aware(ctx.now) or ctx.now
        if survey_at is None:
            freshness = 0.3
        else:
            age = (now - survey_at).total_seconds()
            freshness = max(0.3, 1.0 - age / (7 * 86400))
        coverage = 1.0 if has_inventory else 0.4
        confidence = round(coverage * freshness, 3)
        notes = []
        if not has_inventory:
            notes.append("package inventory missing — score may understate risk")

        return SubScore(
            score=round(score, 1),
            confidence=confidence,
            drivers=drivers,
            coverage_notes=notes,
        )
