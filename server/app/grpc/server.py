"""gRPC async server scaffold with mTLS + SPIFFE peer context."""

from __future__ import annotations

from typing import Any

import grpc
from grpc.aio import server as aio_server
from grpc.aio import Server

# Inject _pb into sys.path so proto imports work
from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2_grpc

from .tls import make_server_credentials


class _StubAgentBridge(agent_bridge_pb2_grpc.AgentBridgeServicer):
    """Placeholder AgentBridge service. Real implementation lands in C1 Task 5.2."""

    async def Stream(self, request_iterator: Any, context: Any) -> None:
        """Stub Stream RPC that returns UNIMPLEMENTED."""
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED, "AgentBridge.Stream not yet implemented"
        )


def make_grpc_server(
    *,
    server_cert_chain_pem: bytes,
    server_key_pem: bytes,
    client_ca_pem: bytes,
    bind_address: str = "0.0.0.0:8444",
) -> tuple[Server, str]:
    """Build configured async gRPC server with mTLS + servicer wired.

    Args:
        server_cert_chain_pem: leaf + intermediate(s) concatenated in PEM.
        server_key_pem: PEM-encoded private key for the leaf.
        client_ca_pem: trust roots used to verify client certs (CA chain PEM).
        bind_address: Address to bind to (e.g., "0.0.0.0:8444" or "127.0.0.1:0").

    Returns:
        (server, bound_address) tuple. Caller must `await server.start()`.
        If bind_address ends with ":0", bound_address contains the actual port.
    """
    server = aio_server()
    agent_bridge_pb2_grpc.add_AgentBridgeServicer_to_server(_StubAgentBridge(), server)  # type: ignore[no-untyped-call]
    creds = make_server_credentials(server_cert_chain_pem, server_key_pem, client_ca_pem)
    bound_port = server.add_secure_port(bind_address, creds)

    # Compute actual bound address (for :0 case)
    if bind_address.endswith(":0"):
        host = bind_address.rsplit(":", 1)[0]
        actual_address = f"{host}:{bound_port}"
    else:
        actual_address = bind_address

    return server, actual_address
