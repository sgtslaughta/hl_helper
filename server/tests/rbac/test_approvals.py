import pytest
from datetime import datetime, timedelta, timezone

from server.app.rbac.approvals import ApprovalEngine, DEFAULT_TTL


@pytest.mark.asyncio
async def test_two_person_rejects_same_principal(sm):
    async with sm() as session:
        eng = ApprovalEngine(session)
        await eng.request(
            subject_type="command", subject_id="c-1",
            policy="two_person", requester_id="u-1", approval_id="a-1",
        )
        await session.commit()
        res = await eng.decide("a-1", decider_id="u-1", decision="approve")
        await session.commit()
        assert res.approved is False
        assert res.rejected_reason == "same_principal"


@pytest.mark.asyncio
async def test_two_person_approves_with_different_principal(sm):
    async with sm() as session:
        eng = ApprovalEngine(session)
        await eng.request(
            subject_type="command", subject_id="c-2",
            policy="two_person", requester_id="u-1", approval_id="a-2",
        )
        await session.commit()
        res = await eng.decide("a-2", decider_id="u-2", decision="approve")
        await session.commit()
        assert res.approved is True
        assert res.state == "approved"


@pytest.mark.asyncio
async def test_single_second_factor_requires_mfa_proof(sm):
    async with sm() as session:
        eng = ApprovalEngine(session)
        await eng.request(
            subject_type="task", subject_id="t-1",
            policy="single_second_factor", requester_id="u-1", approval_id="a-3",
        )
        await session.commit()
        # No proof — stays pending with hint
        res = await eng.decide("a-3", decider_id="u-1", decision="approve", mfa_proof=None)
        assert res.approved is False
        assert res.state == "pending"
        assert res.rejected_reason == "mfa_required"
        # With proof — approved
        res2 = await eng.decide("a-3", decider_id="u-1", decision="approve", mfa_proof="totp:123456")
        await session.commit()
        assert res2.approved is True


@pytest.mark.asyncio
async def test_approval_expires(sm):
    async with sm() as session:
        eng = ApprovalEngine(session, ttl=timedelta(minutes=1))
        now = datetime.now(timezone.utc)
        await eng.request(
            subject_type="command", subject_id="c-3",
            policy="single", requester_id="u-1", approval_id="a-4", now=now,
        )
        await session.commit()
        # Advance past TTL
        future = now + timedelta(minutes=2)
        s = await eng.state("a-4", now=future)
        assert s == "expired"


@pytest.mark.asyncio
async def test_decide_after_expiry_returns_expired(sm):
    async with sm() as session:
        eng = ApprovalEngine(session, ttl=timedelta(minutes=1))
        now = datetime.now(timezone.utc)
        await eng.request(
            subject_type="task", subject_id="t-2",
            policy="single", requester_id="u-1", approval_id="a-5", now=now,
        )
        await session.commit()
        future = now + timedelta(minutes=2)
        res = await eng.decide("a-5", decider_id="u-2", decision="approve", now=future)
        assert res.approved is False
        assert res.state == "expired"


@pytest.mark.asyncio
async def test_reject_records_reason(sm):
    async with sm() as session:
        eng = ApprovalEngine(session)
        await eng.request(
            subject_type="command", subject_id="c-4",
            policy="single", requester_id="u-1", approval_id="a-6",
        )
        await session.commit()
        res = await eng.decide("a-6", decider_id="u-2", decision="reject",
                              reason="too_risky")
        await session.commit()
        assert res.approved is False
        assert res.state == "rejected"
        assert res.rejected_reason == "too_risky"


@pytest.mark.asyncio
async def test_default_ttl_is_10_minutes():
    assert DEFAULT_TTL == timedelta(minutes=10)
