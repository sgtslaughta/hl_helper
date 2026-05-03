"""FastAPI application lifespan and dependency injection wiring."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.auth.capability import CapabilityIssuer
from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.db.session import make_engine, make_sessionmaker
from server.app.dispatcher.dispatcher import CommandDispatcher as ApiCommandDispatcher
from server.app.dispatcher.queue import CommandQueue
from server.app.enrollment.service import EnrollmentService
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.grpc.result_handler import ResultHandler
from server.app.models import Base
from server.app.revocation.service import RevocationService
from server.app.settings.config import FleetSettings


class _PermissiveRbacProvider:
    """Stub RBAC provider that allows all actions (fail-open).

    Used when real RBAC provider is not yet wired. Admin auth gate upstream
    provides the actual security boundary.
    """

    async def is_authorized(self, principal: Any, action: str, resource: Any, ctx: Any) -> Any:
        """Always allow (fail-open)."""
        from dataclasses import dataclass

        @dataclass
        class AllowDecision:
            allow: bool = True

        return AllowDecision()


@dataclass
class AppState:
    """Application state container."""

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


async def build_app_state(settings: FleetSettings) -> AppState:
    """Build application state from settings.

    Initializes:
    - CA: bootstrap or load from data_dir/ca/
    - SigningBackend: bootstrap or load from data_dir/signing/
    - AsyncEngine and sessionmaker
    - CommandDispatcher, SqlAuditChain, ResultHandler
    - RevocationService with CRL hydrated via load_from_db
    - EnrollmentService

    Args:
        settings: Fleet settings

    Returns:
        AppState dataclass with all services initialized
    """
    # Setup CA
    ca_dir = settings.data_dir / "ca"
    if ca_dir.exists():
        ca = InternalCA.load(ca_dir)
    else:
        ca = InternalCA.bootstrap(ca_dir)

    # Setup signing backend
    signing_dir = settings.data_dir / "signing"
    if signing_dir.exists():
        signing_backend = FileBackend(signing_dir)
    else:
        signing_backend = FileBackend.bootstrap(signing_dir)

    # Setup database
    engine = make_engine(settings.db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)

    # Setup command dispatcher and audit chain
    dispatcher = CommandDispatcher()
    audit_chain = SqlAuditChain(signing_backend)

    # Setup API command dispatcher with collaborators.
    #
    # NOTE: queue + capability_issuer are instantiated fresh on each restart.
    # The CommandQueue is in-memory only (idempotency LRU rotates on restart);
    # CapabilityIssuer.generate() rotates the biscuit signing key, invalidating
    # outstanding capabilities. Both are intentional for the current dev
    # iteration; durable persistence is a follow-up.
    queue = CommandQueue()
    capability_issuer = CapabilityIssuer.generate()
    approval_engine = None  # Will be created per-request; duck-typed

    # Fail-open stub RBAC. Refuse to start in production unless explicitly
    # acknowledged via FLEET_ALLOW_PERMISSIVE_RBAC=1 — prevents an accidental
    # prod deploy from defaulting to "anyone wins every authorization check".
    if os.environ.get("FLEET_ENV", "dev").lower() == "prod" and (
        os.environ.get("FLEET_ALLOW_PERMISSIVE_RBAC") != "1"
    ):
        raise RuntimeError(
            "Refusing to start: FLEET_ENV=prod with permissive RBAC stub. "
            "Wire a real RBACProvider or set FLEET_ALLOW_PERMISSIVE_RBAC=1 "
            "to acknowledge."
        )
    rbac_provider = _PermissiveRbacProvider()
    api_dispatcher = ApiCommandDispatcher(
        queue=queue,
        audit=audit_chain,
        capability_issuer=capability_issuer,
        signing_backend=signing_backend,
        approval_engine=approval_engine,
        rbac_provider=rbac_provider,
        scope_evaluator=None,
    )

    # Setup result handler
    result_handler = ResultHandler(sm, audit_chain)

    # Setup revocation service and hydrate CRL
    revocation_service = RevocationService(dispatcher, audit_chain)
    async with sm() as session:
        await revocation_service.load_from_db(session)

    # Setup enrollment service
    grpc_endpoint = settings.public_url.replace("https://", "").replace("http://", "")
    if not grpc_endpoint.endswith(":50051"):
        grpc_endpoint = f"{grpc_endpoint}:50051"
    enrollment_service = EnrollmentService(
        ca=ca,
        signing_backend=signing_backend,
        grpc_endpoint=grpc_endpoint,
    )

    return AppState(
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


@asynccontextmanager
async def app_lifespan(app: Any) -> AsyncIterator[None]:
    """FastAPI lifespan context manager.

    Startup: builds app state and stores in app.state
    Shutdown: disposes engine and closes things gracefully
    """
    from server.app.settings.config import load_settings

    settings = load_settings()
    state = await build_app_state(settings)
    app.state.app_state = state

    yield

    # Shutdown: close engine
    await state.engine.dispose()
