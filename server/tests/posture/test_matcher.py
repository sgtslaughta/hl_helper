"""Tests for advisory matcher (joins host_packages × affected_packages)."""

from __future__ import annotations

from uuid import uuid4
import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.models.advisory import Advisory, AffectedPackage
from server.app.models.host import Host
from server.app.models.host_package import HostPackage
from server.app.models.host_advisory import HostAdvisory
from server.app.advisory.matcher import match_host, _in_range


@pytest.mark.asyncio
async def test_in_range_ecosystem_pypi() -> None:
    """_in_range with PyPI ecosystem and version comparisons."""
    # Happy path: current in range [introduced, fixed)
    assert _in_range("1.5.0", "1.0.0", "2.0.0", "PyPI") is True
    # Current equals introduced
    assert _in_range("1.0.0", "1.0.0", "2.0.0", "PyPI") is True
    # Current equals fixed (should be excluded)
    assert _in_range("2.0.0", "1.0.0", "2.0.0", "PyPI") is False
    # Current > fixed
    assert _in_range("3.0.0", "1.0.0", "2.0.0", "PyPI") is False
    # No fixed version, current > introduced
    assert _in_range("2.0.0", "1.0.0", None, "PyPI") is True
    # No introduced, current < fixed
    assert _in_range("1.0.0", None, "2.0.0", "PyPI") is True
    # No introduced, current >= fixed
    assert _in_range("2.0.0", None, "1.0.0", "PyPI") is False
    # Current < introduced
    assert _in_range("0.5.0", "1.0.0", "2.0.0", "PyPI") is False


@pytest.mark.asyncio
async def test_match_host_emits_host_advisory(sm: async_sessionmaker) -> None:
    """match_host creates HostAdvisory for matching vulnerable packages."""
    host_id = str(uuid4())

    # Create host
    async with sm() as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=b"\x00" * 32,
            agent_version="0.4.0",
        )
        session.add(host)
        await session.commit()

    # Create advisory + affected package
    async with sm() as session:
        advisory = Advisory(
            id="CVE-2024-1234",
            summary="Test vulnerability",
            severity="high",
        )
        session.add(advisory)

        affected = AffectedPackage(
            advisory_id="CVE-2024-1234",
            ecosystem="PyPI",
            package="requests",
            introduced="1.0.0",
            fixed="2.28.1",
            range_kind="SEMVER",
        )
        session.add(affected)
        await session.commit()

    # Create 2 host packages: 1 vulnerable, 1 safe
    async with sm() as session:
        # Vulnerable: 2.27.1 is in [1.0.0, 2.28.1)
        vuln_pkg = HostPackage(
            host_id=host_id,
            ecosystem="PyPI",
            name="requests",
            version="2.27.1",
        )
        session.add(vuln_pkg)

        # Safe: 2.28.1+ is fixed
        safe_pkg = HostPackage(
            host_id=host_id,
            ecosystem="PyPI",
            name="urllib3",
            version="1.26.0",
        )
        session.add(safe_pkg)
        await session.commit()

    # Run matcher
    count = await match_host(sm, host_id)

    # Assert 1 HostAdvisory created
    assert count == 1

    async with sm() as session:
        from sqlalchemy import select
        stmt = select(HostAdvisory).where(HostAdvisory.host_id == host_id)
        result = await session.execute(stmt)
        advisories = result.scalars().all()
        assert len(advisories) == 1
        assert advisories[0].advisory_id == "CVE-2024-1234"
        assert advisories[0].package == "requests"
        assert advisories[0].current_version == "2.27.1"
        assert advisories[0].fixed_version == "2.28.1"


@pytest.mark.asyncio
async def test_match_host_preserves_suppression(sm: async_sessionmaker) -> None:
    """Re-running match_host preserves existing suppression."""
    host_id = str(uuid4())

    # Create host
    async with sm() as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=b"\x00" * 32,
            agent_version="0.4.0",
        )
        session.add(host)
        await session.commit()

    # Create advisory + affected package
    async with sm() as session:
        advisory = Advisory(
            id="CVE-2024-5555",
            summary="Test vulnerability",
            severity="medium",
        )
        session.add(advisory)

        affected = AffectedPackage(
            advisory_id="CVE-2024-5555",
            ecosystem="PyPI",
            package="flask",
            introduced="1.0.0",
            fixed="2.0.0",
            range_kind="SEMVER",
        )
        session.add(affected)
        await session.commit()

    # Create host package
    async with sm() as session:
        pkg = HostPackage(
            host_id=host_id,
            ecosystem="PyPI",
            name="flask",
            version="1.5.0",
        )
        session.add(pkg)
        await session.commit()

    # First match
    await match_host(sm, host_id)

    # Pre-create a suppressed HostAdvisory
    expiry = datetime(2099, 12, 31, tzinfo=timezone.utc)
    async with sm() as session:
        from sqlalchemy import select
        stmt = select(HostAdvisory).where(HostAdvisory.host_id == host_id)
        result = await session.execute(stmt)
        ha = result.scalar_one()
        ha.suppressed_until = expiry
        ha.suppressed_by = "test-user"
        ha.suppressed_reason = "test reason"
        await session.commit()

    # Re-run matcher
    await match_host(sm, host_id)

    # Verify suppression preserved
    async with sm() as session:
        from sqlalchemy import select
        stmt = select(HostAdvisory).where(HostAdvisory.host_id == host_id)
        result = await session.execute(stmt)
        ha = result.scalar_one()
        assert ha.suppressed_by == "test-user"
        assert ha.suppressed_reason == "test reason"
        # Check expiry is set (may lose TZ info through DB)
        assert ha.suppressed_until is not None


@pytest.mark.asyncio
async def test_match_host_marks_fixed_when_upgraded(sm: async_sessionmaker) -> None:
    """When current >= fixed after upgrade, status becomes 'fixed'."""
    host_id = str(uuid4())

    # Create host
    async with sm() as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=b"\x00" * 32,
            agent_version="0.4.0",
        )
        session.add(host)
        await session.commit()

    # Create advisory + affected package
    async with sm() as session:
        advisory = Advisory(
            id="CVE-2024-6666",
            summary="Test vulnerability",
            severity="high",
        )
        session.add(advisory)

        affected = AffectedPackage(
            advisory_id="CVE-2024-6666",
            ecosystem="PyPI",
            package="django",
            introduced="1.0.0",
            fixed="3.0.0",
            range_kind="SEMVER",
        )
        session.add(affected)
        await session.commit()

    # Create host package with vulnerable version
    async with sm() as session:
        pkg = HostPackage(
            host_id=host_id,
            ecosystem="PyPI",
            name="django",
            version="2.0.0",  # vulnerable
        )
        session.add(pkg)
        await session.commit()

    # Run matcher - creates open advisory
    await match_host(sm, host_id)

    # Verify status is 'open'
    async with sm() as session:
        from sqlalchemy import select
        stmt = select(HostAdvisory).where(HostAdvisory.host_id == host_id)
        result = await session.execute(stmt)
        ha = result.scalar_one()
        assert ha.status == "open"

    # Now upgrade the package
    async with sm() as session:
        from sqlalchemy import select
        stmt = select(HostPackage).where(
            HostPackage.host_id == host_id,
            HostPackage.name == "django"
        )
        result = await session.execute(stmt)
        pkg = result.scalar_one()
        pkg.version = "3.2.0"  # >= fixed
        await session.commit()

    # Re-run matcher
    await match_host(sm, host_id)

    # Verify status is now 'fixed'
    async with sm() as session:
        from sqlalchemy import select
        stmt = select(HostAdvisory).where(HostAdvisory.host_id == host_id)
        result = await session.execute(stmt)
        ha = result.scalar_one()
        assert ha.status == "fixed"
