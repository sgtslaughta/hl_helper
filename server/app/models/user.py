"""User model — represents a user (local or OIDC)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SQLEnum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class UserKind(str, Enum):
    """Type of user authentication."""

    LOCAL = "local"
    OIDC = "oidc"


class User(Base):
    """User table — represents a local or OIDC-authenticated user."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[UserKind] = mapped_column(SQLEnum(UserKind))
    oidc_subject: Mapped[str | None] = mapped_column(String, nullable=True)
    oidc_issuer: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    disabled: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
