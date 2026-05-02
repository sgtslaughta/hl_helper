"""Tests for server.app.crypto.ca.InternalCA."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from server.app.crypto.ca import InternalCA


@pytest.fixture
def ca(tmp_path: Path) -> InternalCA:
    return InternalCA.bootstrap(tmp_path)


def _make_csr(host_id: str) -> tuple[ed25519.Ed25519PrivateKey, bytes]:
    """Build a fresh Ed25519 keypair + CSR with CN=host_id."""
    key = ed25519.Ed25519PrivateKey.generate()
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, host_id)])
        )
        .sign(key, algorithm=None)
    )
    return key, csr.public_bytes(serialization.Encoding.PEM)


def test_bootstrap_creates_root_and_intermediate(tmp_path: Path) -> None:
    InternalCA.bootstrap(tmp_path)
    assert (tmp_path / "root.key").exists()
    assert (tmp_path / "root.crt").exists()
    assert (tmp_path / "int.key").exists()
    assert (tmp_path / "int.crt").exists()
    # File modes 0600 for keys.
    assert (tmp_path / "root.key").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "int.key").stat().st_mode & 0o777 == 0o600
    # Root cert is self-signed CA, intermediate is signed by root.
    root_cert = x509.load_pem_x509_certificate((tmp_path / "root.crt").read_bytes())
    int_cert = x509.load_pem_x509_certificate((tmp_path / "int.crt").read_bytes())
    assert root_cert.issuer == root_cert.subject
    assert int_cert.issuer == root_cert.subject


def test_issue_host_cert_signed_by_intermediate(ca: InternalCA) -> None:
    _, csr_pem = _make_csr("host-uuid-1234")
    cert_pem = ca.issue_host_cert(
        csr_pem, host_id="host-uuid-1234", ttl=timedelta(hours=24)
    )
    assert b"-----BEGIN CERTIFICATE-----" in cert_pem
    cert = x509.load_pem_x509_certificate(cert_pem)
    # SPIFFE URI SAN.
    san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    uris = san_ext.value.get_values_for_type(x509.UniformResourceIdentifier)
    assert "spiffe://fleet/host/host-uuid-1234" in uris


def test_verify_chain_accepts_freshly_issued(ca: InternalCA) -> None:
    _, csr_pem = _make_csr("host-A")
    cert_pem = ca.issue_host_cert(csr_pem, host_id="host-A", ttl=timedelta(hours=24))
    assert ca.verify_chain(cert_pem) is True


def test_verify_chain_rejects_unrelated_cert(ca: InternalCA, tmp_path: Path) -> None:
    other_ca = InternalCA.bootstrap(tmp_path / "other")
    _, csr_pem = _make_csr("host-B")
    foreign_pem = other_ca.issue_host_cert(
        csr_pem, host_id="host-B", ttl=timedelta(hours=24)
    )
    assert ca.verify_chain(foreign_pem) is False


def test_issue_rejects_invalid_csr_signature(ca: InternalCA) -> None:
    # Build a CSR signed with one key but tamper-replace the public key with another.
    k1 = ed25519.Ed25519PrivateKey.generate()
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "host-X")])
        )
        .sign(k1, algorithm=None)
    )
    # Flip a byte in the signature region — easiest by re-encoding then mangling.
    pem = csr.public_bytes(serialization.Encoding.PEM)
    der = csr.public_bytes(serialization.Encoding.DER)
    bad_der = der[:-1] + bytes([der[-1] ^ 0xFF])
    bad_pem = (
        b"-----BEGIN CERTIFICATE REQUEST-----\n"
        + __import__("base64").encodebytes(bad_der)
        + b"-----END CERTIFICATE REQUEST-----\n"
    )
    del pem
    with pytest.raises(ValueError):
        ca.issue_host_cert(bad_pem, host_id="host-X", ttl=timedelta(hours=24))


def test_issue_respects_ttl(ca: InternalCA) -> None:
    _, csr_pem = _make_csr("host-ttl")
    cert_pem = ca.issue_host_cert(csr_pem, host_id="host-ttl", ttl=timedelta(hours=24))
    cert = x509.load_pem_x509_certificate(cert_pem)
    span = cert.not_valid_after_utc - cert.not_valid_before_utc
    # 24h ± a couple of minutes of bookkeeping (small backdate to tolerate clock skew).
    assert timedelta(hours=23, minutes=55) <= span <= timedelta(hours=24, minutes=10)


def test_issue_rejects_zero_or_negative_ttl(ca: InternalCA) -> None:
    _, csr_pem = _make_csr("host-bad")
    with pytest.raises(ValueError):
        ca.issue_host_cert(csr_pem, host_id="host-bad", ttl=timedelta(seconds=0))
    with pytest.raises(ValueError):
        ca.issue_host_cert(csr_pem, host_id="host-bad", ttl=timedelta(hours=-1))


def test_verify_chain_rejects_tampered_leaf(ca: InternalCA) -> None:
    _, csr_pem = _make_csr("host-tamper")
    cert_pem = ca.issue_host_cert(
        csr_pem, host_id="host-tamper", ttl=timedelta(hours=24)
    )
    # Flip a byte in the middle of the PEM body and re-encode.
    cert = x509.load_pem_x509_certificate(cert_pem)
    der = cert.public_bytes(serialization.Encoding.DER)
    bad_der = der[:200] + bytes([der[200] ^ 0xFF]) + der[201:]
    import base64

    bad_pem = (
        b"-----BEGIN CERTIFICATE-----\n"
        + base64.encodebytes(bad_der)
        + b"-----END CERTIFICATE-----\n"
    )
    assert ca.verify_chain(bad_pem) is False
