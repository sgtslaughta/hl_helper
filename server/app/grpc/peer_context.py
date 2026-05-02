"""Context manager for extracting SPIFFE peer identity from gRPC requests."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any

from .tls import extract_spiffe_id, host_id_from_spiffe

_peer_host_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "peer_host_id", default=None
)
_peer_spiffe_uri_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "peer_spiffe_uri", default=None
)


def current_peer_host_id() -> str | None:
    """Return the current peer's host_id extracted from SPIFFE URI, or None.

    Must be called within a peer_context() block.
    """
    return _peer_host_id_var.get()


def current_peer_spiffe_uri() -> str | None:
    """Return the current peer's full SPIFFE URI, or None.

    Must be called within a peer_context() block.
    """
    return _peer_spiffe_uri_var.get()


def _peer_cert_pem_from_context(context: Any) -> bytes | None:
    """Extract peer certificate PEM from grpc auth_context.

    Args:
        context: grpc.aio.ServicerContext from an RPC handler.

    Returns:
        PEM-encoded certificate bytes, or None if not present.
    """
    auth = context.auth_context()
    # Try both bytes and string keys
    certs = auth.get("x509_pem_cert") or []
    if not certs:
        return None
    pem = certs[0]
    if isinstance(pem, str):
        pem_bytes: bytes = pem.encode("utf-8")
    else:
        pem_bytes = pem
    return pem_bytes


@contextmanager
def peer_context(
    context: Any,
) -> Iterator[tuple[str | None, str | None]]:
    """Context manager that extracts SPIFFE identity from peer cert and binds it.

    Reads the peer's leaf certificate from the gRPC connection context,
    extracts the SPIFFE URI and host_id, and stores them in context vars
    accessible via current_peer_host_id() and current_peer_spiffe_uri().

    Args:
        context: grpc.aio.ServicerContext from an RPC handler.

    Yields:
        (host_id, spiffe_uri) tuple. Either or both may be None if not present.

    Example:
        async def Stream(self, request_iterator, context):
            with peer_context(context) as (host_id, spiffe_uri):
                # host_id and spiffe_uri are now available in context vars
                ...
    """
    pem = _peer_cert_pem_from_context(context)
    spiffe_uri = extract_spiffe_id(pem) if pem else None
    host_id = host_id_from_spiffe(spiffe_uri) if spiffe_uri else None

    tok_uri = _peer_spiffe_uri_var.set(spiffe_uri)
    tok_host = _peer_host_id_var.set(host_id)
    try:
        yield host_id, spiffe_uri
    finally:
        _peer_spiffe_uri_var.reset(tok_uri)
        _peer_host_id_var.reset(tok_host)
