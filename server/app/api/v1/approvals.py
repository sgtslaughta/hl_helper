"""Approvals API routes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from server.app.api.state import get_app_state
from server.app.api.middleware.admin_auth import admin_required
from server.app.models import Approval
from server.app.pagination import apply_cursor, build_page
from server.app.rbac.approvals import ApprovalEngine

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


class ApprovalCreate(BaseModel):
    """Request body for creating an approval.

    Note: requester_id is derived from X-Acting-Principal header.
    """

    subject_type: Literal["command", "task", "policy_change"]
    subject_id: str
    policy: Literal["single", "two_person", "single_second_factor"]
    ttl_minutes: int = Field(default=10, ge=1, le=1440)


class ApprovalDecide(BaseModel):
    """Request body for deciding an approval.

    Note: decider_id is derived from X-Acting-Principal header.
    """

    decision: Literal["approve", "reject"]
    mfa_proof: str | None = None
    reason: str | None = None


class ApprovalListItemOut(BaseModel):
    """Approval item in list responses (without mfa_proof for privacy)."""

    id: str
    subject_type: str
    subject_id: str
    policy: str
    requester_id: str
    state: str
    decided_by_id: str | None
    decided_at: datetime | None
    rejected_reason: str | None
    expires_at: datetime
    created_at: datetime
    # NOTE: mfa_proof intentionally redacted from list responses (privacy).


class ApprovalOut(BaseModel):
    """Approval object in responses (mfa_proof_hash never exposed)."""

    id: str
    subject_type: str
    subject_id: str
    policy: str
    requester_id: str
    state: str
    decided_by_id: str | None
    decided_at: datetime | None
    rejected_reason: str | None
    expires_at: datetime
    created_at: datetime


class ApprovalDecisionOut(BaseModel):
    """Response from decide endpoint."""

    approved: bool
    state: str
    rejected_reason: str | None


class ApprovalsPage(BaseModel):
    """Paginated response for list approvals."""

    items: list[ApprovalListItemOut]
    next_cursor: str | None


@router.get(
    "",
    response_model=ApprovalsPage,
    dependencies=[Depends(admin_required)],
)
async def list_approvals(
    request: Request,
    subject_type: str | None = None,
    state: str | None = None,
    cursor: str | None = None,
    limit: int = 100,
) -> ApprovalsPage:
    """List approvals with cursor pagination, optionally filtered by subject_type and state.

    Requires admin authentication.
    Supports ?cursor= and ?limit= query params (limit default 100, max 500).
    Returns next_cursor if more items exist.
    """
    # Clamp limit
    limit = min(max(1, limit), 500)

    sm = get_app_state(request).sessionmaker
    async with sm() as session:
        query = select(Approval)
        if subject_type:
            query = query.where(Approval.subject_type == subject_type)
        if state:
            query = query.where(Approval.state == state)

        # Apply cursor pagination: sort by created_at desc, id desc
        query = apply_cursor(
            query,
            sort_column=Approval.created_at,
            id_column=Approval.id,
            cursor=cursor,
            limit=limit,
            descending=True,
        )
        rows = (await session.execute(query)).scalars().all()

    # Build page with next_cursor if needed
    page = build_page(rows, limit=limit, sort_attr="created_at", id_attr="id")

    return ApprovalsPage(
        items=[
            ApprovalListItemOut(
                id=r.id,
                subject_type=r.subject_type,
                subject_id=r.subject_id,
                policy=r.policy,
                requester_id=r.requester_id,
                state=r.state,
                decided_by_id=r.decided_by_id,
                decided_at=r.decided_at,
                rejected_reason=r.rejected_reason,
                expires_at=r.expires_at,
                created_at=r.created_at,
            )
            for r in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{approval_id}",
    response_model=ApprovalOut,
    dependencies=[Depends(admin_required)],
)
async def get_approval(request: Request, approval_id: str) -> ApprovalOut:
    """Get a single approval by id.

    Requires admin authentication.
    Returns 404 if not found.
    """
    sm = get_app_state(request).sessionmaker
    async with sm() as session:
        row = await session.scalar(
            select(Approval).where(Approval.id == approval_id)
        )

    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")

    return ApprovalOut(
        id=row.id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        policy=row.policy,
        requester_id=row.requester_id,
        state=row.state,
        decided_by_id=row.decided_by_id,
        decided_at=row.decided_at,
        rejected_reason=row.rejected_reason,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


@router.post(
    "",
    response_model=ApprovalOut,
    status_code=201,
    dependencies=[Depends(admin_required)],
)
async def create_approval(request: Request, body: ApprovalCreate) -> ApprovalOut:
    """Create an approval request.

    Requires admin authentication and X-Acting-Principal header.
    Returns 201 with the created approval.
    """
    # TODO(C3): replace X-Acting-Principal header with current_principal once user auth is wired
    requester_id = request.headers.get("X-Acting-Principal", "").strip()
    if not requester_id:
        raise HTTPException(status_code=400, detail="acting_principal_required")

    sm = get_app_state(request).sessionmaker
    async with sm() as session:
        engine = ApprovalEngine(session, ttl=timedelta(minutes=body.ttl_minutes))
        approval = await engine.request(
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            policy=body.policy,
            requester_id=requester_id,
            approval_id=str(uuid4()),
        )
        await session.commit()

    return ApprovalOut(
        id=approval.id,
        subject_type=approval.subject_type,
        subject_id=approval.subject_id,
        policy=approval.policy,
        requester_id=approval.requester_id,
        state=approval.state,
        decided_by_id=approval.decided_by_id,
        decided_at=approval.decided_at,
        rejected_reason=approval.rejected_reason,
        expires_at=approval.expires_at,
        created_at=approval.created_at,
    )


@router.post(
    "/{approval_id}/decisions",
    response_model=ApprovalDecisionOut,
    dependencies=[Depends(admin_required)],
)
async def decide_approval(
    request: Request, approval_id: str, body: ApprovalDecide
) -> ApprovalDecisionOut:
    """Decide on an approval.

    Requires admin authentication and X-Acting-Principal header.
    Returns 404 if approval not found.
    Returns 200 with decision result.
    """
    # TODO(C3): replace X-Acting-Principal header with current_principal once user auth is wired
    decider_id = request.headers.get("X-Acting-Principal", "").strip()
    if not decider_id:
        raise HTTPException(status_code=400, detail="acting_principal_required")

    sm = get_app_state(request).sessionmaker
    async with sm() as session:
        engine = ApprovalEngine(session)
        result = await engine.decide(
            approval_id,
            decider_id=decider_id,
            decision=body.decision,
            mfa_proof=body.mfa_proof,
            reason=body.reason,
        )
        await session.commit()

    # Check if approval exists (not_found is returned by decide if it doesn't)
    if result.rejected_reason == "not_found":
        raise HTTPException(status_code=404, detail="Approval not found")

    return ApprovalDecisionOut(
        approved=result.approved,
        state=result.state,
        rejected_reason=result.rejected_reason,
    )
