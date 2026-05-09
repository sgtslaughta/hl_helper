"""gRPC async server scaffold with mTLS + SPIFFE peer context."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from grpc.aio import server as aio_server
from grpc.aio import Server

# Inject _pb into sys.path so proto imports work
from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2_grpc

from .agent_bridge import AgentBridgeService
from .dispatcher import CommandDispatcher
from .tls import make_server_credentials

if TYPE_CHECKING:
    from server.app.revocation.service import RevocationService
    from .result_handler import ResultHandler


def make_grpc_server(
    *,
    server_cert_chain_pem: bytes,
    server_key_pem: bytes,
    client_ca_pem: bytes,
    bind_address: str = "0.0.0.0:8444",
    dispatcher: CommandDispatcher | None = None,
    result_handler: ResultHandler | None = None,
    revocation: RevocationService | None = None,
    sessionmaker: Any | None = None,
    audit_chain: Any | None = None,
    advisory_worker: Any | None = None,
    event_bus: Any | None = None,
    rotation_orchestrator: Any | None = None,
) -> tuple[Server, str, CommandDispatcher, AgentBridgeService]:
    """Build configured async gRPC server with mTLS + servicer wired.

    Args:
        server_cert_chain_pem: leaf + intermediate(s) concatenated in PEM.
        server_key_pem: PEM-encoded private key for the leaf.
        client_ca_pem: trust roots used to verify client certs (CA chain PEM).
        bind_address: Address to bind to (e.g., "0.0.0.0:8444" or "127.0.0.1:0").
        dispatcher: CommandDispatcher instance; created if None.
        result_handler: ResultHandler instance; optional for tests.
        revocation: RevocationService instance; optional for tests.
        audit_chain: Optional audit chain for persisting audit events.

    Returns:
        (server, bound_address, dispatcher, agent_bridge) tuple. Caller must `await server.start()`.
        If bind_address ends with ":0", bound_address contains the actual port.
    """
    dispatcher = dispatcher or CommandDispatcher()
    server = aio_server()
    agent_bridge = AgentBridgeService(  # type: ignore[no-untyped-call]
        dispatcher,
        result_handler=result_handler,
        revocation=revocation,
        sessionmaker=sessionmaker,
        audit_chain=audit_chain,
        advisory_worker=advisory_worker,
        event_bus=event_bus,
        rotation_orchestrator=rotation_orchestrator,
    )
    agent_bridge_pb2_grpc.add_AgentBridgeServicer_to_server(
        agent_bridge,
        server,
    )
    creds = make_server_credentials(server_cert_chain_pem, server_key_pem, client_ca_pem)
    bound_port = server.add_secure_port(bind_address, creds)

    # Compute actual bound address (for :0 case)
    if bind_address.endswith(":0"):
        host = bind_address.rsplit(":", 1)[0]
        actual_address = f"{host}:{bound_port}"
    else:
        actual_address = bind_address

    return server, actual_address, dispatcher, agent_bridge
