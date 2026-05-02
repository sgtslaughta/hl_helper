"""Result envelope signing and verification."""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import results_pb2


def canonical_result_bytes(env: results_pb2.ResultEnvelope) -> bytes:
    """Return deterministic byte representation with signature field cleared.

    Args:
        env: ResultEnvelope to canonicalize.

    Returns:
        Serialized bytes of envelope with signature=b''.
    """
    copy = results_pb2.ResultEnvelope()
    copy.CopyFrom(env)
    copy.signature = b""
    return copy.SerializeToString(deterministic=True)  # type: ignore[no-any-return]


def verify_result(env: results_pb2.ResultEnvelope, agent_pubkey: bytes) -> bool:
    """Verify env.signature against the host's raw 32-byte Ed25519 pubkey.

    Args:
        env: ResultEnvelope to verify.
        agent_pubkey: Raw 32-byte Ed25519 public key.

    Returns:
        True if signature verifies; False otherwise.
    """
    if len(agent_pubkey) != 32 or not env.signature:
        return False
    try:
        pk = ed25519.Ed25519PublicKey.from_public_bytes(agent_pubkey)
        pk.verify(env.signature, canonical_result_bytes(env))
        return True
    except (InvalidSignature, ValueError):
        return False


def sign_result(
    env: results_pb2.ResultEnvelope,
    agent_signing_key: ed25519.Ed25519PrivateKey,
) -> results_pb2.ResultEnvelope:
    """Sign ResultEnvelope in-place.

    Args:
        env: ResultEnvelope to sign. Modified in-place.
        agent_signing_key: Ed25519 private key for signing.

    Returns:
        Same env object with signature field set.
    """
    env.signature = agent_signing_key.sign(canonical_result_bytes(env))
    return env
