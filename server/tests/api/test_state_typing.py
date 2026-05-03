"""Tests for AppStateProtocol typing coverage."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.api.state import AppStateProtocol
from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.dispatcher.dispatcher import CommandDispatcher as ApiCommandDispatcher
from server.app.events.bus import Bus
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.grpc.result_handler import ResultHandler
from server.app.lifespan import AppState
from server.app.enrollment.service import EnrollmentService
from server.app.revocation.service import RevocationService


def test_protocol_satisfied_by_app_state() -> None:
    """AppState instance satisfies AppStateProtocol."""
    from unittest.mock import MagicMock

    # Create minimal fake instances for required types
    bus = MagicMock(spec=Bus)
    ca = MagicMock(spec=InternalCA)
    signing_backend = MagicMock(spec=FileBackend)
    engine = MagicMock()
    sm = MagicMock(spec=async_sessionmaker)
    dispatcher = MagicMock(spec=CommandDispatcher)
    api_dispatcher = MagicMock(spec=ApiCommandDispatcher)
    audit_chain = MagicMock(spec=SqlAuditChain)
    result_handler = MagicMock(spec=ResultHandler)
    revocation_service = MagicMock(spec=RevocationService)
    enrollment_service = MagicMock(spec=EnrollmentService)

    state = AppState(
        bus=bus,
        ca=ca,
        signing_backend=signing_backend,
        engine=engine,
        sessionmaker=sm,
        dispatcher=dispatcher,
        api_dispatcher=api_dispatcher,
        audit_chain=audit_chain,
        result_handler=result_handler,
        revocation_service=revocation_service,
        enrollment_service=enrollment_service,
    )

    # Verify it has all required attributes
    assert hasattr(state, "bus")
    assert hasattr(state, "ca")
    assert hasattr(state, "signing_backend")
    assert hasattr(state, "engine")
    assert hasattr(state, "sessionmaker")
    assert hasattr(state, "dispatcher")
    assert hasattr(state, "api_dispatcher")
    assert hasattr(state, "audit_chain")
    assert hasattr(state, "result_handler")
    assert hasattr(state, "revocation_service")
    assert hasattr(state, "enrollment_service")

    # Runtime check: AppState instance satisfies AppStateProtocol
    assert isinstance(state, AppStateProtocol)




def test_get_app_state_raises_when_uninitialized() -> None:
    """get_app_state raises RuntimeError when app_state not initialized."""
    from unittest.mock import MagicMock
    from server.app.api.state import get_app_state

    # Create a mock request with an app.state that has no app_state attribute
    request = MagicMock()
    request.app.state = MagicMock(spec=[])  # Empty spec, no attributes

    # Should raise RuntimeError with helpful message
    with pytest.raises(RuntimeError) as exc_info:
        get_app_state(request)

    assert "AppState not initialized" in str(exc_info.value)
    assert "make_test_app_state" in str(exc_info.value)
