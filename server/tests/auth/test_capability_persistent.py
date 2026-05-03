"""Tests for persistent CapabilityIssuer key storage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


from server.app.auth.capability import (
    CapabilityIssuer,
    CapabilityVerifier,
    CapabilityClaims,
)


class TestCapabilityKeyPersistence:
    """Test that CapabilityIssuer key is persisted to disk and reloaded."""

    def test_load_or_generate_creates_key_on_first_call(self) -> None:
        """load_or_generate creates a new key on first call."""
        with TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "capability.key"

            issuer = CapabilityIssuer.load_or_generate(key_path)

            assert issuer is not None
            assert key_path.exists()

    def test_load_or_generate_reloads_key_on_second_call(self) -> None:
        """load_or_generate loads existing key on subsequent calls."""
        with TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "capability.key"

            # First call: generate
            issuer1 = CapabilityIssuer.load_or_generate(key_path)
            pub_key1 = issuer1.public_key

            # Second call: load (different instance, same key)
            issuer2 = CapabilityIssuer.load_or_generate(key_path)
            pub_key2 = issuer2.public_key

            # Public keys should be identical (same private key)
            assert pub_key1.to_bytes() == pub_key2.to_bytes()

    def test_tokens_issued_by_one_issuer_verify_under_reloaded_issuer(self) -> None:
        """Token issued by issuer1 verifies under issuer2 (loaded from same key file)."""
        with TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "capability.key"

            # Create issuer, issue token
            issuer1 = CapabilityIssuer.load_or_generate(key_path)
            now = datetime.now(timezone.utc)
            claims = CapabilityClaims(
                host_id="h1",
                action="pkg.update",
                resource=None,
                issued_at=now,
                expires_at=now + timedelta(minutes=5),
                issuer="admin",
            )
            token = issuer1.issue(claims)

            # Load a new issuer from the same key file (simulating process restart)
            issuer2 = CapabilityIssuer.load_or_generate(key_path)
            verifier = CapabilityVerifier([issuer2.public_key])

            # Verify the token issued by issuer1 with issuer2's public key
            result = verifier.verify(
                token,
                expected_host="h1",
                expected_action="pkg.update",
            )

            assert result.host_id == "h1"
            assert result.action == "pkg.update"

    def test_key_file_has_restrictive_permissions(self) -> None:
        """Key file is created with 0o600 (readable/writable by owner only)."""
        import os

        with TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "capability.key"

            CapabilityIssuer.load_or_generate(key_path)

            # Check file permissions
            stat_info = os.stat(key_path)
            mode = stat_info.st_mode & 0o777

            # Should be 0o600 (owner read+write)
            assert mode == 0o600

    def test_load_or_generate_with_parent_directory_creation(self) -> None:
        """load_or_generate creates parent directories if needed."""
        with TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "keys" / "subdir" / "capability.key"

            issuer = CapabilityIssuer.load_or_generate(key_path)

            assert issuer is not None
            assert key_path.exists()
            assert key_path.parent.exists()

    def test_multiple_issuers_with_different_paths_have_different_keys(self) -> None:
        """Two issuers from different key files have different keys."""
        with TemporaryDirectory() as tmpdir:
            path1 = Path(tmpdir) / "key1.pem"
            path2 = Path(tmpdir) / "key2.pem"

            issuer1 = CapabilityIssuer.load_or_generate(path1)
            issuer2 = CapabilityIssuer.load_or_generate(path2)

            # Public keys should be different
            assert issuer1.public_key.to_bytes() != issuer2.public_key.to_bytes()
