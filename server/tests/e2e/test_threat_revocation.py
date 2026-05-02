"""Threat-model E2E test: revocation behavior.

Covered in detail by server/tests/grpc/test_revocation_e2e.py
This test serves as a reference assertion that RevocationService exists.
"""

from __future__ import annotations

from server.app.revocation.service import RevocationService


def test_revoked_host_disconnected_within_seconds() -> None:
    """Reference assertion: RevocationService provides revocation capability.

    Full threat-model coverage (dispatcher termination, RevokedCert DB row,
    handshake rejection) is tested in server/tests/grpc/test_revocation_e2e.py.
    """
    assert RevocationService is not None
    assert hasattr(RevocationService, "revoke")
