"""Posture finding dataclass + severity ordering.

@brief Defines the Finding value object used by all finding functions and the
PostureFindingRow ORM model for persistent storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base

Severity = Literal["critical", "high", "medium", "low", "info"]


@dataclass(frozen=True)
class Finding:
    """@brief A single posture finding produced by a finding function.

    @param id       Stable identifier (hash of subject+rule).
    @param severity One of critical/high/medium/low/info.
    @param title    Human-readable short title.
    @param summary  Longer description of the finding.
    @param fix_action_url  Optional URL to trigger a fix action.
    @param docs_url        Optional link to documentation.
    @param rule            Finding rule name (defaults to id for backward compat).
    @param subject_kind    Kind of subject: host, user, plugin, setting, global.
    @param subject_id      Identifier of the subject, if applicable.
    @param first_seen      Timestamp when the finding was first observed.
    @param last_seen       Timestamp when the finding was last observed.
    @param suppressed_until  Suppression expiry timestamp.
    @param suppressed_by     Who suppressed the finding.
    @param suppressed_reason Reason for suppression.
    """

    id: str
    severity: Severity
    title: str
    summary: str
    fix_action_url: str | None = None
    docs_url: str | None = None
    rule: str = ""
    subject_kind: str = "global"
    subject_id: str | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    suppressed_until: datetime | None = None
    suppressed_by: str | None = None
    suppressed_reason: str | None = None


class PostureFindingRow(Base):
    """@brief SQLAlchemy ORM model for the posture_findings table.

    Stores persisted posture findings with suppression state and timestamps.
    """

    __tablename__ = "posture_findings"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    rule: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(256))
    summary: Mapped[str] = mapped_column(Text)
    subject_kind: Mapped[str] = mapped_column(String(32), default="global")
    subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fix_action_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    docs_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    suppressed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suppressed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    suppressed_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)


# Severity ordering for sorting (lower = more severe).
SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


__all__ = ["Finding", "PostureFindingRow", "Severity", "SEVERITY_ORDER"]
