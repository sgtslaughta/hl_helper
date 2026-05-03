"""Tests for SecretRef parser."""

from __future__ import annotations

import pytest

from server.app.secrets.ref import SecretRef


class TestSecretRefParser:
    """Tests for SecretRef URI parsing and roundtrip."""

    def test_parse_local_backend_simple(self) -> None:
        """Parse simple local backend reference."""
        ref = SecretRef.parse("secret://local/foo")
        assert ref.backend == "local"
        assert ref.path == "foo"
        assert ref.field is None

    def test_parse_vault_with_field(self) -> None:
        """Parse Vault reference with field selector."""
        ref = SecretRef.parse("secret://vault/kv/data/foo#password")
        assert ref.backend == "vault"
        assert ref.path == "kv/data/foo"
        assert ref.field == "password"

    def test_parse_bitwarden_with_field(self) -> None:
        """Parse Bitwarden reference with field selector."""
        ref = SecretRef.parse("secret://bitwarden/abc123#password")
        assert ref.backend == "bitwarden"
        assert ref.path == "abc123"
        assert ref.field == "password"

    def test_reject_missing_scheme(self) -> None:
        """Reject URI without secret:// scheme."""
        with pytest.raises(ValueError, match="scheme"):
            SecretRef.parse("local/foo")

    def test_reject_wrong_scheme(self) -> None:
        """Reject URI with wrong scheme."""
        with pytest.raises(ValueError, match="scheme"):
            SecretRef.parse("http://local/foo")

    def test_reject_missing_path(self) -> None:
        """Reject URI with missing path."""
        with pytest.raises(ValueError, match="path"):
            SecretRef.parse("secret://local/")

    def test_reject_missing_backend(self) -> None:
        """Reject URI with missing backend."""
        with pytest.raises(ValueError, match="backend"):
            SecretRef.parse("secret:///foo")

    def test_reject_not_uri(self) -> None:
        """Reject completely malformed input."""
        with pytest.raises(ValueError):
            SecretRef.parse("not-a-uri")

    def test_roundtrip_via_str(self) -> None:
        """String representation roundtrips via parse."""
        original = "secret://vault/kv/data/foo#password"
        ref = SecretRef.parse(original)
        assert str(ref) == original

    def test_roundtrip_simple_no_field(self) -> None:
        """Simple reference without field roundtrips."""
        original = "secret://local/my/secret/path"
        ref = SecretRef.parse(original)
        assert str(ref) == original

    def test_field_with_special_chars(self) -> None:
        """Field selector can contain alphanumerics and underscore."""
        ref = SecretRef.parse("secret://local/path#my_field_123")
        assert ref.field == "my_field_123"
        assert str(ref) == "secret://local/path#my_field_123"

    def test_reject_path_traversal_with_dotdot(self) -> None:
        """Reject paths containing .. segments."""
        with pytest.raises(ValueError, match="path traversal"):
            SecretRef.parse("secret://local/foo/../bar")

    def test_reject_path_traversal_percent_encoded(self) -> None:
        """Reject paths with percent-encoded traversal (%2e, %2f)."""
        with pytest.raises(ValueError, match="path traversal"):
            SecretRef.parse("secret://local/foo%2e%2ebar")

    def test_reject_path_with_double_slash(self) -> None:
        """Reject paths with empty segments (double slash)."""
        with pytest.raises(ValueError, match="path traversal"):
            SecretRef.parse("secret://local/foo//bar")

    def test_reject_path_starting_with_slash(self) -> None:
        """Reject paths starting with /."""
        with pytest.raises(ValueError, match="path traversal"):
            SecretRef.parse("secret://local//foo")

    def test_reject_path_dot_segment(self) -> None:
        """Reject paths containing single . segment."""
        with pytest.raises(ValueError, match="path traversal"):
            SecretRef.parse("secret://local/foo/./bar")
