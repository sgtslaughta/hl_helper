"""Operational Hygiene pillar scorer.

Inputs: agent version drift vs latest release, cert expiry window,
never-heartbeated state, heartbeat staleness, agent update failure
status.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from server.app.posture.risk.types import Driver, ScoreContext, SubScore


def _aware(dt: datetime | None) -> datetime | None:
    """Coerce a naive datetime to UTC-aware. SQLite drops tz info on
    DateTime(timezone=True) columns; treat naive values as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_minor(v: str | None) -> tuple[int, int] | None:
    if not v:
        return None
    m = re.match(r"^v?(\d+)\.(\d+)", v)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _minor_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    # major bump treated as 10 minors so "1.x → 2.0" carries weight.
    return abs((a[0] - b[0]) * 10 + (a[1] - b[1]))


class HygieneScorer:
    name = "hygiene"
    label = "Operational Hygiene"
    description = (
        "Agent version drift, cert expiry, heartbeat health, agent "
        "update failures. Reflects fleet maintenance state, not "
        "vulnerability content."
    )
    weight_default = 0.15
    enabled_by_default = True

    async def score(self, ctx: ScoreContext) -> SubScore:
        host = ctx.host
        now = _aware(ctx.now) or ctx.now
        score = 0.0
        drivers: list[Driver] = []

        cert = _aware(getattr(host, "cert_expires_at", None))
        if cert is not None:
            days = (cert - now).total_seconds() / 86400
            if days < 7:
                score += 40
                drivers.append(Driver(label=f"cert expires in {int(days)}d", contrib=40))
            elif days < 30:
                score += 15
                drivers.append(Driver(label=f"cert expires in {int(days)}d", contrib=15))

        last_seen = _aware(getattr(host, "last_seen_at", None))
        enrolled = _aware(getattr(host, "enrolled_at", None))
        if last_seen is None and enrolled is not None:
            if (now - enrolled) > timedelta(minutes=30):
                score += 25
                drivers.append(Driver(label="never heartbeated", contrib=25))
        elif last_seen is not None:
            interval = getattr(host, "heartbeat_interval_s", 60) or 60
            age = (now - last_seen).total_seconds()
            if age > 4 * interval:
                score += 20
                drivers.append(Driver(label="heartbeat stale", contrib=20))

        if getattr(host, "agent_update_status", "ok") == "failed":
            score += 15
            drivers.append(Driver(label="agent update failed", contrib=15))

        latest = (ctx.metrics or {}).get("latest_agent_release") if ctx.metrics else None
        cur = _parse_minor(getattr(host, "agent_version", None))
        latest_v = _parse_minor(latest)
        if cur and latest_v:
            d = _minor_distance(cur, latest_v)
            if d > 0:
                drift = d * 8
                score += drift
                drivers.append(
                    Driver(
                        label=f"agent v{getattr(host,'agent_version','?')} (latest {latest})",
                        contrib=drift,
                    )
                )

        score = min(100.0, score)

        if last_seen is None:
            confidence = 0.7
        else:
            age = (now - last_seen).total_seconds()
            confidence = max(0.4, 1.0 - age / (7 * 86400))

        return SubScore(
            score=round(score, 1),
            confidence=round(confidence, 3),
            drivers=drivers[:3],
            coverage_notes=[],
        )
