"""Tests for inventory servicer handlers."""

from __future__ import annotations

from uuid import uuid4

import pytest_asyncio
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.grpc._pb.fleet.v1 import inventory_pb2
from server.app.grpc.inventory_servicer import (
    handle_package_inventory,
    handle_container_inventory,
    handle_host_facts,
)
from server.app.models.host import Host
from server.app.models.host_package import HostPackage
from server.app.models.host_container import HostContainer


@pytest_asyncio.fixture
async def host_id(sm: async_sessionmaker) -> str:
    """Create a test host."""
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


class TestPackageInventory:
    """Test handle_package_inventory function."""

    async def test_full_snapshot_inserts_packages(self, sm: async_sessionmaker, host_id: str):
        """Full snapshot with 2 packages should insert 2 rows."""
        now_ts = Timestamp()
        now_ts.GetCurrentTime()

        msg = inventory_pb2.PackageInventory(
            host_id=host_id,
            at=now_ts,
            full_snapshot=True,
            added=[
                inventory_pb2.PackageInventory.Pkg(
                    ecosystem="dpkg",
                    name="curl",
                    version="7.68.0",
                    source="curl",
                    arch="amd64",
                ),
                inventory_pb2.PackageInventory.Pkg(
                    ecosystem="dpkg",
                    name="openssl",
                    version="1.1.1",
                    source="openssl",
                    arch="amd64",
                ),
            ],
        )

        await handle_package_inventory(sm, msg)

        # Assert 2 packages inserted
        async with sm() as session:
            pkgs = (
                await session.execute(
                    select(HostPackage).where(HostPackage.host_id == host_id)
                )
            ).scalars().all()
            assert len(pkgs) == 2
            names = {p.name for p in pkgs}
            assert names == {"curl", "openssl"}

    async def test_full_snapshot_replaces_packages(self, sm: async_sessionmaker, host_id: str):
        """Full snapshot should replace previous packages."""
        now_ts = Timestamp()
        now_ts.GetCurrentTime()

        # First snapshot: 2 packages
        msg1 = inventory_pb2.PackageInventory(
            host_id=host_id,
            at=now_ts,
            full_snapshot=True,
            added=[
                inventory_pb2.PackageInventory.Pkg(
                    ecosystem="dpkg",
                    name="curl",
                    version="7.68.0",
                ),
                inventory_pb2.PackageInventory.Pkg(
                    ecosystem="dpkg",
                    name="openssl",
                    version="1.1.1",
                ),
            ],
        )
        await handle_package_inventory(sm, msg1)

        # Second snapshot: 1 package
        msg2 = inventory_pb2.PackageInventory(
            host_id=host_id,
            at=now_ts,
            full_snapshot=True,
            added=[
                inventory_pb2.PackageInventory.Pkg(
                    ecosystem="dpkg",
                    name="curl",
                    version="7.70.0",
                ),
            ],
        )
        await handle_package_inventory(sm, msg2)

        # Assert only 1 package remains (the new curl)
        async with sm() as session:
            result = await session.execute(
                select(HostPackage).where(HostPackage.host_id == host_id)
            )
            pkgs = result.scalars().all()
            assert len(pkgs) == 1
            assert pkgs[0].name == "curl"
            assert pkgs[0].version == "7.70.0"

    async def test_delta_upsert_and_remove(self, sm: async_sessionmaker, host_id: str):
        """Delta: upsert added packages, delete removed packages."""
        now_ts = Timestamp()
        now_ts.GetCurrentTime()

        # Full snapshot: 2 packages
        msg1 = inventory_pb2.PackageInventory(
            host_id=host_id,
            at=now_ts,
            full_snapshot=True,
            added=[
                inventory_pb2.PackageInventory.Pkg(
                    ecosystem="dpkg",
                    name="curl",
                    version="7.68.0",
                ),
                inventory_pb2.PackageInventory.Pkg(
                    ecosystem="dpkg",
                    name="openssl",
                    version="1.1.1",
                ),
            ],
        )
        await handle_package_inventory(sm, msg1)

        # Delta: upgrade curl, remove openssl
        msg2 = inventory_pb2.PackageInventory(
            host_id=host_id,
            at=now_ts,
            full_snapshot=False,
            added=[
                inventory_pb2.PackageInventory.Pkg(
                    ecosystem="dpkg",
                    name="curl",
                    version="7.70.0",
                ),
            ],
            removed=[
                inventory_pb2.PackageInventory.Pkg(
                    ecosystem="dpkg",
                    name="openssl",
                ),
            ],
        )
        await handle_package_inventory(sm, msg2)

        # Assert curl upgraded, openssl removed
        async with sm() as session:
            result = await session.execute(
                select(HostPackage).where(HostPackage.host_id == host_id)
            )
            pkgs = result.scalars().all()
            assert len(pkgs) == 1
            assert pkgs[0].name == "curl"
            assert pkgs[0].version == "7.70.0"


class TestContainerInventory:
    """Test handle_container_inventory function."""

    async def test_full_snapshot_inserts_containers(self, sm: async_sessionmaker, host_id: str):
        """Full snapshot should insert containers."""
        now_ts = Timestamp()
        now_ts.GetCurrentTime()

        msg = inventory_pb2.ContainerInventory(
            host_id=host_id,
            at=now_ts,
            full_snapshot=True,
            containers=[
                inventory_pb2.ContainerInventory.Container(
                    id="abc123",
                    name="nginx",
                    image_ref="nginx:1.18",
                    image_digest="sha256:deadbeef",
                    state="running",
                    engine="docker",
                ),
            ],
        )

        await handle_container_inventory(sm, msg)

        # Assert 1 container inserted
        async with sm() as session:
            result = await session.execute(
                select(HostContainer).where(HostContainer.host_id == host_id)
            )
            containers = result.scalars().all()
            assert len(containers) == 1
            assert containers[0].name == "nginx"
            assert containers[0].container_id == "abc123"

    async def test_full_snapshot_replaces_containers(self, sm: async_sessionmaker, host_id: str):
        """Full snapshot should replace previous containers."""
        now_ts = Timestamp()
        now_ts.GetCurrentTime()

        # First snapshot
        msg1 = inventory_pb2.ContainerInventory(
            host_id=host_id,
            at=now_ts,
            full_snapshot=True,
            containers=[
                inventory_pb2.ContainerInventory.Container(
                    id="abc123",
                    name="nginx",
                    image_ref="nginx:1.18",
                    state="running",
                    engine="docker",
                ),
            ],
        )
        await handle_container_inventory(sm, msg1)

        # Second snapshot
        msg2 = inventory_pb2.ContainerInventory(
            host_id=host_id,
            at=now_ts,
            full_snapshot=True,
            containers=[
                inventory_pb2.ContainerInventory.Container(
                    id="def456",
                    name="redis",
                    image_ref="redis:6.0",
                    state="running",
                    engine="podman",
                ),
            ],
        )
        await handle_container_inventory(sm, msg2)

        # Assert only new container exists
        async with sm() as session:
            result = await session.execute(
                select(HostContainer).where(HostContainer.host_id == host_id)
            )
            containers = result.scalars().all()
            assert len(containers) == 1
            assert containers[0].name == "redis"


class TestHostFacts:
    """Test handle_host_facts function."""

    async def test_host_facts_persisted_to_survey(self, sm: async_sessionmaker, host_id: str):
        """Host facts should be persisted to host.survey['facts']."""
        now_ts = Timestamp()
        now_ts.GetCurrentTime()

        msg = inventory_pb2.HostFacts(
            host_id=host_id,
            at=now_ts,
            sshd={
                "passwordauthentication": "no",
                "pubkeyauthentication": "yes",
            },
            sysctl={
                "net.ipv4.ip_forward": "1",
            },
            mounts=[
                "/dev /dev devtmpfs",
                "/proc /proc proc",
            ],
            fs_perms={
                "/etc/shadow": "0640",
                "/etc/passwd": "0644",
            },
        )

        await handle_host_facts(sm, msg)

        # Assert facts in host.survey
        async with sm() as session:
            host = await session.get(Host, host_id)
            assert host is not None
            assert host.survey is not None
            assert "facts" in host.survey
            facts = host.survey["facts"]
            assert facts["sshd"]["passwordauthentication"] == "no"
            assert facts["sysctl"]["net.ipv4.ip_forward"] == "1"
            assert len(facts["mounts"]) == 2
            assert facts["fs_perms"]["/etc/shadow"] == "0640"


class TestBridgeMatcherHook:
    """Verify the agent_bridge layer enqueues a match on the worker after ingest.

    Matching itself is owned by AdvisoryWorker now (covered separately); these
    tests just assert the bridge → worker.enqueue_match wiring fires.
    """

    async def test_bridge_enqueues_match_after_inventory(
        self, sm: async_sessionmaker, host_id: str
    ):
        from server.app.grpc.agent_bridge import AgentBridgeService
        from server.app.grpc.dispatcher import CommandDispatcher

        class _StubWorker:
            def __init__(self) -> None:
                self.calls: list[str] = []

            async def enqueue_match(self, host_id: str) -> bool:
                self.calls.append(host_id)
                return True

        worker = _StubWorker()
        bridge = AgentBridgeService(
            CommandDispatcher(),
            sessionmaker=sm,
            advisory_worker=worker,
        )

        # Drive the same path agent_bridge.Stream uses on each inventory msg.
        msg_pkg = inventory_pb2.PackageInventory(host_id=host_id, full_snapshot=True)
        await handle_package_inventory(sm, msg_pkg)
        await bridge._enqueue_match(host_id)

        msg_ct = inventory_pb2.ContainerInventory(host_id=host_id, full_snapshot=True)
        await handle_container_inventory(sm, msg_ct)
        await bridge._enqueue_match(host_id)

        assert worker.calls == [host_id, host_id]
