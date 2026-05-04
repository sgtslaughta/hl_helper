"""Tests for posture finding store CRUD operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.posture.model import Finding
from server.app.posture.store import (
    expire_suppressions,
    get_finding,
    list_findings,
    suppress_finding,
    unsuppress_finding,
    upsert_finding,
)


@pytest.fixture
async def session(sm: async_sessionmaker) -> AsyncIterator[AsyncSession]:
    """@brief Yield a single async session for test use."""
    async with sm() as s:
        yield s


def _make_finding(
    *,
    id: str = "test_finding_1",
    severity: str = "high",
    title: str = "Test Finding",
    summary: str = "A test finding",
    rule: str = "",
    subject_kind: str = "global",
    subject_id: str | None = None,
) -> Finding:
    """@brief Helper to build a Finding with sensible defaults."""
    return Finding(
        id=id,
        severity=severity,
        title=title,
        summary=summary,
        rule=rule or id,
        subject_kind=subject_kind,
        subject_id=subject_id,
    )


# ---------------------------------------------------------------------------
# upsert_finding
# ---------------------------------------------------------------------------


async def test_upsert_finding_creates_new_row(sm: async_sessionmaker, session: AsyncSession):
    """@brief Upserting a new finding sets first_seen and last_seen."""
    finding = _make_finding(id="new_finding", severity="critical")
    row = await upsert_finding(sm, finding)

    assert row.id == "new_finding"
    assert row.severity == "critical"
    assert row.title == "Test Finding"
    assert row.first_seen is not None
    assert row.last_seen is not None
    assert row.first_seen <= row.last_seen


async def test_upsert_finding_updates_existing_preserves_first_seen(
    sm: async_sessionmaker, session: AsyncSession
):
    """@brief Re-upserting preserves first_seen but bumps last_seen."""
    finding = _make_finding(id="dup_finding")
    row1 = await upsert_finding(sm, finding)
    original_first_seen = row1.first_seen

    updated = _make_finding(id="dup_finding", title="Updated Title")
    row2 = await upsert_finding(sm, updated)

    assert row2.first_seen == original_first_seen
    assert row2.last_seen >= row1.last_seen
    assert row2.title == "Updated Title"


# ---------------------------------------------------------------------------
# get_finding
# ---------------------------------------------------------------------------


async def test_get_finding_returns_row(sm: async_sessionmaker, session: AsyncSession):
    """@brief get_finding returns the row when it exists."""
    finding = _make_finding(id="get_me")
    await upsert_finding(sm, finding)

    row = await get_finding(sm, "get_me")
    assert row is not None
    assert row.id == "get_me"


async def test_get_finding_returns_none_for_missing(sm: async_sessionmaker):
    """@brief get_finding returns None for an unknown ID."""
    row = await get_finding(sm, "does_not_exist")
    assert row is None


# ---------------------------------------------------------------------------
# list_findings
# ---------------------------------------------------------------------------


async def test_list_findings_sorted_by_severity(sm: async_sessionmaker, session: AsyncSession):
    """@brief Findings are returned sorted by severity order."""
    for sev in ("low", "critical", "medium", "high", "info"):
        await upsert_finding(sm, _make_finding(id=f"f_{sev}", severity=sev))

    rows = await list_findings(sm)
    severities = [r.severity for r in rows]
    assert severities == ["critical", "high", "medium", "low", "info"]


async def test_list_findings_filter_by_severity(sm: async_sessionmaker, session: AsyncSession):
    """@brief Filtering by severity returns only matching findings."""
    await upsert_finding(sm, _make_finding(id="f_high", severity="high"))
    await upsert_finding(sm, _make_finding(id="f_low", severity="low"))

    rows = await list_findings(sm, severity="high")
    assert len(rows) == 1
    assert rows[0].id == "f_high"


async def test_list_findings_filter_suppressed(sm: async_sessionmaker, session: AsyncSession):
    """@brief Filtering suppressed=True returns only suppressed findings."""
    await upsert_finding(sm, _make_finding(id="active_f"))
    await upsert_finding(sm, _make_finding(id="suppressed_f"))
    await suppress_finding(
        sm,
        "suppressed_f",
        suppressed_by="admin",
        reason="testing",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    suppressed = await list_findings(sm, suppressed=True)
    assert len(suppressed) == 1
    assert suppressed[0].id == "suppressed_f"

    active = await list_findings(sm, suppressed=False)
    assert all(r.id != "suppressed_f" for r in active)


# ---------------------------------------------------------------------------
# suppress_finding / unsuppress_finding
# ---------------------------------------------------------------------------


async def test_suppress_finding_sets_fields(sm: async_sessionmaker, session: AsyncSession):
    """@brief suppress_finding populates suppressed_* columns."""
    await upsert_finding(sm, _make_finding(id="to_suppress"))
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    row = await suppress_finding(
        sm,
        "to_suppress",
        suppressed_by="admin@test",
        reason="false positive",
        expires_at=expires,
    )
    assert row is not None
    assert row.suppressed_by == "admin@test"
    assert row.suppressed_reason == "false positive"
    assert row.suppressed_until is not None


async def test_suppress_finding_returns_none_for_missing(sm: async_sessionmaker):
    """@brief suppress_finding returns None when finding not found."""
    row = await suppress_finding(
        sm,
        "ghost",
        suppressed_by="admin",
        reason="n/a",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert row is None


async def test_unsuppress_finding_clears_fields(sm: async_sessionmaker, session: AsyncSession):
    """@brief unsuppress_finding clears all suppressed_* columns."""
    await upsert_finding(sm, _make_finding(id="to_unsup"))
    await suppress_finding(
        sm,
        "to_unsup",
        suppressed_by="admin",
        reason="temp",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    row = await unsuppress_finding(sm, "to_unsup")
    assert row is not None
    assert row.suppressed_by is None
    assert row.suppressed_reason is None
    assert row.suppressed_until is None


async def test_unsuppress_finding_returns_none_for_missing(sm: async_sessionmaker):
    """@brief unsuppress_finding returns None when finding not found."""
    row = await unsuppress_finding(sm, "no_such_id")
    assert row is None


# ---------------------------------------------------------------------------
# expire_suppressions
# ---------------------------------------------------------------------------


async def test_expire_suppressions_clears_expired(sm: async_sessionmaker, session: AsyncSession):
    """@brief expire_suppressions clears entries whose suppressed_until is in the past."""
    await upsert_finding(sm, _make_finding(id="expired_sup"))
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await suppress_finding(
        sm,
        "expired_sup",
        suppressed_by="admin",
        reason="old",
        expires_at=past,
    )

    count = await expire_suppressions(sm)
    assert count == 1

    row = await get_finding(sm, "expired_sup")
    assert row is not None
    assert row.suppressed_until is None


async def test_expire_suppressions_ignores_future(sm: async_sessionmaker, session: AsyncSession):
    """@brief expire_suppressions does not touch future-dated suppressions."""
    await upsert_finding(sm, _make_finding(id="future_sup"))
    future = datetime.now(timezone.utc) + timedelta(days=30)
    await suppress_finding(
        sm,
        "future_sup",
        suppressed_by="admin",
        reason="keep",
        expires_at=future,
    )

    count = await expire_suppressions(sm)
    assert count == 0

    row = await get_finding(sm, "future_sup")
    assert row is not None
    assert row.suppressed_until is not None
