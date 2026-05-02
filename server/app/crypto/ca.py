"""Internal X.509 Certificate Authority for hl_helper.

Bootstraps a 5-year self-signed Ed25519 root CA + 1-year intermediate (issuing)
CA stored on disk under a single directory. Issues short-lived per-host client
certificates with SPIFFE-style URI SANs (`spiffe://fleet/host/<uuid>`).

Files written under the bootstrap directory:
    root.key   -- Ed25519 private key, mode 0600
    root.crt   -- self-signed root CA cert, PEM
    int.key    -- Ed25519 private key, mode 0600
    int.crt    -- intermediate cert signed by root, PEM
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT_TTL = timedelta(days=365 * 5)
INT_TTL = timedelta(days=365)
SPIFFE_AUTHORITY = "fleet"
BACKDATE = timedelta(minutes=1)


@dataclass
class InternalCA:
    """Server-managed two-tier internal CA backed by Ed25519."""

    root_key: ed25519.Ed25519PrivateKey
    root_cert: x509.Certificate
    int_key: ed25519.Ed25519PrivateKey
    int_cert: x509.Certificate

    # ------------------------------------------------------------------
    # Bootstrap / load
    # ------------------------------------------------------------------

    @classmethod
    def bootstrap(cls, dir: Path | str) -> "InternalCA":
        """Create a fresh CA hierarchy on disk and return it.

        Idempotent in the sense of files: callers should not invoke twice on the
        same directory; the second call will *overwrite* keys/certs.
        """
        d = Path(dir)
        d.mkdir(parents=True, exist_ok=True)

        root_key = ed25519.Ed25519PrivateKey.generate()
        root_cert = cls._build_self_signed_root(root_key)

        int_key = ed25519.Ed25519PrivateKey.generate()
        int_cert = cls._build_intermediate(root_key, root_cert, int_key)

        cls._write_private_key(d / "root.key", root_key)
        cls._write_certificate(d / "root.crt", root_cert)
        cls._write_private_key(d / "int.key", int_key)
        cls._write_certificate(d / "int.crt", int_cert)

        return cls(
            root_key=root_key,
            root_cert=root_cert,
            int_key=int_key,
            int_cert=int_cert,
        )

    @classmethod
    def load(cls, dir: Path | str) -> "InternalCA":
        """Load an existing CA from disk."""
        d = Path(dir)
        root_key = serialization.load_pem_private_key(
            (d / "root.key").read_bytes(), password=None
        )
        int_key = serialization.load_pem_private_key(
            (d / "int.key").read_bytes(), password=None
        )
        if not isinstance(root_key, ed25519.Ed25519PrivateKey):
            raise ValueError("root.key is not Ed25519")
        if not isinstance(int_key, ed25519.Ed25519PrivateKey):
            raise ValueError("int.key is not Ed25519")
        root_cert = x509.load_pem_x509_certificate((d / "root.crt").read_bytes())
        int_cert = x509.load_pem_x509_certificate((d / "int.crt").read_bytes())
        return cls(
            root_key=root_key,
            root_cert=root_cert,
            int_key=int_key,
            int_cert=int_cert,
        )

    # ------------------------------------------------------------------
    # Issuance
    # ------------------------------------------------------------------

    def issue_host_cert(
        self,
        csr_pem: bytes,
        *,
        host_id: str,
        ttl: timedelta,
        dns_names: list[str] | None = None,
    ) -> bytes:
        """Sign a host CSR, returning the leaf cert as PEM bytes.

        Args:
            csr_pem: PEM-encoded certificate signing request.
            host_id: Identifier for the host (used in SPIFFE URI and CN).
            ttl: Certificate time-to-live.
            dns_names: Optional list of DNS names to add to SAN (in addition to SPIFFE URI).

        Returns:
            PEM-encoded leaf certificate.
        """
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        csr = x509.load_pem_x509_csr(csr_pem)
        if not csr.is_signature_valid:
            raise ValueError("invalid csr signature")

        now = datetime.now(timezone.utc)
        spiffe_id = f"spiffe://{SPIFFE_AUTHORITY}/host/{host_id}"

        # Build SAN with SPIFFE URI + optional DNS names
        san_list = [x509.UniformResourceIdentifier(spiffe_id)]
        if dns_names:
            san_list.extend(x509.DNSName(name) for name in dns_names)

        builder = (
            x509.CertificateBuilder()
            .subject_name(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host_id)])
            )
            .issuer_name(self.int_cert.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - BACKDATE)
            .not_valid_after(now + ttl)
            .add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=True,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
        )
        cert = builder.sign(private_key=self.int_key, algorithm=None)
        return cert.public_bytes(serialization.Encoding.PEM)

    def issue_server_cert(
        self,
        csr_pem: bytes,
        *,
        server_id: str,
        ttl: timedelta,
        dns_names: list[str] | None = None,
    ) -> bytes:
        """Sign a server CSR with spiffe://fleet/server URI, returning the leaf cert as PEM bytes.

        Args:
            csr_pem: PEM-encoded certificate signing request.
            server_id: Identifier for the server (used in CN).
            ttl: Certificate time-to-live.
            dns_names: Optional list of DNS names to add to SAN (in addition to SPIFFE URI).

        Returns:
            PEM-encoded leaf certificate.
        """
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        csr = x509.load_pem_x509_csr(csr_pem)
        if not csr.is_signature_valid:
            raise ValueError("invalid csr signature")

        now = datetime.now(timezone.utc)
        spiffe_id = f"spiffe://{SPIFFE_AUTHORITY}/server"

        # Build SAN with SPIFFE URI + optional DNS names
        san_list = [x509.UniformResourceIdentifier(spiffe_id)]
        if dns_names:
            san_list.extend(x509.DNSName(name) for name in dns_names)

        builder = (
            x509.CertificateBuilder()
            .subject_name(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, server_id)])
            )
            .issuer_name(self.int_cert.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - BACKDATE)
            .not_valid_after(now + ttl)
            .add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=True,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
        )
        cert = builder.sign(private_key=self.int_key, algorithm=None)
        return cert.public_bytes(serialization.Encoding.PEM)

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify_chain(self, leaf_pem: bytes) -> bool:
        """Verify leaf -> intermediate -> root chain.

        Checks signatures only. Does **not** check expiry, revocation, or EKU;
        callers in the request path apply those policies separately.
        """
        try:
            leaf = x509.load_pem_x509_certificate(leaf_pem)
        except Exception:
            return False
        try:
            int_pub = self.int_cert.public_key()
            if isinstance(int_pub, ed25519.Ed25519PublicKey):
                int_pub.verify(leaf.signature, leaf.tbs_certificate_bytes)
            else:
                return False
            root_pub = self.root_cert.public_key()
            if isinstance(root_pub, ed25519.Ed25519PublicKey):
                root_pub.verify(
                    self.int_cert.signature, self.int_cert.tbs_certificate_bytes
                )
            else:
                return False
        except Exception:
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_self_signed_root(key: ed25519.Ed25519PrivateKey) -> x509.Certificate:
        now = datetime.now(timezone.utc)
        name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "hl_helper Root CA")]
        )
        builder = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - BACKDATE)
            .not_valid_after(now + ROOT_TTL)
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=1), critical=True
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
        )
        return builder.sign(private_key=key, algorithm=None)

    @staticmethod
    def _build_intermediate(
        root_key: ed25519.Ed25519PrivateKey,
        root_cert: x509.Certificate,
        int_key: ed25519.Ed25519PrivateKey,
    ) -> x509.Certificate:
        now = datetime.now(timezone.utc)
        name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "hl_helper Issuing CA")]
        )
        builder = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(root_cert.subject)
            .public_key(int_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - BACKDATE)
            .not_valid_after(now + INT_TTL)
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0), critical=True
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
        )
        return builder.sign(private_key=root_key, algorithm=None)

    @staticmethod
    def _write_private_key(path: Path, key: ed25519.Ed25519PrivateKey) -> None:
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        # Atomic-ish write with strict perms.
        path.write_bytes(pem)
        os.chmod(path, 0o600)

    @staticmethod
    def _write_certificate(path: Path, cert: x509.Certificate) -> None:
        path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        os.chmod(path, 0o644)
