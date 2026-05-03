"""API endpoints for audit log queries and verification."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, AsyncGenerator

from fastapi import APIRouter, Depends, Query, Request

if TYPE_CHECKING:
    from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, select

from server.app.api.middleware.admin_auth import admin_required
from server.app.audit.chain import compute_entry_hash
from server.app.models.audit import AuditEntry
from server.app.pagination import apply_cursor, build_page

router = APIRouter(prefix="/v1/audit", tags=["audit"])


class AuditEntryOut(BaseModel):
    """Audit entry for API response."""

    sequence: int
    timestamp: datetime
    actor: str
    action: str
    subject: str | None
    payload: dict[str, object]
    prev_hash: str  # hex-encoded
    entry_hash: str  # hex-encoded


class AuditPage(BaseModel):
    """Paginated audit entries."""

    items: list[AuditEntryOut]
    next_cursor: str | None


class AuditVerifyRequest(BaseModel):
    """Request to verify audit chain."""

    from_seq: int | None = None
    to_seq: int | None = None


class AuditVerifyResult(BaseModel):
    """Result of audit chain verification."""

    ok: bool
    break_at_seq: int | None = None
    total_entries: int
    message: str | None = None


def _entry_to_out(e: AuditEntry) -> AuditEntryOut:
    """Convert AuditEntry to AuditEntryOut."""
    return AuditEntryOut(
        sequence=e.sequence,
        timestamp=e.timestamp,
        actor=e.actor,
        action=e.action,
        subject=e.subject,
        payload=e.payload,
        prev_hash=e.prev_hash.hex(),
        entry_hash=e.entry_hash.hex(),
    )


def _build_filters(
    actor: str | None,
    action: str | None,
    subject: str | None,
    since: datetime | None,
    before: datetime | None,
) -> object | None:
    """Build WHERE clause from filters."""
    conds: list[object] = []
    if actor:
        conds.append(AuditEntry.actor == actor)
    if action:
        conds.append(AuditEntry.action == action)
    if subject:
        conds.append(AuditEntry.subject == subject)
    if since:
        conds.append(AuditEntry.timestamp >= since)
    if before:
        conds.append(AuditEntry.timestamp < before)
    return and_(*conds) if conds else None  # type: ignore[arg-type]


@router.get("", response_model=AuditPage, dependencies=[Depends(admin_required)])
async def list_audit(
    req: Request,
    actor: str | None = None,
    action: str | None = None,
    subject: str | None = None,
    since: datetime | None = None,
    before: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> AuditPage:
    """List audit entries with cursor pagination and filtering."""
    sm = req.app.state.sessionmaker
    async with sm() as session:
        stmt = select(AuditEntry)
        f = _build_filters(actor, action, subject, since, before)
        if f is not None:
            stmt = stmt.where(f)  # type: ignore[arg-type]
        stmt = apply_cursor(
            stmt,
            sort_column=AuditEntry.sequence,
            id_column=AuditEntry.sequence,
            cursor=cursor,
            limit=limit,
        )
        rows = (await session.execute(stmt)).scalars().all()
        page = build_page(rows, limit=limit, sort_attr="sequence", id_attr="sequence")

    return AuditPage(items=[_entry_to_out(e) for e in page.items], next_cursor=page.next_cursor)


@router.get("/export", dependencies=[Depends(admin_required)])
async def export_audit(
    req: Request,
    actor: str | None = None,
    action: str | None = None,
    subject: str | None = None,
    since: datetime | None = None,
    before: datetime | None = None,
) -> "StreamingResponse":
    """Stream all matching entries as JSON Lines (NDJSON)."""
    from fastapi.responses import StreamingResponse

    sm = req.app.state.sessionmaker
    f = _build_filters(actor, action, subject, since, before)

    async def generate() -> "AsyncGenerator[bytes, None]":
        """Generate JSON Lines from audit entries."""
        async with sm() as session:
            stmt = select(AuditEntry).order_by(AuditEntry.sequence.asc())
            if f is not None:
                stmt = stmt.where(f)  # type: ignore[arg-type]
            rows = (await session.execute(stmt)).scalars().all()
            for e in rows:
                yield json.dumps(_entry_to_out(e).model_dump(mode="json")).encode() + b"\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/actions/verify", response_model=AuditVerifyResult, dependencies=[Depends(admin_required)])
async def verify_chain(req: Request, body: AuditVerifyRequest) -> AuditVerifyResult:
    """Re-walk the SHA-256 hash chain and report first break."""
    from server.app.audit.chain import GENESIS_HASH

    sm = req.app.state.sessionmaker
    async with sm() as session:
        stmt = select(AuditEntry).order_by(AuditEntry.sequence.asc())
        if body.from_seq is not None:
            stmt = stmt.where(AuditEntry.sequence >= body.from_seq)
        if body.to_seq is not None:
            stmt = stmt.where(AuditEntry.sequence <= body.to_seq)
        rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        return AuditVerifyResult(ok=True, break_at_seq=None, total_entries=0, message="empty chain in range")

    # Verify chain linkage
    from datetime import timezone

    for i, e in enumerate(rows):
        # First entry must have prev_hash == GENESIS_HASH
        if i == 0:
            if e.prev_hash != GENESIS_HASH:
                return AuditVerifyResult(
                    ok=False,
                    break_at_seq=e.sequence,
                    total_entries=len(rows),
                    message="first entry prev_hash != GENESIS_HASH",
                )
        else:
            # Subsequent entries: prev_hash must match predecessor's entry_hash
            if e.prev_hash != rows[i - 1].entry_hash:
                return AuditVerifyResult(
                    ok=False,
                    break_at_seq=e.sequence,
                    total_entries=len(rows),
                    message=f"prev_hash mismatch at seq={e.sequence}",
                )

        # Ensure timestamp is timezone-aware for hash computation
        ts = e.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # Recompute entry_hash using the same function as sql_chain
        expected_hash = compute_entry_hash(
            sequence=e.sequence,
            timestamp=ts,
            actor=e.actor,
            action=e.action,
            subject=e.subject,
            payload=e.payload,
            prev_hash=e.prev_hash,
        )

        if e.entry_hash != expected_hash:
            return AuditVerifyResult(
                ok=False,
                break_at_seq=e.sequence,
                total_entries=len(rows),
                message=f"entry_hash mismatch at seq={e.sequence}",
            )

    return AuditVerifyResult(ok=True, break_at_seq=None, total_entries=len(rows))
