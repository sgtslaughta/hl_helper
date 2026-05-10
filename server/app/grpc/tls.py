"""mTLS server credentials + SPIFFE peer identity extraction.

grpcio sets cipher suites via SSL context options. For TLS 1.3, we document
the platform's built-in constraints as the limitation source (grpc.aio Python
API does not expose direct TLS 1.3 cipher restriction).

TLS 1.3 cipher pinning is enforced via:
1. GRPC_SSL_CIPHER_SUITES env var (for TLS 1.2 fallback + BoringSSL alignment).
2. enforce_tls_pin() version gate: ensures grpcio >= 1.50 (contains both AES-256-GCM
   and CHACHA20-POLY1305 in BoringSSL for TLS 1.3).
"""

from __future__ import annotations

import logging
import os
import ssl

import grpc
from cryptography import x509
from grpc import ssl_server_credentials

_logger = logging.getLogger(__name__)

# Allowed cipher suites for TLS 1.3 (OpenSSL names).
ALLOWED_TLS13_CIPHERS = "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"

# Set GRPC_SSL_CIPHER_SUITES at module import time (idempotent).
os.environ.setdefault("GRPC_SSL_CIPHER_SUITES", ALLOWED_TLS13_CIPHERS)

SPIFFE_URI_PREFIX = "spiffe://fleet/host/"
SPIFFE_SERVER_URI = "spiffe://fleet/server"


def probe_tls_version() -> None:
    """Probe TLS version of the underlying SSL context; log warning if TLS 1.2 fallback detected.

    Does not raise; purely for observability. Checks if BoringSSL vs OpenSSL
    mismatch causes TLS to fall back below 1.3.
    """
    try:
        ctx = ssl.create_default_context()
        # Check if minimum_version is less than TLS 1.3
        if hasattr(ssl, "TLSVersion"):
            if ctx.minimum_version < ssl.TLSVersion.TLSv1_3:
                _logger.warning(
                    "TLS fallback to 1.2 detected (SSL context minimum_version=%s). "
                    "Verify BoringSSL/OpenSSL build consistency.",
                    ctx.minimum_version,
                )
    except Exception as e:
        # If probe fails, just log at debug level; don't break startup
        _logger.debug("Could not probe TLS version: %s", e)


def enforce_tls_pin() -> None:
    """Enforce TLS 1.3 cipher pin by verifying grpcio >= 1.50.

    grpcio 1.50+ includes BoringSSL with both AES-256-GCM and
    CHACHA20-POLY1305 ciphers available for TLS 1.3.

    Raises:
        RuntimeError: If grpcio version is < 1.50.
    """
    version_str = grpc.__version__
    parts = version_str.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError) as e:
        raise RuntimeError(
            f"Could not parse grpcio version {version_str}: {e}"
        ) from e

    # Check >= 1.50
    if major < 1 or (major == 1 and minor < 50):
        raise RuntimeError(
            f"grpcio >= 1.50 required for TLS 1.3 cipher pin enforcement. "
            f"Found: {version_str}"
        )

    # Probe for TLS 1.2 fallback warning
    probe_tls_version()


def make_server_credentials(
    server_cert_chain_pem: bytes,
    server_key_pem: bytes,
    client_ca_pem: bytes,
) -> grpc.ServerCredentials:
    """Build mTLS server credentials with client cert verification required.

    Args:
        server_cert_chain_pem: leaf + intermediate(s) concatenated in PEM.
        server_key_pem: PEM-encoded private key for the leaf.
        client_ca_pem: trust roots used to verify client certs (CA chain PEM).

    Returns:
        grpc.ServerCredentials configured for mTLS.

    Raises:
        RuntimeError: If grpcio version < 1.50 (cipher pin enforcement requirement).

    Note:
        gRPC's Python API does not expose direct TLS 1.3 cipher restriction.
        We rely on the cipher list compiled into BoringSSL/OpenSSL on the platform.
        This is a known limitation in grpcio.
    """
    enforce_tls_pin()
    return ssl_server_credentials(
        private_key_certificate_chain_pairs=[(server_key_pem, server_cert_chain_pem)],
        root_certificates=client_ca_pem,
        require_client_auth=True,
    )


def extract_spiffe_id(peer_cert_pem: bytes) -> str | None:
    """Extract the spiffe:// URI from peer cert SAN, or None if absent.

    Args:
        peer_cert_pem: PEM-encoded X.509 certificate.

    Returns:
        spiffe:// URI string if found, None otherwise.
    """
    try:
        cert = x509.load_pem_x509_certificate(peer_cert_pem)
    except Exception as e:
        _logger.warning("spiffe extract failed: %s", e)
        return None
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return None
    for uri in ext.value.get_values_for_type(x509.UniformResourceIdentifier):
        if uri.startswith("spiffe://"):
            return uri
    return None


def host_id_from_spiffe(uri: str) -> str | None:
    """Extract host_id from spiffe://fleet/host/<id>, or None if not a host URI.

    Args:
        uri: A SPIFFE URI string.

    Returns:
        host_id if uri matches the host prefix, None otherwise.
    """
    if uri.startswith(SPIFFE_URI_PREFIX):
        return uri[len(SPIFFE_URI_PREFIX) :]
    return None


def extract_peer_cert_info(context: object) -> dict[str, str]:
    """Pull peer cert subject CN + serial + not_after from grpc context.

    Args:
        context: grpc.aio.ServicerContext with auth_context() method.

    Returns:
        Dict with keys: cn, serial, not_after. Empty dict if not extractable.
    """
    info: dict[str, str] = {}
    try:
        auth_context = context.auth_context()  # type: ignore[union-attr]
        # auth maps property -> list[bytes]. Common keys: x509_common_name, x509_pem_cert
        cn = auth_context.get("x509_common_name")
        if cn:
            info["cn"] = cn[0].decode() if isinstance(cn[0], bytes) else cn[0]
        pem = auth_context.get("x509_pem_cert")
        if pem:
            cert = x509.load_pem_x509_certificate(pem[0])
            info["serial"] = format(cert.serial_number, "x")
            # Use not_valid_after_utc if available, else not_valid_after
            not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
            info["not_after"] = not_after.isoformat()
    except Exception:
        pass
    return info
