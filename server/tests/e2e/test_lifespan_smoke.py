"""End-to-end smoke test: lifespan, enroll, revoke."""

from __future__ import annotations

import base64
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from server.app.api.app import create_app
from server.app.models.host import Host


def make_csr() -> tuple[bytes, bytes]:
    """Build a fresh Ed25519 keypair + CSR. Returns (csr_pem, pubkey_raw)."""
    sk = ed25519.Ed25519PrivateKey.generate()
    pk_raw = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "agent")]))
        .sign(sk, None)  # Ed25519 doesn't need hash algorithm
    )
    return csr.public_bytes(serialization.Encoding.PEM), pk_raw


@pytest.mark.asyncio
async def test_lifespan_enroll_revoke_smoke(tmp_path: Path, monkeypatch) -> None:
    """Smoke test: start app, issue token, enroll, revoke, verify."""
    # Set FLEET_DATA_DIR to tmp_path
    monkeypatch.setenv("FLEET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "FLEET_DB_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'fleet.db'}",
    )
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", "test-admin-token-123")

    app = create_app()

    # Manually trigger the lifespan startup
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            # Get app state from the lifespan
            state = app.state.app_state

            # Issue enrollment token
            async with state.sessionmaker() as session:
                plaintext, _ = await state.enrollment_service.issue_token(
                    session,
                    issued_by="smoke-test",
                    ttl=timedelta(minutes=15),
                )
                await session.commit()

            # Prepare enrollment request
            csr_pem, agent_pubkey = make_csr()
            agent_pubkey_b64 = base64.b64encode(agent_pubkey).decode("ascii")

            # Enroll
            response = await client.post(
                "/v1/enroll",
                json={
                    "token": plaintext,
                    "hostname": "test-host-1",
                    "csr_pem": csr_pem.decode("utf-8"),
                    "agent_pubkey_b64": agent_pubkey_b64,
                },
            )
            assert response.status_code == 200
            enroll_data = response.json()
            assert "host_id" in enroll_data
            host_id = enroll_data["host_id"]

            # Verify host was created
            async with state.sessionmaker() as session:
                host = await session.get(Host, host_id)
                assert host is not None
                assert host.hostname == "test-host-1"
                assert host.status == "offline"

            # Revoke with admin token
            response = await client.delete(
                f"/v1/hosts/{host_id}",
                headers={"Authorization": "Bearer test-admin-token-123"},
            )
            assert response.status_code == 204

            # Verify host is revoked
            async with state.sessionmaker() as session:
                host = await session.get(Host, host_id)
                assert host is not None
                assert host.status == "revoked"
