"""Tests for the make_test_app_state helper."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.lifespan import AppState
from server.tests._helpers.app_state import make_test_app_state


@pytest.mark.asyncio
async def test_make_test_app_state_minimal(sm: async_sessionmaker) -> None:
    """Pass only sessionmaker; assert returned AppState has it.

    Minimal AppState should:
    - Accept sessionmaker as required argument
    - Return an actual AppState dataclass (not SimpleNamespace)
    - Have sessionmaker set to the provided value
    - Have sensible defaults for other fields
    """
    state = make_test_app_state(sessionmaker=sm)

    assert isinstance(state, AppState)
    assert state.sessionmaker is sm


@pytest.mark.asyncio
async def test_make_test_app_state_full(
    sm: async_sessionmaker,
    tmp_path: Path,
) -> None:
    """Pass explicit overrides; assert respected."""
    from server.app.audit.sql_chain import SqlAuditChain
    from server.app.crypto.signing import FileBackend

    signing_backend = FileBackend.bootstrap(tmp_path / "signing")
    audit_chain = SqlAuditChain(signing_backend, checkpoint_interval=100)

    state = make_test_app_state(
        sessionmaker=sm,
        signing_backend=signing_backend,
        audit_chain=audit_chain,
    )

    assert isinstance(state, AppState)
    assert state.sessionmaker is sm
    assert state.signing_backend is signing_backend
    assert state.audit_chain is audit_chain
