"""Helper to build AppState for tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.dispatcher.dispatcher import CommandDispatcher as ApiCommandDispatcher
from server.app.enrollment.service import EnrollmentService
from server.app.events.bus import Bus
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.lifespan import AppState
from server.app.revocation.service import RevocationService


class _NopCommandDispatcher:
    """Stub CommandDispatcher that does nothing."""

    async def dispatch(self, *args: Any, **kwargs: Any) -> Any:
        """No-op dispatch."""
        return None


class _NopApiCommandDispatcher:
    """Stub ApiCommandDispatcher that does nothing."""

    async def dispatch(self, *args: Any, **kwargs: Any) -> Any:
        """No-op dispatch."""
        return None


class _NopResultHandler:
    """Stub ResultHandler that does nothing."""

    async def handle(self, *args: Any, **kwargs: Any) -> None:
        """No-op handle."""
        pass


class _NopEnrollmentService:
    """Stub EnrollmentService that does nothing."""

    async def enroll(self, *args: Any, **kwargs: Any) -> Any:
        """No-op enroll."""
        return None


class _NopRevocationService:
    """Stub RevocationService that does nothing."""

    async def revoke(self, *args: Any, **kwargs: Any) -> None:
        """No-op revoke."""
        pass

    async def load_from_db(self, *args: Any, **kwargs: Any) -> None:
        """No-op load."""
        pass


def make_test_app_state(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    signing_backend: FileBackend | None = None,
    audit_chain: SqlAuditChain | None = None,
    dispatcher: CommandDispatcher | None = None,
    api_dispatcher: ApiCommandDispatcher | None = None,
    enrollment_service: EnrollmentService | None = None,
    revocation_service: RevocationService | None = None,
    ca: InternalCA | None = None,
    engine: AsyncEngine | None = None,
    bus: Bus | None = None,
    tmp_path: Path | None = None,
) -> AppState:
    """Build a minimal AppState for tests with sensible defaults.

    Most callers just need sessionmaker; everything else falls back to a
    no-op double or stub if the route under test doesn't use it. Returns
    an actual AppState dataclass instance, not a SimpleNamespace shim.

    Args:
        sessionmaker: Required sessionmaker for database access
        signing_backend: FileBackend for signing (defaults to bootstrapped in tmp_path)
        audit_chain: SqlAuditChain for audit (defaults to None for simple routes)
        dispatcher: gRPC CommandDispatcher (defaults to noop)
        api_dispatcher: API CommandDispatcher (defaults to noop)
        enrollment_service: EnrollmentService (defaults to noop)
        revocation_service: RevocationService (defaults to noop)
        ca: InternalCA (defaults to bootstrapped in tmp_path)
        engine: AsyncEngine (defaults to None)
        bus: Event bus (defaults to noop Bus)
        tmp_path: Temp path for bootstrapping signing/CA (optional, used if signing_backend not provided)

    Returns:
        AppState dataclass with all required fields populated
    """
    # Determine tmp_path for bootstrap
    bootstrap_path = tmp_path or Path("/tmp/hl_test")

    # Build signing_backend if not provided
    if signing_backend is None:
        signing_backend = FileBackend.bootstrap(bootstrap_path / "signing")

    # Build ca if not provided
    if ca is None:
        ca = InternalCA.bootstrap(bootstrap_path / "ca")

    # Build audit_chain if not provided
    if audit_chain is None:
        audit_chain = SqlAuditChain(signing_backend, checkpoint_interval=100)

    # Build dispatcher if not provided
    if dispatcher is None:
        dispatcher = _NopCommandDispatcher()  # type: ignore[assignment]

    # Build api_dispatcher if not provided
    if api_dispatcher is None:
        api_dispatcher = _NopApiCommandDispatcher()  # type: ignore[assignment]

    # Build enrollment_service if not provided
    if enrollment_service is None:
        enrollment_service = _NopEnrollmentService()  # type: ignore[assignment]

    # Build revocation_service if not provided
    if revocation_service is None:
        revocation_service = _NopRevocationService()  # type: ignore[assignment]

    # Build bus if not provided
    if bus is None:
        bus = Bus()

    # Build result_handler (always noop for tests)
    result_handler = _NopResultHandler()  # type: ignore[assignment]

    return AppState(
        bus=bus,
        ca=ca,
        signing_backend=signing_backend,
        engine=engine,  # type: ignore[arg-type]
        sessionmaker=sessionmaker,
        dispatcher=dispatcher,
        api_dispatcher=api_dispatcher,
        audit_chain=audit_chain,
        result_handler=result_handler,
        revocation_service=revocation_service,
        enrollment_service=enrollment_service,
    )
