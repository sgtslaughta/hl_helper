"""Tests for server.app.crypto.result_envelope: signing and verification."""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric import ed25519

from server.app.crypto.result_envelope import (
    canonical_result_bytes,
    sign_result,
    verify_result,
)
from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import results_pb2


def _make_result(
    host_id: str = "host1",
    command_id: str = "cmd1",
    sequence: int = 1,
    exit_code: int = 0,
    status: int = results_pb2.RESULT_OK,
    prev_hash: bytes = b"\x00" * 32,
) -> results_pb2.ResultEnvelope:
    """Factory to build a ResultEnvelope for testing."""
    env = results_pb2.ResultEnvelope()
    env.command_id = command_id
    env.host_id = host_id
    env.sequence = sequence
    env.exit_code = exit_code
    env.status = status
    env.final = True
    env.prev_result_hash = prev_hash
    return env


class TestCanonicalResultBytes:
    """Tests for canonical_result_bytes function."""

    def test_canonical_bytes_excludes_signature(self) -> None:
        """canonical_result_bytes should match when signature field is cleared."""
        env = _make_result()
        env.signature = b"junk-signature"

        canonical_with_junk = canonical_result_bytes(env)

        env.signature = b""
        canonical_empty = canonical_result_bytes(env)

        assert canonical_with_junk == canonical_empty

    def test_canonical_bytes_deterministic(self) -> None:
        """Two identical envelopes should produce identical canonical bytes."""
        env1 = _make_result()
        env2 = _make_result()

        assert canonical_result_bytes(env1) == canonical_result_bytes(env2)


class TestSignAndVerifyResult:
    """Tests for sign_result and verify_result functions."""

    def test_sign_then_verify_roundtrip(self) -> None:
        """Generate keypair, sign ResultEnvelope, verify with public bytes."""
        signing_key = ed25519.Ed25519PrivateKey.generate()
        agent_pubkey = signing_key.public_key().public_bytes_raw()

        env = _make_result()
        sign_result(env, signing_key)

        assert verify_result(env, agent_pubkey) is True

    def test_verify_rejects_tampered_payload(self) -> None:
        """Verify should reject if exit_code was mutated after signing."""
        signing_key = ed25519.Ed25519PrivateKey.generate()
        agent_pubkey = signing_key.public_key().public_bytes_raw()

        env = _make_result(exit_code=0)
        sign_result(env, signing_key)

        # Tamper with payload
        env.exit_code = 1

        assert verify_result(env, agent_pubkey) is False

    def test_verify_rejects_wrong_pubkey(self) -> None:
        """Verify should reject if signed with a different key."""
        signing_key_a = ed25519.Ed25519PrivateKey.generate()
        signing_key_b = ed25519.Ed25519PrivateKey.generate()
        pubkey_b = signing_key_b.public_key().public_bytes_raw()

        env = _make_result()
        sign_result(env, signing_key_a)

        # Verify with wrong pubkey
        assert verify_result(env, pubkey_b) is False

    def test_verify_rejects_empty_signature(self) -> None:
        """Verify should reject if env has no signature."""
        signing_key = ed25519.Ed25519PrivateKey.generate()
        agent_pubkey = signing_key.public_key().public_bytes_raw()

        env = _make_result()
        # Don't sign; signature is empty

        assert verify_result(env, agent_pubkey) is False

    def test_verify_rejects_short_pubkey(self) -> None:
        """Verify should reject if agent_pubkey length != 32."""
        env = _make_result()
        signing_key = ed25519.Ed25519PrivateKey.generate()
        sign_result(env, signing_key)

        # Pass a short pubkey
        assert verify_result(env, b"short") is False

    def test_verify_rejects_wrong_signature(self) -> None:
        """Verify should reject if signature is tampered."""
        signing_key = ed25519.Ed25519PrivateKey.generate()
        agent_pubkey = signing_key.public_key().public_bytes_raw()

        env = _make_result()
        sign_result(env, signing_key)

        # Tamper with signature
        env.signature = b"x" * 64

        assert verify_result(env, agent_pubkey) is False
