"""Biscuit capability token issuance and verification."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from biscuit_auth import (
    KeyPair,
    PrivateKey,
    PublicKey,
    BiscuitBuilder,
    Biscuit,
    AuthorizerBuilder,
    Rule,
)


class CapabilityError(Exception):
    """Base exception for capability errors."""


class CapabilityExpiredError(CapabilityError):
    """Token has expired."""


class CapabilityScopeError(CapabilityError):
    """Token scope (host, action, resource) does not match expected."""


class CapabilitySignatureError(CapabilityError):
    """Token signature is invalid or issuer is not trusted."""


@dataclass(frozen=True)
class CapabilityClaims:
    """Parsed capability token claims."""

    host_id: str
    action: str  # e.g. "pkg.update", "reboot", "shell.exec"
    resource: str | None  # optional resource id
    issued_at: datetime
    expires_at: datetime
    issuer: str  # user id or service id


class CapabilityIssuer:
    """Issues biscuit-auth tokens; holds Ed25519 private key."""

    def __init__(self, private_key: PrivateKey) -> None:
        """Initialize issuer with a private key."""
        self._private_key = private_key
        # Derive public key from private key via KeyPair
        kp = KeyPair.from_private_key(private_key)
        self._public_key = kp.public_key

    @classmethod
    def generate(cls) -> CapabilityIssuer:
        """Generate a new issuer with random Ed25519 keypair."""
        kp = KeyPair()
        return cls(kp.private_key)

    @property
    def public_key(self) -> PublicKey:
        """Get the public key for verification."""
        return self._public_key

    def issue(self, claims: CapabilityClaims) -> bytes:
        """Issue a capability token with the given claims.

        Uses parameterized datalog to prevent injection attacks.
        Returns bytes (utf-8 encoded base64 string).
        """
        # Format datetimes to RFC3339 with Z suffix
        issued_at_str = claims.issued_at.isoformat().replace("+00:00", "Z")
        expires_at_str = claims.expires_at.isoformat().replace("+00:00", "Z")

        # Build datalog facts using parameterized API to prevent injection
        # Parameters are safely escaped by the biscuit library
        datalog_source = (
            "host({host_id}); "
            "action({action}); "
            "issued_at({issued_at}); "
            "expires_at({expires_at}); "
            "issuer({issuer})"
        )
        if claims.resource is not None:
            datalog_source = (
                "host({host_id}); "
                "action({action}); "
                "resource({resource}); "
                "issued_at({issued_at}); "
                "expires_at({expires_at}); "
                "issuer({issuer})"
            )

        params = {
            "host_id": claims.host_id,
            "action": claims.action,
            "issued_at": issued_at_str,
            "expires_at": expires_at_str,
            "issuer": claims.issuer,
        }
        if claims.resource is not None:
            params["resource"] = claims.resource

        builder = BiscuitBuilder(datalog_source, parameters=params)
        biscuit = builder.build(self._private_key)

        # Return as bytes (utf-8 of base64)
        return biscuit.to_base64().encode("utf-8")


class CapabilityVerifier:
    """Verifies tokens against trust anchors (list of PublicKey)."""

    def __init__(self, trust_anchors: list[PublicKey]) -> None:
        """Initialize verifier with list of trusted public keys."""
        self._trust_anchors = trust_anchors

    def verify(
        self,
        token: bytes,
        *,
        expected_host: str,
        expected_action: str,
        expected_resource: str | None = None,
        now: datetime | None = None,
    ) -> CapabilityClaims:
        """Verify signature + scope + expiry. Returns parsed claims.

        Raises CapabilitySignatureError on bad sig / wrong issuer.
        Raises CapabilityExpiredError when expires_at <= now.
        Raises CapabilityScopeError when host/action/resource mismatch.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # Decode token from bytes to base64 string
        try:
            token_str = token.decode("utf-8")
        except UnicodeDecodeError as e:
            raise CapabilitySignatureError(f"Invalid token encoding: {e}")

        # Try to load from base64 with each trust anchor
        biscuit = None
        for anchor in self._trust_anchors:
            try:
                biscuit = Biscuit.from_base64(token_str, anchor)
                break
            except Exception:
                # This anchor didn't work, try next
                continue

        if biscuit is None:
            raise CapabilitySignatureError("No trusted issuer could verify this token")

        # Extract claims using a query
        # Query pattern depends on whether resource is in the token
        # We'll query with optional resource
        authorizer = AuthorizerBuilder("allow if true;").build(biscuit)

        # Try query with resource included
        rule_with_resource = Rule(
            'data($h, $a, $r, $ia, $e, $i) <- host($h), action($a), resource($r), issued_at($ia), expires_at($e), issuer($i)'
        )
        try:
            result = authorizer.query(rule_with_resource)
            if result:
                host_id, action, resource, issued_at_str, expires_at_str, issuer = result[
                    0
                ].terms
            else:
                raise ValueError("Query returned no results")
        except Exception:
            # Try without resource
            rule_no_resource = Rule(
                'data($h, $a, $ia, $e, $i) <- host($h), action($a), issued_at($ia), expires_at($e), issuer($i)'
            )
            try:
                result = authorizer.query(rule_no_resource)
                if result:
                    host_id, action, issued_at_str, expires_at_str, issuer = result[
                        0
                    ].terms
                    resource = None
                else:
                    raise CapabilitySignatureError(
                        "Could not extract claims from token"
                    )
            except CapabilitySignatureError:
                # Re-raise our own errors
                raise
            except Exception as e:
                # Catch any other exception and convert to CapabilitySignatureError
                raise CapabilitySignatureError(
                    f"Could not extract claims from token: {e}"
                )

        # Parse datetime strings
        # ISO format like "2026-05-02T18:00:00Z"
        issued_at = datetime.fromisoformat(issued_at_str.replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))

        # Check expiry
        if expires_at <= now:
            raise CapabilityExpiredError(f"Token expired at {expires_at}")

        # Check scope
        if host_id != expected_host:
            raise CapabilityScopeError(
                f"Host mismatch: expected {expected_host}, got {host_id}"
            )
        if action != expected_action:
            raise CapabilityScopeError(
                f"Action mismatch: expected {expected_action}, got {action}"
            )

        # Check resource
        if expected_resource is not None and resource != expected_resource:
            raise CapabilityScopeError(
                f"Resource mismatch: expected {expected_resource}, got {resource}"
            )
        if expected_resource is None and resource is not None:
            raise CapabilityScopeError(
                f"Resource mismatch: expected None, got {resource}"
            )

        return CapabilityClaims(
            host_id=host_id,
            action=action,
            resource=resource,
            issued_at=issued_at,
            expires_at=expires_at,
            issuer=issuer,
        )
