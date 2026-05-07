"""FastAPI application lifespan and dependency injection wiring."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from grpc.aio import Server
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
from server.app.grpc.server import make_grpc_server
from server.app.models import Base, Approval
from server.app.rbac.approvals import SubjectType, Policy
from server.app.rbac.engine import BuiltinEngine
from server.app.rbac.provider import Principal, AuthContext, Decision
from server.app.rbac.scope import Resource
from server.app.revocation.service import RevocationService
from server.app.settings.config import FleetSettings

logger = logging.getLogger(__name__)


class _PermissiveRbacProvider:
    """Stub RBAC provider that allows all actions (fail-open).

    Used when allow_permissive_rbac is set to True in config file.
    Admin auth gate upstream provides the actual security boundary.
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
    lockout_tracker: Any | None = None
    session_service: Any | None = None
    secrets_broker: Any | None = None
    webauthn_service: Any | None = None
    webauthn_challenges: Any | None = None
    webauthn_rp_id: str | None = None
    webauthn_origin: str | None = None
    public_url: str | None = None
    public_origin: str | None = None
    advertised_origins: list[str] | None = None
    grpc_server: Server | None = None


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

    # Setup session service
    from server.app.auth.sessions import SessionService
    session_service = SessionService(
        sessionmaker=sm,
        bus=bus,
        idle_ttl_seconds=settings.session_idle_ttl_s,
        absolute_ttl_seconds=settings.session_abs_ttl_s,
    )
    await session_service.start()

    # Setup secrets backend if configured
    secrets_broker = None
    if settings.secrets_root_dir and settings.secrets_root_key_b64:
        from server.app.secrets.backends.local import LocalEncryptedFileBackend
        root_key = base64.urlsafe_b64decode(settings.secrets_root_key_b64)
        secrets_broker = LocalEncryptedFileBackend(Path(settings.secrets_root_dir), root_key)

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
    # Config-file-only setting: allow_permissive_rbac (default False).
    # If FLEET_ALLOW_PERMISSIVE_RBAC env var is set, log warning and ignore.
    if os.environ.get("FLEET_ALLOW_PERMISSIVE_RBAC"):
        logger.warning(
            "FLEET_ALLOW_PERMISSIVE_RBAC env var detected but is no longer supported. "
            "Set allow_permissive_rbac in config file instead."
        )

    allow_permissive = settings.allow_permissive_rbac
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

    # Setup enrollment service.
    # public_url may include scheme and/or HTTP port (e.g. "http://localhost:8000").
    # gRPC runs on a separate port (50051), so we must extract just the host.
    from urllib.parse import urlparse

    _parsed = urlparse(
        settings.public_url
        if "://" in settings.public_url
        else f"http://{settings.public_url}"
    )
    grpc_host = _parsed.hostname or "localhost"
    grpc_endpoint = f"{grpc_host}:50051"
    enrollment_service = EnrollmentService(
        ca=ca,
        signing_backend=signing_backend,
        grpc_endpoint=grpc_endpoint,
    )

    # Setup lockout tracker with DB persistence
    from server.app.auth.lockout import LockoutTrackerPersistent
    lockout_tracker = LockoutTrackerPersistent(sessionmaker=sm)

    advertised_origins = _enumerate_advertised_origins(settings.public_url)

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
        lockout_tracker=lockout_tracker,
        session_service=session_service,
        secrets_broker=secrets_broker,
        public_url=settings.public_url,
        public_origin=settings.public_url,
        advertised_origins=advertised_origins,
    )


def _enumerate_advertised_origins(public_url: str) -> list[str]:
    """Return ``public_url`` followed by ``https://{ip}:{port}`` for each
    routable IPv4 address found on the host.

    Filters out loopback (127.x), link-local (169.254.x), and interfaces that
    are not up. The list is deduplicated, preserving order; ``public_url`` is
    always first when present. Used by the enrollment-mint endpoint so an
    operator on a multi-homed server can pick which IP install commands target.
    """
    from urllib.parse import urlparse

    origins: list[str] = []
    if public_url:
        origins.append(public_url.rstrip("/"))

    try:
        import psutil  # type: ignore
    except Exception:
        return origins

    parsed = urlparse(public_url) if public_url else None
    scheme = (parsed.scheme if parsed else "https") or "https"
    port = parsed.port if parsed else None
    if port is None:
        port = 8443

    try:
        if_addrs = psutil.net_if_addrs()
        if_stats = psutil.net_if_stats()
    except Exception:
        return origins

    for iface, addrs in if_addrs.items():
        stats = if_stats.get(iface)
        if stats is not None and not stats.isup:
            continue
        for a in addrs:
            if int(getattr(a.family, "value", a.family)) != 2:  # AF_INET
                continue
            ip = a.address
            if not ip or ip.startswith("127.") or ip.startswith("169.254."):
                continue
            candidate = f"{scheme}://{ip}:{port}"
            if candidate not in origins:
                origins.append(candidate)
    return origins


def _make_csr_and_key() -> tuple[bytes, bytes]:
    """Generate a fresh ECDSA P-256 keypair + CSR. Returns (csr_pem, key_pem)."""
    sk = ec.generate_private_key(ec.SECP256R1())
    key_pem = sk.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "grpc-server")]))
        .sign(sk, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM), key_pem


async def _start_grpc_server(state: AppState, grpc_host: str) -> None:
    """Start the gRPC server on port 50051.

    Mints a server cert using the CA, builds the gRPC server with mTLS,
    and starts it. If gRPC startup fails, logs a warning and continues
    without it (fail-open for dev mode).

    Args:
        state: AppState with CA, dispatcher, result_handler, revocation_service.
        grpc_host: Hostname to use in the server cert CN.
    """
    # Check if gRPC is disabled via env var
    if os.environ.get("HL_GRPC_DISABLE") == "1":
        logger.info("gRPC startup skipped (HL_GRPC_DISABLE=1)")
        return

    try:
        # Generate server CSR + key
        csr_pem, key_pem = _make_csr_and_key()

        # Split SAN by type — IP literals must go in IPAddress SAN, not DNSName,
        # or TLS verification fails with SSLV3_ALERT_BAD_CERTIFICATE when the
        # agent dials the server by IP. Always include localhost + 127.0.0.1
        # for same-box clients, plus every advertised origin's host.
        import ipaddress

        ip_sans: list[str] = ["127.0.0.1"]
        dns_sans: list[str] = ["localhost"]
        san_hosts = {grpc_host}
        for origin in state.advertised_origins or []:
            from urllib.parse import urlparse as _u

            h = _u(origin).hostname
            if h:
                san_hosts.add(h)
        for h in san_hosts:
            try:
                ipaddress.ip_address(h)
                if h not in ip_sans:
                    ip_sans.append(h)
            except ValueError:
                if h not in dns_sans:
                    dns_sans.append(h)

        # Mint server cert using CA (1-hour TTL for dev)
        server_cert_pem = state.ca.issue_server_cert(
            csr_pem,
            server_id=grpc_host,
            ttl=timedelta(hours=1),
            dns_names=dns_sans,
            ip_addresses=ip_sans,
        )

        # Build CA chain (root + intermediate)
        root_crt_pem = state.ca.root_cert.public_bytes(serialization.Encoding.PEM)
        int_crt_pem = state.ca.int_cert.public_bytes(serialization.Encoding.PEM)
        ca_chain_pem = root_crt_pem + int_crt_pem

        # Build cert chain (leaf + intermediate)
        cert_chain_pem = server_cert_pem + int_crt_pem

        # Create and start gRPC server
        server, bound_addr, _ = make_grpc_server(
            server_cert_chain_pem=cert_chain_pem,
            server_key_pem=key_pem,
            client_ca_pem=ca_chain_pem,
            bind_address="0.0.0.0:50051",
            dispatcher=state.dispatcher,
            result_handler=state.result_handler,
            revocation=state.revocation_service,
            sessionmaker=state.sessionmaker,
        )

        await server.start()
        state.grpc_server = server
        logger.info(f"gRPC server started at {bound_addr}")

    except Exception as e:
        logger.warning(f"Failed to start gRPC server: {e}. Continuing with HTTP-only mode.")


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

    # Start gRPC server alongside HTTP
    from urllib.parse import urlparse
    _parsed = urlparse(
        settings.public_url
        if "://" in settings.public_url
        else f"http://{settings.public_url}"
    )
    grpc_host = _parsed.hostname or "localhost"
    await _start_grpc_server(state, grpc_host)

    # Bridge bus 'command.issued' events into grpc dispatcher's live per-host queue.
    from server.app.grpc.command_bridge import run_command_bridge
    from server.app.dispatcher.sweeper import run_command_sweeper
    bridge_task = asyncio.create_task(
        run_command_bridge(state.bus, state.dispatcher, state.sessionmaker)
    )
    sweeper_task = asyncio.create_task(run_command_sweeper(state.sessionmaker))

    yield

    for t in (bridge_task, sweeper_task):
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    # Shutdown: stop gRPC server, session service, and close engine
    if state.grpc_server:
        try:
            await state.grpc_server.stop(grace=5)
            logger.info("gRPC server stopped")
        except Exception as e:
            logger.warning(f"Error stopping gRPC server: {e}")

    if state.session_service:
        await state.session_service.stop()
    await state.engine.dispose()
