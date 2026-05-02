"""GroupMembership model — represents membership of hosts in groups."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class MembershipKind(str, Enum):
    """Type of group membership."""

    STATIC = "static"
    DYNAMIC = "dynamic"


class GroupMembership(Base):
    """GroupMembership table — represents a host's membership in a group."""

    __tablename__ = "group_memberships"

    host_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hosts.id"), primary_key=True
    )
    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("groups.id"), primary_key=True
    )
    kind: Mapped[MembershipKind] = mapped_column(
        SQLEnum(MembershipKind), default=MembershipKind.STATIC
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
