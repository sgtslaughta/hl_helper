"""mTLS server credentials + SPIFFE peer identity extraction.

grpcio sets cipher suites via SSL context options. For TLS 1.3, we document
the platform's built-in constraints as the limitation source (grpc.aio Python
API does not expose direct TLS 1.3 cipher restriction).
"""

from __future__ import annotations

import grpc
from cryptography import x509
from grpc import ssl_server_credentials

# Allowed cipher suites for TLS 1.3 (OpenSSL names).
ALLOWED_TLS13_CIPHERS = "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"

SPIFFE_URI_PREFIX = "spiffe://fleet/host/"
SPIFFE_SERVER_URI = "spiffe://fleet/server"


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

    Note:
        gRPC's Python API does not expose direct TLS 1.3 cipher restriction.
        We rely on the cipher list compiled into BoringSSL/OpenSSL on the platform.
        This is a known limitation in grpcio.
    """
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
    except Exception:
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
