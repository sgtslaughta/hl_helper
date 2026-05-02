"""Binding model — represents a role binding to a principal with scope."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SQLEnum, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class PrincipalType(str, Enum):
    """Type of principal that can be bound to a role."""

    USER = "user"
    USER_GROUP = "user_group"
    SERVICE_ACCOUNT = "service_account"


class ScopeKind(str, Enum):
    """Kind of scope for a binding."""

    GLOBAL = "global"
    GROUP = "group"
    TAG = "tag"
    HOST_LIST = "host_list"
    SELF = "self"


class Binding(Base):
    """Binding table — represents a role bound to a principal with a scope."""

    __tablename__ = "bindings"
    __table_args__ = (
        UniqueConstraint(
            "principal_type", "principal_id", "role_id", "scope_hash",
            name="uq_binding_principal_role_scope"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    principal_type: Mapped[PrincipalType] = mapped_column(SQLEnum(PrincipalType))
    principal_id: Mapped[str] = mapped_column(String(36))
    role_id: Mapped[str] = mapped_column(String(36))
    scope_kind: Mapped[ScopeKind] = mapped_column(SQLEnum(ScopeKind))
    scope_value: Mapped[dict] = mapped_column(JSON)
    scope_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
