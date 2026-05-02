"""Command envelope signing, verification, and replay protection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from server.app.grpc._pb import fleet  # noqa: F401  triggers sys.path injection
from server.app.grpc._pb.fleet.v1 import envelope_pb2

if TYPE_CHECKING:
    from server.app.crypto.signing import SigningBackend


# Exception classes
class ExpiredCommandError(Exception):
    """Raised when command's expires_at <= now."""

    pass


class ReplayError(Exception):
    """Base for replay protection errors."""

    pass


class SequenceRegressionError(ReplayError):
    """Raised when sequence does not increase monotonically."""

    pass


class DuplicateNonceError(ReplayError):
    """Raised when nonce is reused within the window."""

    pass


def canonical_bytes(env: envelope_pb2.CommandEnvelope) -> bytes:
    """Return deterministic byte representation with signature field cleared.

    Args:
        env: CommandEnvelope to canonicalize.

    Returns:
        Serialized bytes of envelope with signature=b''.
    """
    # Make a copy to avoid mutating the original
    copy = envelope_pb2.CommandEnvelope()
    copy.CopyFrom(env)
    copy.signature = b""
    return copy.SerializeToString(deterministic=True)  # type: ignore[no-any-return]


def sign_command(
    env: envelope_pb2.CommandEnvelope, backend: SigningBackend
) -> envelope_pb2.CommandEnvelope:
    """Set env.signature from backend.sign(canonical_bytes(env)).

    Args:
        env: CommandEnvelope to sign. Modified in-place.
        backend: SigningBackend to use for signing.

    Returns:
        Same env object with signature field set.
    """
    sig = backend.sign(canonical_bytes(env))
    env.signature = sig
    return env


def verify_command(
    env: envelope_pb2.CommandEnvelope, trust_anchors: list[bytes]
) -> bool:
    """Verify envelope signature against any trust anchor.

    Args:
        env: CommandEnvelope to verify.
        trust_anchors: List of Ed25519 raw 32-byte pubkeys (PEM-encoded).

    Returns:
        True if signature verifies under any anchor; False otherwise.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    canonical = canonical_bytes(env)
    sig = env.signature

    for anchor_pem in trust_anchors:
        try:
            pub = serialization.load_pem_public_key(anchor_pem)
            if not isinstance(pub, ed25519.Ed25519PublicKey):
                continue
            pub.verify(sig, canonical)
            return True
        except Exception:
            continue

    return False
