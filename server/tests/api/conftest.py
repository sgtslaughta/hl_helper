"""Shared pytest fixtures for API tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from server.app.models import Host
from server.app.models.agent_release import AgentRelease, ReleaseChannel, ReleaseStatus
from server.app.rbac.provider import Principal

# Re-export session maker and signing backend for API tests
from server.tests.grpc.conftest import signing_backend  # noqa: F401
from server.tests.models.conftest import sm  # noqa: F401


@pytest.fixture(autouse=True)
def _setup_default_current_principal_for_approvals_tests(request):
    """Auto-fixture that sets up a default current_principal for approval tests.

    This allows tests that use X-Acting-Principal headers to work without
    explicitly mocking the current_principal dependency in each test.

    Tests can override this by explicitly setting app.dependency_overrides[current_principal].
    """
    # Only apply to approval tests
    if "approvals" not in request.node.nodeid:
        yield
        return

    def patched_current_principal():
        # Return a default authenticated principal
        # Tests that need specific principals will use X-Acting-Principal header
        return Principal(user_id="u-system")

    # Patch the module
    import server.app.deps
    original = server.app.deps.current_principal
    server.app.deps.current_principal = patched_current_principal

    yield

    # Restore
    server.app.deps.current_principal = original


@pytest_asyncio.fixture
async def host_id(sm):
    """Create a test host with Linux x86_64."""
    async with sm() as session:
        host = Host(
            id=str(uuid4()),
            hostname="test-host",
            display_name="test-host",
            agent_pubkey=b"\x00" * 32,
            labels={"os": "linux", "arch": "x86_64"},
            agent_version="0.4.0",
        )
        session.add(host)
        await session.commit()
        return host.id


@pytest_asyncio.fixture
async def host_id_arm64(sm):
    """Create a test host with Linux ARM64."""
    async with sm() as session:
        host = Host(
            id=str(uuid4()),
            hostname="test-host-arm64",
            display_name="test-host-arm64",
            agent_pubkey=b"\x01" * 32,
            labels={"os": "linux", "arch": "arm64"},
            agent_version="0.4.0",
        )
        session.add(host)
        await session.commit()
        return host.id


@pytest_asyncio.fixture
async def host_with_v042(sm):
    """Create a test host with Linux x86_64 running v0.4.2."""
    async with sm() as session:
        host = Host(
            id=str(uuid4()),
            hostname="test-host-v042",
            display_name="test-host-v042",
            agent_pubkey=b"\x02" * 32,
            labels={"os": "linux", "arch": "x86_64"},
            agent_version="0.4.2",
        )
        session.add(host)
        await session.commit()
        return host.id


@pytest_asyncio.fixture
async def published_release_id(sm):
    """Create a published Linux x86_64 release (v0.4.1)."""
    async with sm() as session:
        release = AgentRelease(
            id=str(uuid4()),
            version="0.4.1",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="x86_64",
            sha256="abc123def456",
            size=1024,
            manifest_json=b'{"version":"0.4.1"}',
            manifest_sig=b"sig",
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="admin",
        )
        session.add(release)
        await session.commit()
        return release.id


@pytest_asyncio.fixture
async def yanked_release_id(sm):
    """Create a yanked Linux x86_64 release (v0.3.0)."""
    async with sm() as session:
        release = AgentRelease(
            id=str(uuid4()),
            version="0.3.0",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="x86_64",
            sha256="bad123def456",
            size=1024,
            manifest_json=b'{"version":"0.3.0"}',
            manifest_sig=b"sig",
            status=ReleaseStatus.YANKED,
            uploaded_by="admin",
        )
        session.add(release)
        await session.commit()
        return release.id


@pytest_asyncio.fixture
async def amd64_release_id(sm):
    """Create a published x86_64-only release (v0.4.1)."""
    async with sm() as session:
        release = AgentRelease(
            id=str(uuid4()),
            version="0.4.1",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="x86_64",
            sha256="xyz789abc456",
            size=1024,
            manifest_json=b'{"version":"0.4.1"}',
            manifest_sig=b"sig",
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="admin",
        )
        session.add(release)
        await session.commit()
        return release.id


@pytest_asyncio.fixture
async def v042_release_id(sm):
    """Create a published Linux x86_64 release (v0.4.2)."""
    async with sm() as session:
        release = AgentRelease(
            id=str(uuid4()),
            version="0.4.2",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="x86_64",
            sha256="def456abc789",
            size=1024,
            manifest_json=b'{"version":"0.4.2"}',
            manifest_sig=b"sig",
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="admin",
        )
        session.add(release)
        await session.commit()
        return release.id
