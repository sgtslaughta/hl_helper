"""Tests for posture inspector (cross-component aggregator)."""

from __future__ import annotations

from typing import AsyncIterator
from unittest import mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.posture.model import Finding
from server.app.posture.inspector import run_inspection
from server.app.posture.store import get_finding


@pytest.fixture
async def session(sm: async_sessionmaker) -> AsyncIterator[AsyncSession]:
    """@brief Yield a single async session for test use."""
    async with sm() as s:
        yield s


def _fake_finding(id: str, severity: str = "medium") -> Finding:
    """@brief Build a minimal Finding for test use."""
    return Finding(
        id=id,
        severity=severity,
        title=f"Title for {id}",
        summary=f"Summary for {id}",
        rule=id,
    )


async def _finding_fn_a(sm, **kwargs) -> Finding | None:
    """@brief Stub finding function returning a critical finding."""
    return _fake_finding("insp_a", severity="critical")


async def _finding_fn_b(sm, **kwargs) -> Finding | None:
    """@brief Stub finding function returning a low finding."""
    return _fake_finding("insp_b", severity="low")


async def _finding_fn_none(sm, **kwargs) -> Finding | None:
    """@brief Stub finding function that returns None (no issue)."""
    return None


async def _finding_fn_raises(sm, **kwargs) -> Finding | None:
    """@brief Stub finding function that raises an error."""
    raise RuntimeError("simulated failure")


# ---------------------------------------------------------------------------
# run_inspection
# ---------------------------------------------------------------------------


async def test_run_inspection_returns_findings(sm: async_sessionmaker):
    """@brief run_inspection collects results from all finding functions."""
    fns = [_finding_fn_a, _finding_fn_b]
    with mock.patch("server.app.posture.inspector.ALL_FINDINGS", fns):
        results = await run_inspection(sm)

    ids = [f.id for f in results]
    assert "insp_a" in ids
    assert "insp_b" in ids


async def test_run_inspection_handles_partial_failures(sm: async_sessionmaker):
    """@brief Failing finding functions do not prevent other findings from returning."""
    fns = [_finding_fn_a, _finding_fn_raises, _finding_fn_b]
    with mock.patch("server.app.posture.inspector.ALL_FINDINGS", fns):
        results = await run_inspection(sm)

    ids = [f.id for f in results]
    assert "insp_a" in ids
    assert "insp_b" in ids
    assert len(results) == 2


async def test_run_inspection_skips_none_results(sm: async_sessionmaker):
    """@brief Finding functions that return None are excluded from results."""
    fns = [_finding_fn_a, _finding_fn_none]
    with mock.patch("server.app.posture.inspector.ALL_FINDINGS", fns):
        results = await run_inspection(sm)

    assert len(results) == 1
    assert results[0].id == "insp_a"


async def test_run_inspection_persists_findings(sm: async_sessionmaker, session: AsyncSession):
    """@brief Findings produced by inspection are persisted in the store."""
    fns = [_finding_fn_a, _finding_fn_b]
    with mock.patch("server.app.posture.inspector.ALL_FINDINGS", fns):
        await run_inspection(sm)

    row_a = await get_finding(sm, "insp_a")
    row_b = await get_finding(sm, "insp_b")
    assert row_a is not None
    assert row_a.severity == "critical"
    assert row_b is not None
    assert row_b.severity == "low"
