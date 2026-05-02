"""Tests for gRPC mTLS server + SPIFFE peer identity extraction."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import grpc
import grpc.aio
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from server.app.crypto.ca import InternalCA
from server.app.grpc.tls import (
    extract_spiffe_id,
    host_id_from_spiffe,
)
from server.app.grpc.server import make_grpc_server
from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2_grpc


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


def test_extract_spiffe_id_from_host_cert(tmp_path: Path) -> None:
    """Test extracting SPIFFE URI from a host cert."""
    ca = InternalCA.bootstrap(tmp_path / "ca")
    csr_pem, _key_pem = make_csr()

    # Issue a host cert
    cert_pem = ca.issue_host_cert(csr_pem, host_id="abc123", ttl=timedelta(hours=1))

    # Extract SPIFFE ID
    spiffe_id = extract_spiffe_id(cert_pem)
    assert spiffe_id == "spiffe://fleet/host/abc123"


def test_host_id_from_spiffe_extracts_uuid() -> None:
    """Test extracting host_id from a host SPIFFE URI."""
    uri = "spiffe://fleet/host/abc123"
    host_id = host_id_from_spiffe(uri)
    assert host_id == "abc123"


def test_host_id_from_spiffe_returns_none_for_server_uri() -> None:
    """Test that server URI doesn't match host prefix."""
    uri = "spiffe://fleet/server"
    host_id = host_id_from_spiffe(uri)
    assert host_id is None


def test_extract_spiffe_returns_none_for_cert_without_san(tmp_path: Path) -> None:
    """Test that a cert without SAN returns None."""
    # Create a cert without a URI SAN
    sk = ed25519.Ed25519PrivateKey.generate()
    now_utc = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "test")]))
        .issuer_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "test")]))
        .public_key(sk.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now_utc)
        .not_valid_after(now_utc + timedelta(days=1))
        .sign(sk, None)
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)

    spiffe_id = extract_spiffe_id(cert_pem)
    assert spiffe_id is None


@pytest.mark.asyncio
async def test_end_to_end_mtls_handshake(tmp_path: Path) -> None:
    """End-to-end test: bootstrap CA, issue server + client certs, handshake, RPC."""
    # Bootstrap CA
    ca_dir = tmp_path / "ca"
    ca = InternalCA.bootstrap(ca_dir)

    # Generate server cert (use issue_server_cert with localhost DNS SAN)
    server_csr_pem, server_key_pem = make_csr()
    server_cert_pem = ca.issue_server_cert(
        server_csr_pem, server_id="fleet-server", ttl=timedelta(hours=1), dns_names=["localhost", "127.0.0.1"]
    )

    # Generate client cert
    client_csr_pem, client_key_pem = make_csr()
    client_cert_pem = ca.issue_host_cert(
        client_csr_pem, host_id="host-1", ttl=timedelta(hours=1)
    )

    # Build CA chain for verification
    root_crt_pem = ca.root_cert.public_bytes(serialization.Encoding.PEM)
    int_crt_pem = ca.int_cert.public_bytes(serialization.Encoding.PEM)
    ca_chain_pem = root_crt_pem + int_crt_pem

    # Create server
    server, bound_addr, _dispatcher = make_grpc_server(
        server_cert_chain_pem=server_cert_pem + int_crt_pem,
        server_key_pem=server_key_pem,
        client_ca_pem=ca_chain_pem,
        bind_address="127.0.0.1:0",
    )

    await server.start()
    try:
        # Extract actual port
        _host, port_str = bound_addr.rsplit(":", 1)
        port = int(port_str)

        # Connect client
        creds = grpc.ssl_channel_credentials(
            root_certificates=ca_chain_pem,
            private_key=client_key_pem,
            certificate_chain=client_cert_pem + int_crt_pem,
        )
        async with grpc.aio.secure_channel(
            f"127.0.0.1:{port}",
            creds,
            options=[("grpc.ssl_target_name_override", "localhost")],
        ) as channel:
            stub = agent_bridge_pb2_grpc.AgentBridgeStub(channel)

            # Try to invoke Stream (should succeed with real handler)
            call = stub.Stream(iter([]))
            async for _ in call:
                pass
            # If we get here, the stream completed cleanly
    finally:
        await server.stop(grace=5)


@pytest.mark.asyncio
async def test_handshake_rejects_unknown_client_ca(tmp_path: Path) -> None:
    """Client cert signed by different CA must be rejected."""
    # Bootstrap first CA
    ca1_dir = tmp_path / "ca1"
    ca1 = InternalCA.bootstrap(ca1_dir)

    # Bootstrap second CA
    ca2_dir = tmp_path / "ca2"
    ca2 = InternalCA.bootstrap(ca2_dir)

    # Server uses CA1
    server_csr_pem, server_key_pem = make_csr()
    server_cert_pem = ca1.issue_server_cert(
        server_csr_pem, server_id="fleet-server", ttl=timedelta(hours=1), dns_names=["localhost", "127.0.0.1"]
    )

    # Client uses CA2 (different)
    client_csr_pem, client_key_pem = make_csr()
    client_cert_pem = ca2.issue_host_cert(
        client_csr_pem, host_id="host-1", ttl=timedelta(hours=1)
    )

    # Server trusts only CA1
    ca1_root_pem = ca1.root_cert.public_bytes(serialization.Encoding.PEM)
    ca1_int_pem = ca1.int_cert.public_bytes(serialization.Encoding.PEM)
    ca1_chain = ca1_root_pem + ca1_int_pem

    server, bound_addr, _dispatcher = make_grpc_server(
        server_cert_chain_pem=server_cert_pem + ca1_int_pem,
        server_key_pem=server_key_pem,
        client_ca_pem=ca1_chain,
        bind_address="127.0.0.1:0",
    )

    await server.start()
    try:
        _host, port_str = bound_addr.rsplit(":", 1)
        port = int(port_str)

        # Client tries to connect with CA2-signed cert
        ca2_root_pem = ca2.root_cert.public_bytes(serialization.Encoding.PEM)
        ca2_int_pem = ca2.int_cert.public_bytes(serialization.Encoding.PEM)
        ca2_chain = ca2_root_pem + ca2_int_pem

        creds = grpc.ssl_channel_credentials(
            root_certificates=ca2_chain,
            private_key=client_key_pem,
            certificate_chain=ca2_int_pem + client_cert_pem,
        )

        with pytest.raises(Exception):  # SSL/TLS error
            async with grpc.aio.secure_channel(
                f"127.0.0.1:{port}",
                creds,
                options=[("grpc.ssl_target_name_override", "localhost")],
            ) as channel:
                stub = agent_bridge_pb2_grpc.AgentBridgeStub(channel)
                call = stub.Stream(iter([]))
                async for _ in call:
                    pass
    finally:
        await server.stop(grace=5)


@pytest.mark.asyncio
async def test_handshake_requires_client_cert(tmp_path: Path) -> None:
    """Client must present a cert; bare root cert should fail."""
    ca_dir = tmp_path / "ca"
    ca = InternalCA.bootstrap(ca_dir)

    # Server cert
    server_csr_pem, server_key_pem = make_csr()
    server_cert_pem = ca.issue_server_cert(
        server_csr_pem, server_id="fleet-server", ttl=timedelta(hours=1), dns_names=["localhost", "127.0.0.1"]
    )

    ca_root_pem = ca.root_cert.public_bytes(serialization.Encoding.PEM)
    ca_int_pem = ca.int_cert.public_bytes(serialization.Encoding.PEM)
    ca_chain = ca_root_pem + ca_int_pem

    server, bound_addr, _dispatcher = make_grpc_server(
        server_cert_chain_pem=server_cert_pem + ca_int_pem,
        server_key_pem=server_key_pem,
        client_ca_pem=ca_chain,
        bind_address="127.0.0.1:0",
    )

    await server.start()
    try:
        _host, port_str = bound_addr.rsplit(":", 1)
        port = int(port_str)

        # Connect without client cert (only root for verification)
        creds = grpc.ssl_channel_credentials(root_certificates=ca_chain)

        with pytest.raises(Exception):  # SSL/TLS error
            async with grpc.aio.secure_channel(
                f"127.0.0.1:{port}",
                creds,
                options=[("grpc.ssl_target_name_override", "localhost")],
            ) as channel:
                stub = agent_bridge_pb2_grpc.AgentBridgeStub(channel)
                call = stub.Stream(iter([]))
                async for _ in call:
                    pass
    finally:
        await server.stop(grace=5)
