"""Inventory handlers for PackageInventory, ContainerInventory, HostFacts.

After a successful ingest the agent_bridge layer calls
``worker.enqueue_match(host_id)`` when an AdvisoryWorker is wired in. This
module therefore no longer fans out ``asyncio.create_task`` for matching;
the worker queue handles dedup and serialisation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.grpc._pb.fleet.v1 import inventory_pb2
from server.app.models.host import Host
from server.app.models.host_container import HostContainer
from server.app.models.host_package import HostPackage

log = structlog.get_logger(__name__)


async def handle_package_inventory(
    sm: async_sessionmaker[AsyncSession],
    msg: inventory_pb2.PackageInventory,
) -> None:
    """Handle PackageInventory message: full snapshot or delta upsert.

    On full_snapshot=True: delete all host_packages for host_id, then insert added.
    On full_snapshot=False: upsert added (update version on conflict), delete removed.

    Args:
        sm: Async sessionmaker.
        msg: PackageInventory proto message.
    """
    try:
        async with sm() as session:
            host_id = msg.host_id
            if not host_id:
                log.warning("package_inventory.empty_host_id")
                return

            if msg.full_snapshot:
                # Delete all packages for this host
                await session.execute(
                    delete(HostPackage).where(HostPackage.host_id == host_id)
                )

            # Upsert added packages
            for pkg in msg.added:
                stmt = pg_insert(HostPackage).values(
                    host_id=host_id,
                    ecosystem=pkg.ecosystem,
                    name=pkg.name,
                    version=pkg.version,
                    source=pkg.source or None,
                    arch=pkg.arch or None,
                )
                # On conflict, update version and last_seen
                stmt = stmt.on_conflict_do_update(
                    index_elements=["host_id", "ecosystem", "name"],
                    set_={
                        "version": pkg.version,
                        "last_seen": datetime.now(timezone.utc),
                    },
                )
                await session.execute(stmt)

            # Delete removed packages
            for pkg in msg.removed:
                await session.execute(
                    delete(HostPackage).where(
                        HostPackage.host_id == host_id,
                        HostPackage.ecosystem == pkg.ecosystem,
                        HostPackage.name == pkg.name,
                    )
                )

            await session.commit()
    except Exception as e:
        log.warning(
            "package_inventory.handle_failed",
            host_id=msg.host_id,
            error=str(e),
        )


async def handle_container_inventory(
    sm: async_sessionmaker[AsyncSession],
    msg: inventory_pb2.ContainerInventory,
) -> None:
    """Handle ContainerInventory message: full snapshot or delta.

    On full_snapshot=True: delete all host_containers for host_id, then insert.
    On full_snapshot=False: upsert by (host_id, container_id).

    Args:
        sm: Async sessionmaker.
        msg: ContainerInventory proto message.
    """
    try:
        async with sm() as session:
            host_id = msg.host_id
            if not host_id:
                log.warning("container_inventory.empty_host_id")
                return

            if msg.full_snapshot:
                # Delete all containers for this host
                await session.execute(
                    delete(HostContainer).where(HostContainer.host_id == host_id)
                )

            # Upsert containers
            now = datetime.now(timezone.utc)
            for container in msg.containers:
                stmt = pg_insert(HostContainer).values(
                    host_id=host_id,
                    container_id=container.id,
                    name=container.name,
                    image_ref=container.image_ref,
                    image_digest=container.image_digest,
                    state=container.state,
                    engine=container.engine,
                )
                # On conflict, update state, image_ref, and last_seen
                stmt = stmt.on_conflict_do_update(
                    index_elements=["host_id", "container_id"],
                    set_={
                        "state": container.state,
                        "image_ref": container.image_ref,
                        "image_digest": container.image_digest,
                        "last_seen": now,
                    },
                )
                await session.execute(stmt)

            await session.commit()
    except Exception as e:
        log.warning(
            "container_inventory.handle_failed",
            host_id=msg.host_id,
            error=str(e),
        )


async def handle_host_facts(
    sm: async_sessionmaker[AsyncSession],
    msg: inventory_pb2.HostFacts,
) -> None:
    """Handle HostFacts message: persist facts to Host.survey['facts'].

    Args:
        sm: Async sessionmaker.
        msg: HostFacts proto message.
    """
    try:
        async with sm() as session:
            host_id = msg.host_id
            if not host_id:
                log.warning("host_facts.empty_host_id")
                return

            host = await session.get(Host, host_id)
            if not host:
                log.warning("host_facts.host_not_found", host_id=host_id)
                return

            # Load or initialize survey dict
            survey = dict(host.survey) if host.survey else {}

            # Build facts dict
            ts = datetime.now(timezone.utc).isoformat()
            facts = {
                "sshd": dict(msg.sshd),
                "sysctl": dict(msg.sysctl),
                "mounts": list(msg.mounts),
                "fs_perms": dict(msg.fs_perms),
                "at": ts,
            }

            # Merge facts into survey
            survey["facts"] = facts
            host.survey = survey
            await session.commit()
    except Exception as e:
        log.warning(
            "host_facts.handle_failed",
            host_id=msg.host_id,
            error=str(e),
        )
