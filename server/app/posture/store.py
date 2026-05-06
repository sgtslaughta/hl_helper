"""Posture findings store — async CRUD operations.

@brief Provides functions for upserting, querying, suppressing, and
       expiring posture findings in the ``posture_findings`` table.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.posture.model import Finding, PostureFindingRow, SEVERITY_ORDER


async def upsert_finding(
    sm: async_sessionmaker[AsyncSession],
    finding: Finding,
) -> PostureFindingRow:
    """@brief Insert or update a posture finding.

    On insert, ``first_seen`` and ``last_seen`` are set to now.
    On update, ``first_seen`` is preserved and ``last_seen`` is bumped.

    @param sm      Async sessionmaker for database access.
    @param finding The in-memory finding to persist.
    @return The persisted ``PostureFindingRow``.
    """
    now = datetime.now(timezone.utc)
    async with sm() as session:
        row = await session.get(PostureFindingRow, finding.id)
        if row is None:
            row = PostureFindingRow(
                id=finding.id,
                rule=finding.rule or finding.id,
                severity=finding.severity,
                title=finding.title,
                summary=finding.summary,
                subject_kind=finding.subject_kind,
                subject_id=finding.subject_id,
                fix_action_url=finding.fix_action_url,
                docs_url=finding.docs_url,
                first_seen=now,
                last_seen=now,
            )
            session.add(row)
        else:
            row.rule = finding.rule or finding.id
            row.severity = finding.severity
            row.title = finding.title
            row.summary = finding.summary
            row.subject_kind = finding.subject_kind
            row.subject_id = finding.subject_id
            row.fix_action_url = finding.fix_action_url
            row.docs_url = finding.docs_url
            row.last_seen = now
        await session.commit()
        await session.refresh(row)
    return row


async def get_finding(
    sm: async_sessionmaker[AsyncSession],
    finding_id: str,
) -> PostureFindingRow | None:
    """@brief Retrieve a single posture finding by ID.

    @param sm         Async sessionmaker for database access.
    @param finding_id Primary key of the finding.
    @return The row, or ``None`` if not found.
    """
    async with sm() as session:
        return await session.get(PostureFindingRow, finding_id)


async def list_findings(
    sm: async_sessionmaker[AsyncSession],
    *,
    severity: str | None = None,
    suppressed: bool | None = None,
    subject_kind: str | None = None,
    subject_id: str | None = None,
) -> list[PostureFindingRow]:
    """@brief List posture findings with optional filters, sorted by severity.

    @param sm           Async sessionmaker for database access.
    @param severity     Filter to a single severity level (optional).
    @param suppressed   When ``True``, return only suppressed findings.
                        When ``False``, return only non-suppressed. ``None`` = all.
    @param subject_kind Filter by subject_kind (e.g., 'host', 'user').
    @param subject_id   Filter by subject_id (requires subject_kind to be meaningful).
    @return List of ``PostureFindingRow`` sorted by severity (most severe first).
    """
    async with sm() as session:
        stmt = select(PostureFindingRow)
        if severity is not None:
            stmt = stmt.where(PostureFindingRow.severity == severity)
        if suppressed is True:
            stmt = stmt.where(PostureFindingRow.suppressed_until.is_not(None))
        elif suppressed is False:
            stmt = stmt.where(PostureFindingRow.suppressed_until.is_(None))
        if subject_kind is not None:
            stmt = stmt.where(PostureFindingRow.subject_kind == subject_kind)
        if subject_id is not None:
            stmt = stmt.where(PostureFindingRow.subject_id == subject_id)
        rows = (await session.execute(stmt)).scalars().all()

    return sorted(rows, key=lambda r: SEVERITY_ORDER.get(r.severity, 99))


async def suppress_finding(
    sm: async_sessionmaker[AsyncSession],
    finding_id: str,
    *,
    suppressed_by: str,
    reason: str,
    expires_at: datetime,
) -> PostureFindingRow | None:
    """@brief Mark a finding as suppressed.

    @param sm            Async sessionmaker for database access.
    @param finding_id    ID of the finding to suppress.
    @param suppressed_by Identity of the actor suppressing the finding.
    @param reason        Free-text reason for suppression.
    @param expires_at    When the suppression expires (re-activates the finding).
    @return The updated row, or ``None`` if not found.
    """
    async with sm() as session:
        row = await session.get(PostureFindingRow, finding_id)
        if row is None:
            return None
        row.suppressed_by = suppressed_by
        row.suppressed_reason = reason
        row.suppressed_until = expires_at
        await session.commit()
        await session.refresh(row)
    return row


async def unsuppress_finding(
    sm: async_sessionmaker[AsyncSession],
    finding_id: str,
) -> PostureFindingRow | None:
    """@brief Clear suppression on a finding.

    @param sm         Async sessionmaker for database access.
    @param finding_id ID of the finding to unsuppress.
    @return The updated row, or ``None`` if not found.
    """
    async with sm() as session:
        row = await session.get(PostureFindingRow, finding_id)
        if row is None:
            return None
        row.suppressed_by = None
        row.suppressed_reason = None
        row.suppressed_until = None
        await session.commit()
        await session.refresh(row)
    return row


async def expire_suppressions(
    sm: async_sessionmaker[AsyncSession],
) -> int:
    """@brief Clear suppressions whose ``suppressed_until`` is in the past.

    @param sm Async sessionmaker for database access.
    @return Number of findings whose suppression was expired.
    """
    now = datetime.now(timezone.utc)
    async with sm() as session:
        stmt = (
            update(PostureFindingRow)
            .where(
                PostureFindingRow.suppressed_until.is_not(None),
                PostureFindingRow.suppressed_until < now,
            )
            .values(
                suppressed_until=None,
                suppressed_by=None,
                suppressed_reason=None,
            )
        )
        result = await session.execute(stmt)
        await session.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
