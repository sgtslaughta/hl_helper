"""Approval model — represents an approval request for an action."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, Enum as SQLEnum, Index, String, func, LargeBinary, JSON
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class ApprovalSubjectType(str, Enum):
    """Type of entity being approved."""

    COMMAND = "command"
    TASK = "task"
    POLICY_CHANGE = "policy_change"


class ApprovalPolicy(str, Enum):
    """Approval policy required."""

    SINGLE = "single"
    TWO_PERSON = "two_person"
    SINGLE_SECOND_FACTOR = "single_second_factor"


class ApprovalState(str, Enum):
    """State of an approval."""

    PENDING = "pending"
    PENDING_SECOND = "pending_second"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Approval(Base):
    """Approval table — represents an approval request for an action.

    State machine (allowed transitions):
    - pending → pending_second (two_person policy, first approve from non-requester)
    - pending → approved (single or single_second_factor with valid MFA, or two_person with same decider as first)
    - pending → rejected (when decision="reject")
    - pending_second → approved (two_person, second approve from third principal)
    - pending_second → rejected (two_person, reject decision)
    - pending/pending_second → expired (when expires_at < now)
    - approved, rejected, expired → (terminal states, no further transitions)
    """

    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approval_subject", "subject_type", "subject_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_type: Mapped[ApprovalSubjectType] = mapped_column(
        SQLEnum(ApprovalSubjectType)
    )
    subject_id: Mapped[str] = mapped_column(String(36))
    policy: Mapped[ApprovalPolicy] = mapped_column(SQLEnum(ApprovalPolicy))
    requester_id: Mapped[str] = mapped_column(String(36))
    state: Mapped[ApprovalState] = mapped_column(
        SQLEnum(ApprovalState), default=ApprovalState.PENDING, server_default=ApprovalState.PENDING
    )
    first_decider_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mfa_proof_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
