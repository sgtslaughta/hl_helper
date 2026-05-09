"""Integration test: cert_rotate arm of AgentToServer."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_agent_bridge_handles_cert_rotate(
    sm, fake_ca, agent_bridge_servicer
):
    """recv_loop dispatches cert_rotate to orchestrator and pushes cert_issue."""
    # Setup: enroll host with known serial in DB
    from server.app.models.host import Host

    async with sm() as s:
        s.add(
            Host(
                id="h-1",
                hostname="h1",
                agent_pubkey=b"\x00" * 32,
                cert_serial="OLDSERIAL",
            )
        )
        await s.commit()

    # Drive a CertRotateRequest through the bridge mock context
    sent_responses: list = []
    bridge = agent_bridge_servicer  # configured fixture w/ orchestrator
    await bridge.handle_cert_rotate_for_test(
        host_id="h-1",
        csr_pem=_build_test_csr("h-1"),
        signing_pubkey=b"\x00" * 32,
        prev_serial="OLDSERIAL",
        peer_ip="127.0.0.1",
        push=lambda msg: sent_responses.append(msg),
    )

    assert len(sent_responses) == 1
    assert sent_responses[0].WhichOneof("msg") == "cert_issue"
    assert sent_responses[0].cert_issue.cert_chain_pem


def _build_test_csr(cn: str) -> bytes:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        )
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM)
