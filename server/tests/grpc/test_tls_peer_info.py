"""Tests for extract_peer_cert_info from tls module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from server.app.grpc.tls import extract_peer_cert_info


@pytest.fixture
def mock_context_with_cert() -> tuple[MagicMock, bytes]:
    """Create a mock grpc context with a valid test certificate."""
    # Generate a test private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Build certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "test-agent-123"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(0xDEADBEEF)
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30))
        .sign(private_key, hashes.SHA256())
    )

    # Serialize to PEM
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)

    # Create mock context
    mock_ctx = MagicMock()
    mock_ctx.auth_context.return_value = {
        "x509_common_name": [b"test-agent-123"],
        "x509_pem_cert": [cert_pem],
    }

    return mock_ctx, cert_pem


@pytest.fixture
def mock_context_without_cert() -> MagicMock:
    """Create a mock grpc context without cert info."""
    mock_ctx = MagicMock()
    mock_ctx.auth_context.return_value = {}
    return mock_ctx


def test_extract_peer_cert_info_with_full_cert(
    mock_context_with_cert: tuple[MagicMock, bytes],
) -> None:
    """Test extracting CN, serial, and not_after from a valid cert."""
    mock_ctx, cert_pem = mock_context_with_cert

    info = extract_peer_cert_info(mock_ctx)

    assert info["cn"] == "test-agent-123"
    assert info["serial"] == "deadbeef"
    assert "not_after" in info
    # Verify not_after is ISO format
    datetime.fromisoformat(info["not_after"])


def test_extract_peer_cert_info_without_cert(
    mock_context_without_cert: MagicMock,
) -> None:
    """Test extracting from context with no cert returns empty dict."""
    info = extract_peer_cert_info(mock_context_without_cert)
    assert info == {}


def test_extract_peer_cert_info_with_broken_auth(
) -> None:
    """Test gracefully handling a context that raises on auth_context()."""
    mock_ctx = MagicMock()
    mock_ctx.auth_context.side_effect = Exception("auth error")

    info = extract_peer_cert_info(mock_ctx)
    assert info == {}


def test_extract_peer_cert_info_with_only_cn(
) -> None:
    """Test extracting when only CN is available (no PEM)."""
    mock_ctx = MagicMock()
    mock_ctx.auth_context.return_value = {
        "x509_common_name": [b"agent-xyz"],
    }

    info = extract_peer_cert_info(mock_ctx)
    assert info["cn"] == "agent-xyz"
    assert "serial" not in info
    assert "not_after" not in info
