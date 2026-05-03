"""FastAPI application lifespan and dependency injection wiring."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.auth.capability import CapabilityIssuer
from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.db.session import make_engine, make_sessionmaker
from server.app.dispatcher.dispatcher import CommandDispatcher as ApiCommandDispatcher
from server.app.dispatcher.queue import CommandQueue
from server.app.enrollment.service import EnrollmentService
from server.app.events.bus import Bus
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.grpc.result_handler import ResultHandler
from server.app.models import Base, Approval
from server.app.rbac.approvals import SubjectType, Policy
from server.app.rbac.engine import BuiltinEngine
from server.app.rbac.provider import Principal, AuthContext, Decision
from server.app.rbac.scope import Resource
from server.app.revocation.service import RevocationService
from server.app.settings.config import FleetSettings


class _PermissiveRbacProvider:
    """Stub RBAC provider that allows all actions (fail-open).

    Used when FLEET_ALLOW_PERMISSIVE_RBAC=1. Admin auth gate upstream
    provides the actual security boundary.
    """

    async def is_authorized(
        self, principal: Principal, action: str, resource: Resource, ctx: AuthContext
    ) -> Decision:
        """Always allow (fail-open)."""
        return Decision(allow=True)


class _RealRbacProvider:
    """Wrapper around BuiltinEngine to inject sessions per-call.

    BuiltinEngine requires a session for each authorization check.
    This wrapper creates a fresh session from the sessionmaker for each call,
    ensuring clean transaction isolation.
    """

    def __init__(self, sm: async_sessionmaker[AsyncSession]) -> None:
        """Initialize with sessionmaker."""
        self._sm = sm

    async def is_authorized(
        self, principal: Principal, action: str, resource: Resource, ctx: AuthContext
    ) -> Decision:
        """Check authorization using a fresh session."""
        async with self._sm() as session:
            engine = BuiltinEngine(session)
            return await engine.is_authorized(principal, action, resource, ctx)


class _LifespanApprovalProxy:
    """Wrapper around ApprovalEngine to inject sessions per-call.

    ApprovalEngine requires a session for each request. This wrapper creates
    a fresh session from the sessionmaker for each call, ensuring clean
    transaction isolation and commit semantics.
    """

    def __init__(self, sm: async_sessionmaker[AsyncSession]) -> None:
        """Initialize with sessionmaker."""
        self._sm = sm

    async def request(
        self,
        *,
        subject_type: SubjectType,
        subject_id: str,
        policy: Policy,
        requester_id: str,
        ttl: Any = None,
    ) -> Approval:
        """Request an approval, creating a real Approval row.

        Args:
            subject_type: Type of subject being approved (must be one of: command, task, policy_change)
            subject_id: ID of the subject (e.g., payload kind)
            policy: Approval policy (must be one of: single, two_person, single_second_factor)
            requester_id: ID of the principal requesting approval
            ttl: Optional time-to-live for the approval (unused, kept for interface)

        Returns:
            Approval row (from the real ApprovalEngine)

        Raises:
            ValueError: If subject_type or policy is not in the allowed Literal values.
        """
        from server.app.rbac.approvals import ApprovalEngine

        # Runtime validation: validate Literal values explicitly
        valid_subject_types: tuple[SubjectType, ...] = ("command", "task", "policy_change")
        valid_policies: tuple[Policy, ...] = ("single", "two_person", "single_second_factor")

        if subject_type not in valid_subject_types:
            raise ValueError(
                f"subject_type must be one of {valid_subject_types!r}, got {subject_type!r}"
            )
        if policy not in valid_policies:
            raise ValueError(
                f"policy must be one of {valid_policies!r}, got {policy!r}"
            )

        async with self._sm() as session:
            engine = ApprovalEngine(session)
            approval = await engine.request(
                subject_type=subject_type,
                subject_id=subject_id,
                policy=policy,
                requester_id=requester_id,
                approval_id=str(uuid4()),
            )
            await session.commit()
            return approval


@dataclass
class AppState:
    """Application state container."""

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


async def build_app_state(settings: FleetSettings) -> AppState:
    """Build application state from settings.

    Initializes:
    - CA: bootstrap or load from data_dir/ca/
    - SigningBackend: bootstrap or load from data_dir/signing/
    - AsyncEngine and sessionmaker
    - Bus: in-process event bus (singleton shared across components)
    - CommandDispatcher, SqlAuditChain, ResultHandler with bus wired
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

    # Setup event bus (singleton shared across all components)
    bus = Bus()

    # Setup command dispatcher and audit chain
    dispatcher = CommandDispatcher()
    audit_chain = SqlAuditChain(signing_backend, event_bus=bus)

    # Setup API command dispatcher with collaborators.
    queue = CommandQueue()
    capability_issuer = CapabilityIssuer.load_or_generate(
        settings.data_dir / "keys" / "capability.key"
    )
    approval_engine = _LifespanApprovalProxy(sm)

    # Wire RBAC provider.
    # In production (FLEET_ENV=prod): wire real BuiltinEngine provider unless
    # explicitly opted into permissive mode via FLEET_ALLOW_PERMISSIVE_RBAC=1.
    # In dev: default to real provider, unless flag overrides to permissive stub.
    allow_permissive = os.environ.get("FLEET_ALLOW_PERMISSIVE_RBAC") == "1"
    is_prod = os.environ.get("FLEET_ENV", "dev").lower() == "prod"

    rbac_provider: _RealRbacProvider | _PermissiveRbacProvider
    if is_prod and not allow_permissive:
        rbac_provider = _RealRbacProvider(sm)
    elif allow_permissive:
        rbac_provider = _PermissiveRbacProvider()
    else:
        rbac_provider = _RealRbacProvider(sm)
    api_dispatcher = ApiCommandDispatcher(
        queue=queue,
        audit=audit_chain,
        capability_issuer=capability_issuer,
        signing_backend=signing_backend,
        approval_engine=approval_engine,
        rbac_provider=rbac_provider,
        scope_evaluator=None,
        event_bus=bus,
    )

    # Setup result handler
    result_handler = ResultHandler(sm, audit_chain, event_bus=bus)

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
