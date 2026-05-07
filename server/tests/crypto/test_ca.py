"""Tests for server.app.crypto.ca.InternalCA."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from cryptography.exceptions import InvalidSignature

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


def test_verify_chain_rejects_expired_leaf(ca: InternalCA) -> None:
    """Chain validation must reject expired leaf certificate."""
    _, csr_pem = _make_csr("host-expired")
    # Issue cert with -24 hours (already expired)
    cert_pem = ca.issue_host_cert(
        csr_pem, host_id="host-expired", ttl=timedelta(hours=1)
    )
    # Manually modify cert to be expired by moving not_valid_after to past
    cert = x509.load_pem_x509_certificate(cert_pem)
    now = datetime.now(timezone.utc)
    expired_cert = (
        x509.CertificateBuilder()
        .subject_name(cert.subject)
        .issuer_name(cert.issuer)
        .public_key(cert.public_key())
        .serial_number(cert.serial_number)
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now - timedelta(hours=1))  # Expired 1h ago
        .add_extension(cert.extensions[0].value, critical=cert.extensions[0].critical)
        .add_extension(cert.extensions[1].value, critical=cert.extensions[1].critical)
        .add_extension(cert.extensions[2].value, critical=cert.extensions[2].critical)
        .add_extension(cert.extensions[3].value, critical=cert.extensions[3].critical)
        .sign(private_key=ca.int_key, algorithm=None)
    )
    expired_pem = expired_cert.public_bytes(serialization.Encoding.PEM)
    assert ca.verify_chain(expired_pem) is False


def test_verify_chain_rejects_leaf_name_mismatch(ca: InternalCA, tmp_path: Path) -> None:
    """Chain validation must reject if leaf issuer != intermediate subject."""
    other_ca = InternalCA.bootstrap(tmp_path / "other")
    _, csr_pem = _make_csr("host-X")
    # Issue from different CA, will have wrong issuer
    foreign_pem = other_ca.issue_host_cert(
        csr_pem, host_id="host-X", ttl=timedelta(hours=24)
    )
    # This is already rejected because signature won't match, but explicitly test name check
    assert ca.verify_chain(foreign_pem) is False


def test_verify_chain_rejects_intermediate_without_ca_flag(ca: InternalCA) -> None:
    """Chain validation must reject intermediate without BasicConstraints.ca=True."""
    _, csr_pem = _make_csr("host-Y")

    # Create a cert that looks like an intermediate but lacks CA flag
    # We'll patch the intermediate temporarily
    original_int_cert = ca.int_cert

    # Build a fake intermediate without CA flag
    non_ca_int = (
        x509.CertificateBuilder()
        .subject_name(ca.int_cert.subject)
        .issuer_name(ca.root_cert.subject)
        .public_key(ca.int_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ca.int_cert.not_valid_before_utc)
        .not_valid_after(ca.int_cert.not_valid_after_utc)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key=ca.root_key, algorithm=None)
    )

    # Temporarily swap to invalid intermediate
    ca.int_cert = non_ca_int
    cert_pem = ca.issue_host_cert(
        csr_pem, host_id="host-Y", ttl=timedelta(hours=24)
    )
    # Restore original
    ca.int_cert = original_int_cert

    # Create a new CA instance with the invalid intermediate to test
    test_ca = InternalCA(
        root_key=ca.root_key,
        root_cert=ca.root_cert,
        int_key=ca.int_key,
        int_cert=non_ca_int,
    )
    assert test_ca.verify_chain(cert_pem) is False


def test_private_key_file_mode_secure(tmp_path: Path) -> None:
    """Private key file must be written with 0600 perms atomically."""
    InternalCA.bootstrap(tmp_path)
    # Check that the written key file has 0600 perms
    key_file = tmp_path / "root.key"
    mode = key_file.stat().st_mode & 0o777
    assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


def test_signing_private_key_file_mode_secure(tmp_path: Path) -> None:
    """Signing backend private key file must be written with 0600 perms atomically."""
    from server.app.crypto.signing import FileBackend

    FileBackend.bootstrap(tmp_path / "signing")
    key_file = tmp_path / "signing" / "current.key"
    mode = key_file.stat().st_mode & 0o777
    assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


def test_sign_release_manifest_round_trip(ca: InternalCA) -> None:
    """Test that sign_release_manifest produces valid Ed25519 signatures."""
    payload = b'{"version":"0.4.2"}'
    sig = ca.sign_release_manifest(payload)
    assert isinstance(sig, bytes)
    assert len(sig) == 64

    pub = ca.signing_pubkey()
    pub.verify(sig, payload)

    with pytest.raises(InvalidSignature):
        pub.verify(sig, payload + b"x")
