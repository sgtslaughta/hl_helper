"""Helper to resolve AppState from a FastAPI request.

Lives in its own module to avoid circular imports between app.py (which
includes v1 routers) and v1 routers (which need AppState).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fastapi import Request

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
from server.app.secrets.backends.base import SecretsBackend

# Type hints for optional session/secrets services
# SessionService is not imported directly to avoid circular dependencies


@runtime_checkable
class AppStateProtocol(Protocol):
    """Protocol for application state container.

    Defines the interface that consumers of get_app_state() expect.
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
    lockout_tracker: Any | None  # LockoutTrackerPersistent | None
    session_service: Any | None  # SessionService | None, but lazily imported to avoid circular deps
    secrets_broker: SecretsBackend | None


def get_app_state(request: Request) -> AppStateProtocol:
    """Return AppState from app.state.app_state.

    In production, lifespan stores AppState at app.state.app_state.
    In tests, set app.state.app_state = make_test_app_state(...).

    Raises RuntimeError if AppState is not initialized.
    """
    state = getattr(request.app.state, "app_state", None)
    if state is None:
        raise RuntimeError(
            "AppState not initialized. Production: ensure lifespan_context ran. "
            "Tests: set app.state.app_state = make_test_app_state(...)"
        )
    return state  # type: ignore[no-any-return]
