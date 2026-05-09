"""Tests for Advisory, AffectedPackage, HostPackage, HostAdvisory models."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.exc import IntegrityError

from server.app.models.advisory import Advisory, AffectedPackage
from server.app.models.host_package import HostPackage
from server.app.models.host_advisory import HostAdvisory
from server.app.models.host import Host


@pytest.mark.asyncio
async def test_advisory_insert_round_trip(sm: async_sessionmaker) -> None:
    """Insert Advisory + AffectedPackages, query back, assert fields."""
    async with sm() as session:
        # Create advisory
        advisory = Advisory(
            id="CVE-2024-1234",
            aliases=["GHSA-xxxx-yyyy-zzzz"],
            summary="Test vulnerability",
            description_md="# Details\nThis is a test",
            severity="high",
            cvss_v3="7.5",
            cvss_v4="8.0",
            epss=0.42,
            kev=True,
            published=datetime(2024, 1, 1),
            modified=datetime(2024, 1, 2),
            refs=["https://example.com"],
            sources=["nvd"],
        )
        session.add(advisory)

        # Create affected packages
        pkg1 = AffectedPackage(
            advisory_id="CVE-2024-1234",
            ecosystem="PyPI",
            package="requests",
            introduced="1.0.0",
            fixed="2.28.1",
            range_kind="SEMVER",
        )
        pkg2 = AffectedPackage(
            advisory_id="CVE-2024-1234",
            ecosystem="npm",
            package="lodash",
            introduced=None,
            fixed="4.17.21",
            range_kind="SEMVER",
        )
        session.add(pkg1)
        session.add(pkg2)

        await session.commit()

        # Query back
        stmt = select(Advisory).where(Advisory.id == "CVE-2024-1234")
        result = await session.execute(stmt)
        fetched_advisory = result.scalar_one()

        assert fetched_advisory.id == "CVE-2024-1234"
        assert fetched_advisory.summary == "Test vulnerability"
        assert fetched_advisory.severity == "high"
        assert fetched_advisory.kev is True
        assert fetched_advisory.epss == 0.42
        assert "GHSA-xxxx-yyyy-zzzz" in fetched_advisory.aliases

        # Query packages
        pkg_stmt = select(AffectedPackage).where(
            AffectedPackage.advisory_id == "CVE-2024-1234"
        )
        pkg_results = await session.execute(pkg_stmt)
        packages = pkg_results.scalars().all()
        assert len(packages) == 2
        assert any(p.package == "requests" for p in packages)
        assert any(p.package == "lodash" for p in packages)


@pytest.mark.asyncio
async def test_host_package_unique_constraint(sm: async_sessionmaker) -> None:
    """Inserting same (host_id, ecosystem, name) twice raises IntegrityError."""
    host_id = str(uuid4())
    async with sm() as session:
        # Create host first
        host = Host(
            id=host_id,
            hostname="test-host",
            display_name="test-host",
            agent_pubkey=b"\x00" * 32,
            labels={},
            agent_version="0.4.0",
        )
        session.add(host)
        await session.commit()

    async with sm() as session:
        # Insert first package
        pkg1 = HostPackage(
            host_id=host_id,
            ecosystem="PyPI",
            name="requests",
            version="2.28.0",
            source="pip",
            arch="x86_64",
        )
        session.add(pkg1)
        await session.commit()

        # Try to insert duplicate
        pkg2 = HostPackage(
            host_id=host_id,
            ecosystem="PyPI",
            name="requests",
            version="2.28.1",  # Different version, same (host, ecosystem, name)
            source="pip",
            arch="x86_64",
        )
        session.add(pkg2)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_host_advisory_status_default(sm: async_sessionmaker) -> None:
    """Insert minimal HostAdvisory; status defaults to 'open'."""
    host_id = str(uuid4())
    async with sm() as session:
        # Create host
        host = Host(
            id=host_id,
            hostname="test-host",
            display_name="test-host",
            agent_pubkey=b"\x00" * 32,
            labels={},
            agent_version="0.4.0",
        )
        session.add(host)

        # Create advisory
        advisory = Advisory(
            id="CVE-2024-9999",
            summary="Test",
            severity="medium",
        )
        session.add(advisory)
        await session.commit()

    async with sm() as session:
        # Insert HostAdvisory with minimal fields
        host_adv = HostAdvisory(
            host_id=host_id,
            advisory_id="CVE-2024-9999",
            package="test-pkg",
            ecosystem="PyPI",
            current_version="1.0.0",
        )
        session.add(host_adv)
        await session.commit()

        # Verify status is 'open'
        stmt = select(HostAdvisory).where(HostAdvisory.host_id == host_id)
        result = await session.execute(stmt)
        fetched = result.scalar_one()
        assert fetched.status == "open"
