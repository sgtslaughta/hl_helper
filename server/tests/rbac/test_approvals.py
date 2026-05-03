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
async def test_two_person_first_approve_goes_to_pending_second(sm):
    """First approve on two_person approval transitions to pending_second."""
    async with sm() as session:
        eng = ApprovalEngine(session)
        await eng.request(
            subject_type="command", subject_id="c-2",
            policy="two_person", requester_id="u-1", approval_id="a-2",
        )
        await session.commit()
        res = await eng.decide("a-2", decider_id="u-2", decision="approve")
        await session.commit()
        assert res.approved is False
        assert res.state == "pending_second"


@pytest.mark.asyncio
async def test_two_person_second_approve_with_different_principal_approves(sm):
    """Second approve from different principal (not requester, not first decider) approves."""
    async with sm() as session:
        eng = ApprovalEngine(session)
        await eng.request(
            subject_type="command", subject_id="c-2b",
            policy="two_person", requester_id="u-1", approval_id="a-2b",
        )
        await session.commit()
        # First decision
        res1 = await eng.decide("a-2b", decider_id="u-2", decision="approve")
        await session.commit()
        assert res1.state == "pending_second"
        # Second decision from different principal
        res2 = await eng.decide("a-2b", decider_id="u-3", decision="approve")
        await session.commit()
        assert res2.approved is True
        assert res2.state == "approved"


@pytest.mark.asyncio
async def test_two_person_second_approve_same_first_decider_rejected(sm):
    """Second approve from same principal as first decider is rejected."""
    async with sm() as session:
        eng = ApprovalEngine(session)
        await eng.request(
            subject_type="command", subject_id="c-2c",
            policy="two_person", requester_id="u-1", approval_id="a-2c",
        )
        await session.commit()
        # First decision
        res1 = await eng.decide("a-2c", decider_id="u-2", decision="approve")
        await session.commit()
        assert res1.state == "pending_second"
        # Second decision from same principal as first — should reject
        res2 = await eng.decide("a-2c", decider_id="u-2", decision="approve")
        await session.commit()
        assert res2.approved is False
        assert res2.rejected_reason == "same_principal"


@pytest.mark.asyncio
async def test_single_second_factor_requires_mfa_proof(sm):
    async with sm() as session:
        eng = ApprovalEngine(session)
        await eng.request(
            subject_type="task", subject_id="t-1",
            policy="single_second_factor", requester_id="u-1", approval_id="a-3",
        )
        await session.commit()
        # No proof — fail-closed: rejected with mfa_required reason
        res = await eng.decide("a-3", decider_id="u-2", decision="approve", mfa_proof=None)
        assert res.approved is False
        assert res.rejected_reason == "mfa_required"
        # With a proof matching the StubMfaVerifier shape — approved
        valid_proof = "mfa_v1:chal-1:1700000000:abc-DEF_xyz"
        res2 = await eng.decide(
            "a-3", decider_id="u-2", decision="approve", mfa_proof=valid_proof
        )
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


@pytest.mark.asyncio
async def test_two_person_second_approve_by_first_decider_rejected(sm):
    """Second approve from same principal as first decider rejects."""
    async with sm() as session:
        eng = ApprovalEngine(session)
        await eng.request(
            subject_type="command", subject_id="c-5",
            policy="two_person", requester_id="u-1", approval_id="a-7",
        )
        await session.commit()
        # First decision by u-2
        res1 = await eng.decide("a-7", decider_id="u-2", decision="approve")
        await session.commit()
        assert res1.state == "pending_second"
        # Second decision by same principal (u-2) — should reject
        res2 = await eng.decide("a-7", decider_id="u-2", decision="approve")
        await session.commit()
        assert res2.approved is False
        assert res2.rejected_reason == "same_principal"
        assert res2.state == "rejected"


@pytest.mark.asyncio
async def test_reject_at_any_state_denies(sm):
    """Reject decision at any state → DENIED."""
    async with sm() as session:
        eng = ApprovalEngine(session)
        await eng.request(
            subject_type="command", subject_id="c-6",
            policy="two_person", requester_id="u-1", approval_id="a-8",
        )
        await session.commit()
        # First decision transitions to pending_second
        res1 = await eng.decide("a-8", decider_id="u-2", decision="approve")
        await session.commit()
        assert res1.state == "pending_second"
        # Reject from pending_second
        res2 = await eng.decide("a-8", decider_id="u-3", decision="reject", reason="security_concern")
        await session.commit()
        assert res2.approved is False
        assert res2.state == "rejected"
        assert res2.rejected_reason == "security_concern"
