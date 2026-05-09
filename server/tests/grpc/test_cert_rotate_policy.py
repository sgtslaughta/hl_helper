"""Tests for cert rotation policy."""
from __future__ import annotations

import time

import pytest


def test_rate_limiter_allows_first_call():
    from server.app.grpc.cert_rotate_policy import RotationRateLimiter

    rl = RotationRateLimiter(window_seconds=3600)
    assert rl.allow("host-1") is True


def test_rate_limiter_blocks_second_call_in_window():
    from server.app.grpc.cert_rotate_policy import RotationRateLimiter

    rl = RotationRateLimiter(window_seconds=3600)
    assert rl.allow("host-1") is True
    assert rl.allow("host-1") is False


def test_rate_limiter_allows_after_window(monkeypatch):
    from server.app.grpc import cert_rotate_policy

    base = 1_000_000.0
    monkeypatch.setattr(cert_rotate_policy.time, "monotonic", lambda: base)
    rl = cert_rotate_policy.RotationRateLimiter(window_seconds=3600)
    rl.allow("host-1")

    monkeypatch.setattr(cert_rotate_policy.time, "monotonic", lambda: base + 3601)
    assert rl.allow("host-1") is True


def test_rate_limiter_independent_per_host():
    from server.app.grpc.cert_rotate_policy import RotationRateLimiter

    rl = RotationRateLimiter(window_seconds=3600)
    assert rl.allow("host-a") is True
    assert rl.allow("host-b") is True


def _make_csr(common_name: str = "h-1") -> tuple[bytes, bytes]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
        )
        .sign(key, hashes.SHA256())
    )
    pem = csr.public_bytes(
        serialization.Encoding.PEM
    )
    pub_der = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem, pub_der


def test_validate_csr_accepts_valid_ecdsa_csr():
    from server.app.grpc.cert_rotate_policy import validate_csr

    csr_pem, _ = _make_csr("h-1")
    info = validate_csr(csr_pem, expected_cn="h-1")
    assert info.public_key_der is not None


def test_validate_csr_rejects_cn_mismatch():
    from server.app.grpc.cert_rotate_policy import (
        CSRValidationError,
        validate_csr,
    )

    csr_pem, _ = _make_csr("h-1")
    with pytest.raises(CSRValidationError):
        validate_csr(csr_pem, expected_cn="h-2")


def test_validate_csr_rejects_malformed():
    from server.app.grpc.cert_rotate_policy import (
        CSRValidationError,
        validate_csr,
    )

    with pytest.raises(CSRValidationError):
        validate_csr(b"not a csr", expected_cn="h-1")


def test_validate_csr_rejects_pubkey_match_with_current(monkeypatch):
    """Forward secrecy: CSR pubkey must differ from current TLS pubkey."""
    from server.app.grpc.cert_rotate_policy import (
        CSRValidationError,
        validate_csr,
    )

    csr_pem, pub_der = _make_csr("h-1")
    with pytest.raises(CSRValidationError, match="forward.secrecy"):
        validate_csr(
            csr_pem, expected_cn="h-1", current_tls_pubkey_der=pub_der
        )
