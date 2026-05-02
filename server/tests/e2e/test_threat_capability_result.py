"""Phase 8 threat-model tests: capability scope violation + forged result rejection."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from server.app.auth.capability import (
    CapabilityIssuer,
    CapabilityVerifier,
    CapabilityClaims,
    CapabilityScopeError,
)
from server.app.crypto.result_envelope import sign_result
from server.app.crypto.signing import FileBackend
from server.app.db.session import session_scope
from server.app.grpc._pb.fleet.v1 import results_pb2
from server.app.grpc.result_handler import BadSignatureError, ResultHandler
from server.app.models import Host
from server.app.audit.sql_chain import SqlAuditChain


def test_capability_outside_manifest_denied():
    """Issue capability for host_id=host-A, pkg.update; verify for power.reboot → CapabilityScopeError."""
    issuer = CapabilityIssuer.generate()
    now = datetime.now(timezone.utc)

    # Issue token for pkg.update on host-A
    claims = CapabilityClaims(
        host_id="host-A",
        action="pkg.update",
        resource=None,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        issuer="admin",
    )
    token = issuer.issue(claims)

    # Try to verify for power.reboot action
    verifier = CapabilityVerifier([issuer.public_key])
    with pytest.raises(CapabilityScopeError):
        verifier.verify(
            token,
            expected_host="host-A",
            expected_action="power.reboot",
        )


@pytest.mark.asyncio
async def test_forged_result_wrong_host_key_rejected(
    sm, tmp_path
) -> None:
    """Build ResultEnvelope, sign with wrong Ed25519 key, pass through ResultHandler → BadSignatureError."""
    # Setup
    backend = FileBackend.bootstrap(tmp_path / "audit")
    audit_chain = SqlAuditChain(backend)
    handler = ResultHandler(sm, audit_chain)

    # Host registered with key_a
    key_a = ed25519.Ed25519PrivateKey.generate()
    pubkey_a = key_a.public_key().public_bytes_raw()
    host_id = "host-A"

    async with session_scope(sm) as session:
        host = Host(id=host_id, hostname="test-host", agent_pubkey=pubkey_a)
        session.add(host)
        await session.commit()

    # Build result signed with different key_b (forged)
    key_b = ed25519.Ed25519PrivateKey.generate()
    env = results_pb2.ResultEnvelope()
    env.command_id = "cmd-1"
    env.host_id = host_id
    env.sequence = 1
    env.exit_code = 0
    env.status = results_pb2.RESULT_OK
    env.final = True
    env.prev_result_hash = b"\x00" * 32
    env = sign_result(env, key_b)

    # Pass through handler with wrong signature
    with pytest.raises(BadSignatureError):
        await handler.handle(env, expected_host_id=host_id)

    # Verify audit entry was emitted
    async with session_scope(sm) as session:
        from server.app.models import AuditEntry  # type: ignore
        from sqlalchemy import select
        rows = (await session.execute(select(AuditEntry))).scalars().all()
        actions = [r.action for r in rows]
        assert any("bad_signature" in a or "BadSignature" in a or "reject" in a.lower() for a in actions), \
            f"expected audit entry for forged result; got {actions}"
