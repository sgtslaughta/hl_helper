"""End-to-end tests for host revocation with real mTLS."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import grpc
import grpc.aio
import pytest
from cryptography import x509
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.signing import FileBackend
from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2_grpc, envelope_pb2
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.models import Host
from server.app.revocation.service import RevocationService


@pytest.fixture
def dispatcher() -> CommandDispatcher:
    """Create a fresh dispatcher for testing."""
    return CommandDispatcher()


def make_env(host_id: str, command_id: str) -> envelope_pb2.CommandEnvelope:
    """Build a CommandEnvelope for testing."""
    env = envelope_pb2.CommandEnvelope()
    env.command_id = command_id
    env.host_id = host_id
    env.sequence = 1
    env.nonce = b"test"
    now = datetime.now(timezone.utc)
    env.issued_at.FromDatetime(now)
    env.expires_at.FromDatetime(now)
    env.issued_by = "test-server"
    env.pkg_update.classes.append("base")
    return env


@pytest.mark.asyncio
async def test_dispatcher_terminate_method(
    dispatcher: CommandDispatcher,
) -> None:
    """Test that dispatcher.terminate() sets the termination event."""
    state = await dispatcher.register("test-host-1")
    assert state.connected

    # Verify terminate returns True when host is connected
    result = await dispatcher.terminate("test-host-1")
    assert result is True
    assert state.terminate_event.is_set()

    # Terminate on non-connected host returns False
    await dispatcher.unregister("test-host-1")
    result = await dispatcher.terminate("test-host-1")
    assert result is False


@pytest.mark.asyncio
async def test_stream_rejected_at_handshake_when_host_revoked(
    tls_creds: dict[str, bytes],
    sm: async_sessionmaker,
    signing_backend: FileBackend,
) -> None:
    """Pre-revoke host before connect; connect; PERMISSION_DENIED at handshake."""
    from server.app.grpc.server import make_grpc_server

    # Extract serial from client cert
    client_cert = x509.load_pem_x509_certificate(tls_creds["client_cert_pem"])
    cert_serial = format(client_cert.serial_number, "x")

    # Create dispatcher and revocation service
    dispatcher = CommandDispatcher()
    audit_chain = SqlAuditChain(signing_backend, checkpoint_interval=100)
    revocation_service = RevocationService(dispatcher=dispatcher, audit=audit_chain)

    # Start gRPC server with revocation service
    server, bound_addr, _ = make_grpc_server(
        server_cert_chain_pem=tls_creds["server_cert_pem"],
        server_key_pem=tls_creds["server_key_pem"],
        client_ca_pem=tls_creds["ca_chain_pem"],
        bind_address="127.0.0.1:0",
        dispatcher=dispatcher,
        revocation=revocation_service,
    )

    await server.start()
    try:
        # Pre-create and pre-revoke host with actual client cert serial
        async with sm() as session:
            host = Host(
                id="test-host-1",
                hostname="test.example.com",
                agent_pubkey=b"x" * 32,
                cert_serial=cert_serial,
            )
            session.add(host)
            await session.commit()

            await revocation_service.revoke(
                session,
                host_id="test-host-1",
                actor="admin",
                reason="test revocation",
            )
            await session.commit()

        _host, port_str = bound_addr.rsplit(":", 1)
        port = int(port_str)

        creds = grpc.ssl_channel_credentials(
            root_certificates=tls_creds["ca_chain_pem"],
            private_key=tls_creds["client_key_pem"],
            certificate_chain=tls_creds["client_cert_pem"],
        )

        async with grpc.aio.secure_channel(
            f"127.0.0.1:{port}",
            creds,
            options=[("grpc.ssl_target_name_override", "localhost")],
        ) as channel:
            stub = agent_bridge_pb2_grpc.AgentBridgeStub(channel)

            # Try to connect
            call = stub.Stream(iter([]))

            try:
                await asyncio.wait_for(call.read(), timeout=2.0)
                pytest.fail("Expected PERMISSION_DENIED but got message")
            except grpc.RpcError as e:
                assert e.code() == grpc.StatusCode.PERMISSION_DENIED
                assert "revoked" in str(e.details()).lower()
    finally:
        await server.stop(grace=5)
