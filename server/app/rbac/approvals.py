"""Approval engine — gates high-risk subjects behind a policy + decider check."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models import Approval


DEFAULT_TTL = timedelta(minutes=10)
SubjectType = Literal["command", "task", "policy_change"]
Policy = Literal["single", "two_person", "single_second_factor"]


@dataclass(frozen=True)
class DecisionResult:
    approved: bool
    state: str  # "approved" | "rejected" | "pending" | "expired"
    rejected_reason: str | None = None


class ApprovalEngine:
    """Manages Approval rows. All methods take an AsyncSession; caller controls commits."""

    def __init__(self, session: AsyncSession, *, ttl: timedelta = DEFAULT_TTL) -> None:
        self._s = session
        self._ttl = ttl

    async def request(
        self,
        *,
        subject_type: SubjectType,
        subject_id: str,
        policy: Policy,
        requester_id: str,
        approval_id: str,
        now: datetime | None = None,
    ) -> Approval:
        now = now or datetime.now(timezone.utc)
        a = Approval(
            id=approval_id,
            subject_type=subject_type,
            subject_id=subject_id,
            policy=policy,
            requester_id=requester_id,
            state="pending",
            expires_at=now + self._ttl,
        )
        self._s.add(a)
        await self._s.flush()
        return a

    async def decide(
        self,
        approval_id: str,
        *,
        decider_id: str,
        decision: Literal["approve", "reject"],
        mfa_proof: str | None = None,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> DecisionResult:
        now = now or datetime.now(timezone.utc)
        a = await self._s.scalar(select(Approval).where(Approval.id == approval_id))
        if a is None:
            return DecisionResult(approved=False, state="rejected", rejected_reason="not_found")

        # Already terminal
        if a.state != "pending":
            return DecisionResult(approved=False, state=a.state, rejected_reason=a.rejected_reason)

        # Expiry check
        expires_at = a.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now >= expires_at:
            a.state = "expired"
            await self._s.flush()
            return DecisionResult(approved=False, state="expired", rejected_reason="expired")

        if decision == "reject":
            a.state = "rejected"
            a.decided_by_id = decider_id
            a.decided_at = now
            a.rejected_reason = reason or "rejected"
            await self._s.flush()
            return DecisionResult(approved=False, state="rejected", rejected_reason=a.rejected_reason)

        # decision == "approve"
        if a.policy == "two_person" and decider_id == a.requester_id:
            a.state = "rejected"
            a.decided_by_id = decider_id
            a.decided_at = now
            a.rejected_reason = "same_principal"
            await self._s.flush()
            return DecisionResult(approved=False, state="rejected", rejected_reason="same_principal")

        if a.policy == "single_second_factor" and not mfa_proof:
            return DecisionResult(approved=False, state="pending", rejected_reason="mfa_required")

        a.state = "approved"
        a.decided_by_id = decider_id
        a.decided_at = now
        a.mfa_proof = mfa_proof
        await self._s.flush()
        return DecisionResult(approved=True, state="approved")

    async def state(self, approval_id: str, *, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        a = await self._s.scalar(select(Approval).where(Approval.id == approval_id))
        if a is None:
            return "rejected"  # no row = doesn't exist; closed
        expires_at = a.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if a.state == "pending" and now >= expires_at:
            a.state = "expired"
            await self._s.flush()
            return "expired"
        return a.state
