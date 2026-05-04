"""Tests for ApprovalSweeper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from server.app.models import Approval
from server.app.models.approval import ApprovalState
from server.app.rbac.approval_sweeper import ApprovalSweeper


def _approval(state: str, expires_at: datetime) -> Approval:
    return Approval(
        id=str(uuid4()),
        subject_type="command",
        subject_id="c-1",
        policy="single",
        requester_id="u-r",
        state=state,
        expires_at=expires_at,
    )


@pytest.mark.asyncio
async def test_sweep_returns_zero_when_nothing_expired(sm) -> None:
    now = datetime.now(timezone.utc)
    async with sm() as s:
        s.add(_approval("pending", now + timedelta(minutes=5)))
        await s.commit()

    sweeper = ApprovalSweeper(sm)
    assert await sweeper.sweep(now=now) == 0


@pytest.mark.asyncio
async def test_sweep_expires_pending_past_ttl(sm) -> None:
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=1)

    async with sm() as s:
        a = _approval("pending", past)
        s.add(a)
        await s.commit()
        aid = a.id

    sweeper = ApprovalSweeper(sm)
    assert await sweeper.sweep(now=now) == 1

    async with sm() as s:
        row = await s.scalar(select(Approval).where(Approval.id == aid))
    assert row.state == ApprovalState.EXPIRED
    assert row.rejected_reason == "expired"


@pytest.mark.asyncio
async def test_sweep_expires_pending_second(sm) -> None:
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=1)

    async with sm() as s:
        a = _approval("pending_second", past)
        s.add(a)
        await s.commit()
        aid = a.id

    sweeper = ApprovalSweeper(sm)
    assert await sweeper.sweep(now=now) == 1

    async with sm() as s:
        row = await s.scalar(select(Approval).where(Approval.id == aid))
    assert row.state == ApprovalState.EXPIRED


@pytest.mark.asyncio
async def test_sweep_does_not_touch_terminal_states(sm) -> None:
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=1)
    async with sm() as s:
        a1 = _approval("approved", past)
        a2 = _approval("rejected", past)
        s.add_all([a1, a2])
        await s.commit()

    sweeper = ApprovalSweeper(sm)
    assert await sweeper.sweep(now=now) == 0


@pytest.mark.asyncio
async def test_sweep_idempotent(sm) -> None:
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=1)
    async with sm() as s:
        s.add(_approval("pending", past))
        s.add(_approval("pending", past))
        await s.commit()

    sweeper = ApprovalSweeper(sm)
    first = await sweeper.sweep(now=now)
    second = await sweeper.sweep(now=now)
    assert first == 2
    assert second == 0
