"""AgentRelease model — represents a release artifact for agent distribution."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class ReleaseChannel(str, enum.Enum):
    """Release channel enum."""

    STABLE = "stable"
    BETA = "beta"
    CANARY = "canary"


class ReleaseStatus(str, enum.Enum):
    """Release status enum."""

    STAGED = "staged"
    PUBLISHED = "published"
    YANKED = "yanked"


class AgentRelease(Base):
    """AgentRelease table — represents a release artifact for agent distribution."""

    __tablename__ = "agent_releases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel: Mapped[ReleaseChannel] = mapped_column(SAEnum(ReleaseChannel), nullable=False, index=True)
    os: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    arch: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    manifest_json: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    manifest_sig: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[ReleaseStatus] = mapped_column(
        SAEnum(ReleaseStatus), nullable=False, default=ReleaseStatus.STAGED, index=True
    )
    uploaded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    yanked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    yanked_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (UniqueConstraint("version", "os", "arch", name="uq_agent_release_ver_os_arch"),)
