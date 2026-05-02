"""Command envelope signing, verification, and replay protection."""

from __future__ import annotations

from datetime import datetime, timezone
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


class SequenceTracker:
    """Per-host monotonic sequence + nonce dedup with bounded LRU.

    Tracks:
    - Last seen sequence per host (for monotonicity)
    - Recent nonces per host (LRU window for replay detection)
    """

    def __init__(self, nonce_window: int = 1024) -> None:
        """Initialize tracker.

        Args:
            nonce_window: Maximum number of nonces to track per host.
        """
        self.nonce_window = nonce_window
        self._last_seq: dict[str, int] = {}  # host_id -> last sequence
        self._nonces: dict[str, list[bytes]] = {}  # host_id -> [nonces] (FIFO queue)

    def accept(
        self,
        env: envelope_pb2.CommandEnvelope,
        *,
        now: datetime | None = None,
    ) -> None:
        """Accept an envelope if it passes all checks.

        Args:
            env: CommandEnvelope to validate.
            now: Current time (defaults to now(timezone.utc)).

        Raises:
            ExpiredCommandError: If expires_at <= now.
            SequenceRegressionError: If sequence <= last_seen[host_id].
            DuplicateNonceError: If nonce seen within window.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # Check expiration
        expires_at = env.expires_at.ToDatetime(tzinfo=timezone.utc)
        if expires_at <= now:
            raise ExpiredCommandError(f"Command expired at {expires_at}")

        host_id = env.host_id
        nonce = env.nonce

        # Check sequence monotonicity
        last_seq = self._last_seq.get(host_id, 0)
        if env.sequence <= last_seq:
            raise SequenceRegressionError(
                f"Host {host_id}: sequence {env.sequence} <= last {last_seq}"
            )

        # Check nonce dedup
        if host_id in self._nonces and nonce in self._nonces[host_id]:
            raise DuplicateNonceError(
                f"Host {host_id}: nonce {nonce!r} already seen"
            )

        # Update state
        self._last_seq[host_id] = env.sequence
        if host_id not in self._nonces:
            self._nonces[host_id] = []
        self._nonces[host_id].append(nonce)

        # Trim LRU window
        if len(self._nonces[host_id]) > self.nonce_window:
            self._nonces[host_id].pop(0)
