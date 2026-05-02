"""Shared pytest fixtures for gRPC tests."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import AsyncGenerator

import grpc
import grpc.aio
import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.db.session import make_engine, make_sessionmaker
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.grpc.server import make_grpc_server
from server.app.models import Base


def make_csr() -> tuple[bytes, bytes]:
    """Build a fresh ECDSA P-256 keypair + CSR. Returns (csr_pem, key_pem)."""
    sk = ec.generate_private_key(ec.SECP256R1())
    key_pem = sk.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "agent")]))
        .sign(sk, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM), key_pem


@pytest.fixture
def tls_creds(tmp_path: Path) -> dict[str, bytes]:
    """Bootstrap CA and generate server + client certs.

    Returns a dict with keys:
      - "ca_chain_pem": Root + Intermediate
      - "server_cert_pem": Server leaf + intermediate
      - "server_key_pem": Server private key
      - "client_cert_pem": Client leaf + intermediate
      - "client_key_pem": Client private key
    """
    ca_dir = tmp_path / "ca"
    ca = InternalCA.bootstrap(ca_dir)

    # Server cert
    server_csr_pem, server_key_pem = make_csr()
    server_cert_pem = ca.issue_server_cert(
        server_csr_pem,
        server_id="fleet-server",
        ttl=timedelta(hours=1),
        dns_names=["localhost", "127.0.0.1"],
    )

    # Client cert
    client_csr_pem, client_key_pem = make_csr()
    client_cert_pem = ca.issue_host_cert(
        client_csr_pem, host_id="test-host-1", ttl=timedelta(hours=1)
    )

    # Build CA chain
    root_crt_pem = ca.root_cert.public_bytes(serialization.Encoding.PEM)
    int_crt_pem = ca.int_cert.public_bytes(serialization.Encoding.PEM)
    ca_chain_pem = root_crt_pem + int_crt_pem

    return {
        "ca_chain_pem": ca_chain_pem,
        "server_cert_pem": server_cert_pem + int_crt_pem,
        "server_key_pem": server_key_pem,
        "client_cert_pem": client_cert_pem + int_crt_pem,
        "client_key_pem": client_key_pem,
    }


@pytest.fixture
async def grpc_server_and_dispatcher(
    tls_creds: dict[str, bytes],
) -> AsyncGenerator[tuple[str, CommandDispatcher], None]:
    """Start a gRPC server with mTLS and yield (bound_address, dispatcher).

    The caller should use bound_address to connect a client.
    """
    dispatcher = CommandDispatcher()
    server, bound_addr, _ = make_grpc_server(
        server_cert_chain_pem=tls_creds["server_cert_pem"],
        server_key_pem=tls_creds["server_key_pem"],
        client_ca_pem=tls_creds["ca_chain_pem"],
        bind_address="127.0.0.1:0",
        dispatcher=dispatcher,
    )

    await server.start()
    try:
        yield bound_addr, dispatcher
    finally:
        await server.stop(grace=5)


@pytest.fixture
def agent_channel(
    tls_creds: dict[str, bytes], grpc_server_and_dispatcher: tuple[str, CommandDispatcher]
) -> AsyncGenerator[grpc.aio.Channel, None]:
    """Create a gRPC client channel with mTLS to the test server.

    Depends on grpc_server_and_dispatcher which is started/stopped via the fixture.
    """

    async def _channel_gen() -> AsyncGenerator[grpc.aio.Channel, None]:
        bound_addr, _dispatcher = grpc_server_and_dispatcher
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
            yield channel

    # Return an async generator
    return _channel_gen()


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an in-memory SQLite engine and initialize all tables."""
    e = make_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def sm(engine: AsyncEngine) -> async_sessionmaker:
    """Create a sessionmaker for the test engine."""
    return make_sessionmaker(engine)


@pytest.fixture
def signing_backend(tmp_path: Path) -> FileBackend:
    """Create a signing backend for audit chain."""
    return FileBackend.bootstrap(tmp_path / "signing")
