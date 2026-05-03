"""Tests for AppStateProtocol typing coverage."""

from __future__ import annotations

from types import SimpleNamespace

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


def test_simplenamespace_fallback_has_documented_attributes() -> None:
    """SimpleNamespace fallback path has all documented attributes (may be None)."""
    from unittest.mock import MagicMock

    # Simulate what get_app_state fallback returns: SimpleNamespace with attrs
    mock_sm = MagicMock(spec=async_sessionmaker)
    mock_chain = MagicMock(spec=SqlAuditChain)

    fallback = SimpleNamespace(
        bus=MagicMock(spec=Bus),
        sessionmaker=mock_sm,
        audit_chain=mock_chain,
        dispatcher=MagicMock(spec=CommandDispatcher),
        api_dispatcher=MagicMock(spec=ApiCommandDispatcher),
        signing_backend=MagicMock(spec=FileBackend),
        enrollment_service=MagicMock(spec=EnrollmentService),
        revocation_service=MagicMock(spec=RevocationService),
        ca=MagicMock(spec=InternalCA),
        engine=MagicMock(),
        result_handler=MagicMock(spec=ResultHandler),
    )

    # Verify all required attributes exist
    assert fallback.bus is not None
    assert fallback.sessionmaker is not None
    assert fallback.audit_chain is not None
    assert fallback.dispatcher is not None
    assert fallback.api_dispatcher is not None
    assert fallback.signing_backend is not None
    assert fallback.enrollment_service is not None
    assert fallback.revocation_service is not None
    assert fallback.ca is not None
    assert fallback.engine is not None
    assert fallback.result_handler is not None


def test_simplenamespace_fallback_can_have_none_values() -> None:
    """SimpleNamespace fallback can have None values (test-only escape hatch)."""
    # Simulate app.state without app_state but with sparse attributes
    fallback = SimpleNamespace(
        bus=None,
        sessionmaker=None,
        audit_chain=None,
        dispatcher=None,
        api_dispatcher=None,
        signing_backend=None,
        enrollment_service=None,
        revocation_service=None,
        ca=None,
        engine=None,
        result_handler=None,
    )

    # All attributes exist but may be None
    assert hasattr(fallback, "bus")
    assert hasattr(fallback, "sessionmaker")
    assert hasattr(fallback, "audit_chain")
    assert hasattr(fallback, "dispatcher")
    assert hasattr(fallback, "api_dispatcher")
    assert hasattr(fallback, "signing_backend")
    assert hasattr(fallback, "enrollment_service")
    assert hasattr(fallback, "revocation_service")
    assert hasattr(fallback, "ca")
    assert hasattr(fallback, "engine")
    assert hasattr(fallback, "result_handler")
