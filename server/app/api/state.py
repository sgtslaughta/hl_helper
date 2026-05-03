"""Helper to resolve AppState from a FastAPI request.

Lives in its own module to avoid circular imports between app.py (which
includes v1 routers) and v1 routers (which need AppState).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession

from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.dispatcher.dispatcher import CommandDispatcher as ApiCommandDispatcher
from server.app.events.bus import Bus
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.grpc.result_handler import ResultHandler
from server.app.enrollment.service import EnrollmentService
from server.app.revocation.service import RevocationService


@runtime_checkable
class AppStateProtocol(Protocol):
    """Protocol for application state container.

    Defines the interface that consumers of get_app_state() expect.
    Production path (AppState) is strictly typed; test fallback path
    (SimpleNamespace) may have None values for attributes.
    """

    bus: Bus
    ca: InternalCA
    signing_backend: FileBackend
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    dispatcher: CommandDispatcher
    api_dispatcher: ApiCommandDispatcher
    audit_chain: SqlAuditChain
    result_handler: ResultHandler
    revocation_service: RevocationService
    enrollment_service: EnrollmentService


def get_app_state(request: Any) -> AppStateProtocol:
    """Return AppState from app.state.app_state, or a SimpleNamespace shim.

    In production, lifespan stores AppState at app.state.app_state.
    In tests that inject state attributes directly (legacy path), fall back
    to synthesizing from individual attributes via a SimpleNamespace.

    The SimpleNamespace fallback may contain None values for unset attributes.
    This is a documented test-only escape hatch; production callers should handle
    None gracefully or rely on full AppState initialization via lifespan.
    """
    state = getattr(request.app.state, "app_state", None)
    if state is not None:
        return state  # type: ignore[no-any-return]
    ns = SimpleNamespace(
        bus=getattr(request.app.state, "bus", None),
        sessionmaker=getattr(request.app.state, "sessionmaker", None),
        audit_chain=getattr(request.app.state, "audit_chain", None),
        dispatcher=getattr(request.app.state, "dispatcher", None),
        api_dispatcher=getattr(request.app.state, "api_dispatcher", None),
        signing_backend=getattr(request.app.state, "signing_backend", None),
        enrollment_service=getattr(request.app.state, "enrollment_service", None),
        revocation_service=getattr(request.app.state, "revocation_service", None),
        ca=getattr(request.app.state, "ca", None),
        engine=getattr(request.app.state, "engine", None),
        result_handler=getattr(request.app.state, "result_handler", None),
    )
    return ns
