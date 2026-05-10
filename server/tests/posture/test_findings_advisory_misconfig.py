"""Tests for advisory and misconfig findings modules."""

from __future__ import annotations

from uuid import uuid4
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.models.host import Host
from server.app.models.advisory import Advisory
from server.app.models.host_advisory import HostAdvisory
from server.app.posture.findings_advisory import collect_advisory_findings
from server.app.posture.findings_misconfig import collect_misconfig_findings


@pytest.mark.asyncio
async def test_collect_advisory_findings_groups_by_host(sm: async_sessionmaker) -> None:
    """collect_advisory_findings emits one Finding per host with open advisories."""
    host_id_1 = str(uuid4())
    host_id_2 = str(uuid4())

    # Create 2 hosts
    async with sm() as session:
        h1 = Host(
            id=host_id_1,
            hostname="host1",
            agent_pubkey=b"\x00" * 32,
            agent_version="0.4.0",
        )
        h2 = Host(
            id=host_id_2,
            hostname="host2",
            agent_pubkey=b"\x00" * 32,
            agent_version="0.4.0",
        )
        session.add_all([h1, h2])
        await session.commit()

    # Create advisory
    async with sm() as session:
        adv = Advisory(
            id="CVE-2024-7777",
            summary="Critical vulnerability",
            severity="critical",
        )
        session.add(adv)
        await session.commit()

    # Create host advisories for both hosts with critical severity
    async with sm() as session:
        ha1 = HostAdvisory(
            host_id=host_id_1,
            advisory_id="CVE-2024-7777",
            package="curl",
            ecosystem="system",
            current_version="1.0",
            fixed_version="2.0",
            status="open",
        )
        ha2 = HostAdvisory(
            host_id=host_id_2,
            advisory_id="CVE-2024-7777",
            package="curl",
            ecosystem="system",
            current_version="1.0",
            fixed_version="2.0",
            status="open",
        )
        session.add_all([ha1, ha2])
        await session.commit()

    # Call collect_advisory_findings
    findings = await collect_advisory_findings(sm)

    # Should have 2 findings, one per host
    assert len(findings) == 2
    host_ids = {f.subject_id for f in findings}
    assert host_id_1 in host_ids
    assert host_id_2 in host_ids
    # All should be critical
    for f in findings:
        assert f.severity == "critical"


@pytest.mark.asyncio
async def test_collect_misconfig_findings_root_login(sm: async_sessionmaker) -> None:
    """collect_misconfig_findings emits Finding when sshd permitrootlogin is 'yes'."""
    host_id = str(uuid4())

    # Create host with survey facts
    async with sm() as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=b"\x00" * 32,
            agent_version="0.4.0",
            survey={
                "facts": {
                    "sshd": {
                        "permitrootlogin": "yes"
                    }
                }
            }
        )
        session.add(host)
        await session.commit()

    # Call collect_misconfig_findings
    findings = await collect_misconfig_findings(sm)

    # Should have at least 1 finding about root login
    assert len(findings) >= 1
    root_login_findings = [f for f in findings if "Root SSH" in f.title or "root login" in f.title.lower()]
    assert len(root_login_findings) >= 1
    assert root_login_findings[0].subject_kind == "host"
    assert root_login_findings[0].subject_id == host_id
    assert root_login_findings[0].severity == "high"
