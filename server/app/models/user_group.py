"""UserGroup model — represents a group of users and their memberships."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


# Join table for user-group membership
user_group_members = Table(
    "user_group_members",
    Base.metadata,
    Column(
        "user_id",
        String(36),
        ForeignKey("users.id"),
        primary_key=True,
    ),
    Column(
        "user_group_id",
        String(36),
        ForeignKey("user_groups.id"),
        primary_key=True,
    ),
    Column("added_at", DateTime(timezone=True), server_default=func.now()),
)


class UserGroup(Base):
    """UserGroup table — represents a group of users."""

    __tablename__ = "user_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
