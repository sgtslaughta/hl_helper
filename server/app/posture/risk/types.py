"""Risk-scoring shared types used by the aggregator + plugin scorers.

See docs/superpowers/specs/2026-05-09-posture-risk-aggregator-design.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class Driver:
    """A specific contributor to a pillar's score (top-K shown in UI)."""

    label: str
    contrib: float
    href: str | None = None


@dataclass(frozen=True)
class SubScore:
    """A single pillar's contribution to overall risk.

    score: 0..100 — pillar-internal severity, 0 = clean.
    confidence: 0..1 — how sure we are; missing/stale data lowers.
    drivers: top contributors (UI uses for breakdown panel).
    coverage_notes: human-readable gaps ("sshd not surveyed", etc.).
    """

    score: float
    confidence: float
    drivers: list[Driver] = field(default_factory=list)
    coverage_notes: list[str] = field(default_factory=list)


@dataclass
class ScoreContext:
    """Inputs passed to every scorer for a single host.

    Resolved once by the recomputer and shared across all scorers so
    each pillar avoids redundant DB hits. Heavy lookups (advisories,
    findings, survey) are pre-fetched.
    """

    host: Any
    advisories: list[Any]
    findings: list[Any]
    survey: dict | None
    metrics: dict | None
    now: datetime
    host_advisory_exposure: list[Any] = field(default_factory=list)
    exposure_multipliers: dict[str, float] | None = None
    scan_interval_seconds: int = 6 * 3600


@dataclass(frozen=True)
class Risk:
    """Aggregator output."""

    score: int | None  # None when level == 'unknown'
    level: str
    confidence: float
    floor_triggered: bool


class PostureScorer(Protocol):
    """Plugin protocol every pillar implements."""

    name: str
    label: str
    description: str
    weight_default: float
    enabled_by_default: bool

    async def score(self, ctx: ScoreContext) -> SubScore: ...
