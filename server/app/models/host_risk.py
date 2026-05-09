"""HostRisk — persisted snapshot of the multi-pillar posture risk score.

One row per host. Updated by RiskRecomputer (see
server/app/posture/risk/recomputer.py). Schema matches migration 0032.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class HostRisk(Base):
    __tablename__ = "host_risk"

    host_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    pillars: Mapped[dict] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    inputs_hash: Mapped[str] = mapped_column(String(64))
    floor_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    score_prev: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level_prev: Mapped[str | None] = mapped_column(String(16), nullable=True)
