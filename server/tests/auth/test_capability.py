"""Tests for biscuit capability token issuance and verification."""
import pytest
from datetime import datetime, timezone, timedelta
from server.app.auth.capability import (
    CapabilityIssuer,
    CapabilityVerifier,
    CapabilityClaims,
    CapabilityExpiredError,
    CapabilityScopeError,
    CapabilitySignatureError,
)


class TestCapabilityRoundtrip:
    """Test issuance and verification roundtrip."""

    def test_issue_then_verify_roundtrip(self):
        """Issue a token and verify it with correct scope."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)
        claims = CapabilityClaims(
            host_id="h1",
            action="pkg.update",
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        token = issuer.issue(claims)
        verifier = CapabilityVerifier([issuer.public_key])

        result = verifier.verify(
            token,
            expected_host="h1",
            expected_action="pkg.update",
        )

        assert result.host_id == "h1"
        assert result.action == "pkg.update"
        assert result.issuer == "admin"

    def test_verify_returns_correct_claims(self):
        """Verify returns all claim fields correctly."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=10)
        claims = CapabilityClaims(
            host_id="host-abc",
            action="shell.exec",
            resource="script-123",
            issued_at=now,
            expires_at=expires,
            issuer="system",
        )

        token = issuer.issue(claims)
        verifier = CapabilityVerifier([issuer.public_key])

        result = verifier.verify(
            token,
            expected_host="host-abc",
            expected_action="shell.exec",
            expected_resource="script-123",
        )

        assert result.host_id == "host-abc"
        assert result.action == "shell.exec"
        assert result.resource == "script-123"
        assert result.issuer == "system"
        # Check expiry is approximately correct (within 1 second)
        assert abs((result.expires_at - expires).total_seconds()) < 1


class TestCapabilitySignatureVerification:
    """Test signature verification."""

    def test_verify_rejects_wrong_anchor(self):
        """Reject token signed with different key."""
        issuer_a = CapabilityIssuer.generate()
        issuer_b = CapabilityIssuer.generate()

        now = datetime.now(timezone.utc)
        claims = CapabilityClaims(
            host_id="h1",
            action="reboot",
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        token = issuer_a.issue(claims)
        # Verifier has only issuer_b's key
        verifier = CapabilityVerifier([issuer_b.public_key])

        with pytest.raises(CapabilitySignatureError):
            verifier.verify(
                token,
                expected_host="h1",
                expected_action="reboot",
            )

    def test_verify_rejects_tampered_token(self):
        """Reject a token that has been tampered with."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)
        claims = CapabilityClaims(
            host_id="h1",
            action="pkg.update",
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        token = issuer.issue(claims)
        # Tamper: flip a byte in the middle
        token_list = bytearray(token)
        token_list[len(token_list) // 2] ^= 0xFF
        tampered = bytes(token_list)

        verifier = CapabilityVerifier([issuer.public_key])
        with pytest.raises(CapabilitySignatureError):
            verifier.verify(
                tampered,
                expected_host="h1",
                expected_action="pkg.update",
            )


class TestCapabilityExpiry:
    """Test expiry validation."""

    def test_verify_rejects_expired(self):
        """Reject a token that has expired."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)
        # Token expired 1 second ago
        claims = CapabilityClaims(
            host_id="h1",
            action="pkg.update",
            resource=None,
            issued_at=now - timedelta(minutes=5),
            expires_at=now - timedelta(seconds=1),
            issuer="admin",
        )

        token = issuer.issue(claims)
        verifier = CapabilityVerifier([issuer.public_key])

        with pytest.raises(CapabilityExpiredError):
            verifier.verify(
                token,
                expected_host="h1",
                expected_action="pkg.update",
                now=now,
            )


class TestCapabilityScopeVerification:
    """Test scope validation."""

    def test_verify_rejects_wrong_host(self):
        """Reject when host doesn't match."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)
        claims = CapabilityClaims(
            host_id="h1",
            action="pkg.update",
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        token = issuer.issue(claims)
        verifier = CapabilityVerifier([issuer.public_key])

        with pytest.raises(CapabilityScopeError):
            verifier.verify(
                token,
                expected_host="h2",
                expected_action="pkg.update",
            )

    def test_verify_rejects_wrong_action(self):
        """Reject when action doesn't match."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)
        claims = CapabilityClaims(
            host_id="h1",
            action="pkg.update",
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        token = issuer.issue(claims)
        verifier = CapabilityVerifier([issuer.public_key])

        with pytest.raises(CapabilityScopeError):
            verifier.verify(
                token,
                expected_host="h1",
                expected_action="reboot",
            )

    def test_verify_resource_match(self):
        """Accept/reject based on resource match."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)
        claims = CapabilityClaims(
            host_id="h1",
            action="update",
            resource="pkg:openssh-server",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        token = issuer.issue(claims)
        verifier = CapabilityVerifier([issuer.public_key])

        # Accept with matching resource
        result = verifier.verify(
            token,
            expected_host="h1",
            expected_action="update",
            expected_resource="pkg:openssh-server",
        )
        assert result.resource == "pkg:openssh-server"

        # Reject with different resource
        with pytest.raises(CapabilityScopeError):
            verifier.verify(
                token,
                expected_host="h1",
                expected_action="update",
                expected_resource="pkg:curl",
            )

    def test_verify_no_resource_when_none(self):
        """Accept resource=None when token has no resource."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)
        claims = CapabilityClaims(
            host_id="h1",
            action="reboot",
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        token = issuer.issue(claims)
        verifier = CapabilityVerifier([issuer.public_key])

        result = verifier.verify(
            token,
            expected_host="h1",
            expected_action="reboot",
            expected_resource=None,
        )
        assert result.resource is None

    def test_verify_rejects_when_resource_expected_but_token_lacks_it(self):
        """Reject when resource is expected but token has none."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)
        claims = CapabilityClaims(
            host_id="h1",
            action="update",
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        token = issuer.issue(claims)
        verifier = CapabilityVerifier([issuer.public_key])

        with pytest.raises(CapabilityScopeError):
            verifier.verify(
                token,
                expected_host="h1",
                expected_action="update",
                expected_resource="pkg:x",
            )


class TestCapabilityTrustAnchors:
    """Test multiple trust anchors (key rotation scenario)."""

    def test_verify_accepts_with_multiple_anchors(self):
        """Accept token from any trusted anchor."""
        issuer_a = CapabilityIssuer.generate()
        issuer_b = CapabilityIssuer.generate()
        issuer_c = CapabilityIssuer.generate()

        now = datetime.now(timezone.utc)
        claims = CapabilityClaims(
            host_id="h1",
            action="pkg.update",
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        token = issuer_b.issue(claims)

        # Verifier has anchors for A, B, C
        verifier = CapabilityVerifier(
            [issuer_a.public_key, issuer_b.public_key, issuer_c.public_key]
        )

        result = verifier.verify(
            token,
            expected_host="h1",
            expected_action="pkg.update",
        )
        assert result.host_id == "h1"


class TestCapabilityMalformedTokens:
    """Test rejection of malformed and truncated tokens."""

    def test_verify_rejects_malformed_base64(self):
        """Reject token that is not valid base64."""
        issuer = CapabilityIssuer.generate()
        verifier = CapabilityVerifier([issuer.public_key])

        with pytest.raises(CapabilitySignatureError):
            verifier.verify(
                b"!!!not-base64!!!",
                expected_host="h1",
                expected_action="pkg.update",
            )

    def test_verify_rejects_truncated_token(self):
        """Reject token with last 5 bytes of base64 string removed."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)
        claims = CapabilityClaims(
            host_id="h1",
            action="pkg.update",
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        token = issuer.issue(claims)
        # Truncate by removing last 5 bytes
        truncated = token[:-5]

        verifier = CapabilityVerifier([issuer.public_key])
        with pytest.raises(CapabilitySignatureError):
            verifier.verify(
                truncated,
                expected_host="h1",
                expected_action="pkg.update",
            )

    def test_verify_rejects_empty_token(self):
        """Reject empty token."""
        issuer = CapabilityIssuer.generate()
        verifier = CapabilityVerifier([issuer.public_key])

        with pytest.raises(CapabilitySignatureError):
            verifier.verify(
                b"",
                expected_host="h1",
                expected_action="pkg.update",
            )


class TestCapabilityDatalogInjection:
    """Test protection against datalog injection attacks."""

    def test_issue_with_malicious_host_id_injection(self):
        """Reject or safely handle malicious host_id that attempts datalog injection."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)

        # Attacker tries to inject datalog rule via host_id
        malicious_claims = CapabilityClaims(
            host_id='h1"); allow if true; //',
            action="pkg.update",
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        # Either validation rejects the input at issuance, or the parameterized
        # datalog API treats the string as a literal value (no injected rule).
        # In the parameterized case, verifying with a *different* host_id must
        # still fail — proving the injected `allow if true` was not honored.
        try:
            token = issuer.issue(malicious_claims)
            verifier = CapabilityVerifier([issuer.public_key])

            # Verify with a different host should fail — injection not honored
            with pytest.raises(CapabilityScopeError):
                verifier.verify(
                    token,
                    expected_host="not-h1",
                    expected_action="pkg.update",
                )
        except ValueError as e:
            # If validation is done at issuance, ValueError is also acceptable
            assert "injection" in str(e).lower() or "invalid" in str(e).lower()

    def test_issue_with_malicious_action_injection(self):
        """Reject or safely handle malicious action that attempts datalog injection."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)

        malicious_claims = CapabilityClaims(
            host_id="h1",
            action='pkg.update"); allow if true; //',
            resource=None,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin",
        )

        try:
            token = issuer.issue(malicious_claims)
            verifier = CapabilityVerifier([issuer.public_key])

            with pytest.raises(CapabilityScopeError):
                verifier.verify(
                    token,
                    expected_host="h1",
                    expected_action="not-pkg.update",
                )
        except ValueError as e:
            assert "injection" in str(e).lower() or "invalid" in str(e).lower()

    def test_issue_roundtrip_legitimate_values_still_works(self):
        """Verify legitimate input still works correctly after injection protection."""
        issuer = CapabilityIssuer.generate()
        now = datetime.now(timezone.utc)

        # Legitimate values that might look unusual but are safe
        claims = CapabilityClaims(
            host_id="host-123_abc:def",
            action="pkg.update.security",
            resource="pkg:openssl-1.1.1",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            issuer="admin-user",
        )

        token = issuer.issue(claims)
        verifier = CapabilityVerifier([issuer.public_key])

        result = verifier.verify(
            token,
            expected_host="host-123_abc:def",
            expected_action="pkg.update.security",
            expected_resource="pkg:openssl-1.1.1",
        )

        assert result.host_id == "host-123_abc:def"
        assert result.action == "pkg.update.security"
        assert result.resource == "pkg:openssl-1.1.1"
