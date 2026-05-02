"""Tests for Schedule, MaintenanceWindow, UpdatePolicy, and Approval models."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.models import Schedule, MaintenanceWindow, UpdatePolicy, Approval


@pytest.mark.asyncio
async def test_schedule_create(sm):
    """Test basic Schedule creation with defaults."""
    async with sm() as session:
        s = Schedule(
            id="s-1",
            name="nightly-update",
            cron_expr="0 3 * * *",
            payload_kind="pkg_update",
            payload={"classes": ["security"]},
            target_selector={"group_id": "g-prod"},
        )
        session.add(s)
        await session.commit()
        got = await session.scalar(select(Schedule).where(Schedule.id == "s-1"))
        assert got.timezone == "UTC"
        assert got.enabled is True
        assert got.missed_runs_policy == "skip"


@pytest.mark.asyncio
async def test_maintenance_window_duration_check(sm):
    """Test that zero/negative duration fails at DB level (CHECK constraint)."""
    async with sm() as session:
        bad = MaintenanceWindow(
            id="mw-bad",
            name="bad",
            start_cron="0 0 * * 0",
            duration_minutes=0,
            target_selector={},
            kind="allow",
        )
        session.add(bad)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_maintenance_window_blackout_overlap_data_only(sm):
    """Blackout windows store kind correctly; overlap detection happens in app, not DB."""
    async with sm() as session:
        mw = MaintenanceWindow(
            id="mw-1",
            name="prod-blackout",
            start_cron="0 9 * * 1-5",
            duration_minutes=480,
            target_selector={"tag": {"key": "env", "value": "prod"}},
            kind="blackout",
        )
        session.add(mw)
        await session.commit()
        got = await session.scalar(
            select(MaintenanceWindow).where(MaintenanceWindow.id == "mw-1")
        )
        assert got.kind == "blackout"
        assert got.duration_minutes == 480


@pytest.mark.asyncio
async def test_update_policy_create(sm):
    """Test basic UpdatePolicy creation with defaults."""
    async with sm() as session:
        p = UpdatePolicy(
            id="p-1",
            name="security-only",
            target_selector={"group_id": "g-prod"},
            auto_apply_classes=["security"],
            reboot_policy="if_required",
            breaking_change_policy="approve",
        )
        session.add(p)
        await session.commit()
        got = await session.scalar(
            select(UpdatePolicy).where(UpdatePolicy.id == "p-1")
        )
        assert got.approval_required is False
        assert got.auto_apply_classes == ["security"]


@pytest.mark.asyncio
async def test_approval_state_machine(sm):
    """Approval defaults to pending; can transition to approved/rejected/expired."""
    async with sm() as session:
        now = datetime.now(timezone.utc)
        a = Approval(
            id="a-1",
            subject_type="command",
            subject_id="c-1",
            policy="two_person",
            requester_id="u-requester",
            expires_at=now + timedelta(minutes=10),
        )
        session.add(a)
        await session.commit()
        got = await session.scalar(select(Approval).where(Approval.id == "a-1"))
        assert got.state == "pending"
        assert got.decided_by_id is None
        # Transition
        got.state = "approved"
        got.decided_by_id = "u-decider"
        got.decided_at = now
        await session.commit()
        again = await session.scalar(select(Approval).where(Approval.id == "a-1"))
        assert again.state == "approved"
        assert again.decided_by_id == "u-decider"


@pytest.mark.asyncio
async def test_approval_rejection_with_reason(sm):
    """Test Approval with rejection state and reason."""
    async with sm() as session:
        now = datetime.now(timezone.utc)
        a = Approval(
            id="a-2",
            subject_type="task",
            subject_id="t-1",
            policy="single",
            requester_id="u-r",
            expires_at=now + timedelta(minutes=10),
            state="rejected",
            rejected_reason="same_principal",
            decided_by_id="u-r",
            decided_at=now,
        )
        session.add(a)
        await session.commit()
        got = await session.scalar(select(Approval).where(Approval.id == "a-2"))
        assert got.rejected_reason == "same_principal"
