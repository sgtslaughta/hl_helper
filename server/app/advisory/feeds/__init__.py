"""Advisory feed sources abstract base classes and data models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FeedAffected:
    """Package affected by an advisory."""

    ecosystem: str
    package: str
    introduced: str | None = None
    fixed: str | None = None
    range_kind: str = "ECOSYSTEM"


@dataclass
class FeedAdvisory:
    """Advisory from a feed source."""

    id: str
    aliases: list[str]
    summary: str
    description_md: str | None
    severity: str  # critical|high|medium|low|info|unknown
    cvss_v3: str | None
    cvss_v4: str | None
    published: datetime | None
    modified: datetime | None
    refs: list[str]
    affected: list[FeedAffected]


class AdvisoryFeedSource(ABC):
    """Abstract base for advisory feed sources."""

    name: str

    @abstractmethod
    async def sync(self) -> list[FeedAdvisory]:
        """Sync advisories from the source."""


class ScoreFeedSource(ABC):
    """Abstract base for score feed sources (EPSS, KEV)."""

    name: str

    @abstractmethod
    async def sync(self) -> dict[str, float | bool]:
        """Map advisory_id -> EPSS score (float) or KEV flag (bool)."""


__all__ = [
    "FeedAdvisory",
    "FeedAffected",
    "AdvisoryFeedSource",
    "ScoreFeedSource",
]
