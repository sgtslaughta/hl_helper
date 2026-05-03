"""MFA verification — interim stub implementation.

Real WebAuthn verification lands in C4.
This is structural validation only: proofs must match a specific format,
and the HMAC is validated against a stub secret derived from principal_id.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Protocol


class MfaVerifier(Protocol):
    """Protocol for MFA proof verification."""

    def verify(self, principal_id: str, proof: str, challenge_id: str) -> bool:
        """Verify an MFA proof.

        Args:
            principal_id: The principal (user) ID that generated the proof.
            proof: The MFA proof string to validate.
            challenge_id: The challenge ID associated with the proof.

        Returns:
            True if the proof is valid, False otherwise.
        """
        ...


class StubMfaVerifier:
    """Interim MFA verifier for structural validation only.

    Proofs must match: mfa_v1:<challenge_id>:<timestamp>:<hmac>
    The HMAC is validated against a stub secret derived from principal_id.

    Real WebAuthn/TOTP verification lands in C4.
    """

    # Regex: mfa_v1:<challenge_id>:<timestamp>:<hmac>
    PROOF_PATTERN = re.compile(r"^mfa_v1:([A-Za-z0-9_-]+):(\d+):([A-Za-z0-9_-]+)$")

    def verify(self, principal_id: str, proof: str, challenge_id: str) -> bool:
        """Verify a proof.

        Args:
            principal_id: The principal ID.
            proof: The proof string (format: mfa_v1:<cid>:<ts>:<hmac>).
            challenge_id: Expected challenge ID.

        Returns:
            True if shape is correct and HMAC validates.
        """
        match = self.PROOF_PATTERN.match(proof)
        if not match:
            return False

        proof_challenge_id, timestamp_str, proof_hmac = match.groups()

        # Check challenge_id matches
        if proof_challenge_id != challenge_id:
            return False

        # Validate timestamp is numeric (structural only)
        try:
            int(timestamp_str)
        except ValueError:
            return False

        # Validate HMAC: derive stub secret from principal_id
        stub_secret = self._derive_stub_secret(principal_id)

        # HMAC is computed over: mfa_v1:<challenge_id>:<timestamp>
        message = f"mfa_v1:{proof_challenge_id}:{timestamp_str}"
        expected_hmac = self._compute_hmac(stub_secret, message)

        # Use constant-time comparison
        return hmac.compare_digest(proof_hmac, expected_hmac)

    @staticmethod
    def _derive_stub_secret(principal_id: str) -> str:
        """Derive a stub secret from principal_id.

        This is deterministic but not cryptographically secure.
        Real secrets come from secure storage in C4.
        """
        # Hash principal_id to create a deterministic "secret"
        digest = hashlib.sha256(principal_id.encode()).hexdigest()[:32]
        return digest

    @staticmethod
    def _compute_hmac(secret: str, message: str) -> str:
        """Compute HMAC-SHA256 and return base64url-like encoding."""
        h = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256,
        )
        # Simple base64url-ish: use hex for simplicity (structural validation only)
        return h.hexdigest()[:32]
