"""Host revocation service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models.host import Host
from server.app.models.revoked_cert import RevokedCert

if TYPE_CHECKING:
    from server.app.audit.sql_chain import SqlAuditChain
    from server.app.grpc.dispatcher import CommandDispatcher


class HostNotFoundError(Exception):
    """Host not found."""

    pass


class HostAlreadyRevokedError(Exception):
    """Host already revoked."""

    pass


class RevocationService:
    """Service for revoking hosts."""

    def __init__(
        self,
        dispatcher: CommandDispatcher,
        audit: SqlAuditChain,
        *,
        revoked_serials: set[str] | None = None,
    ) -> None:
        """Initialize revocation service.

        Args:
            dispatcher: Command dispatcher for terminating streams.
            audit: Audit chain for logging revocations.
            revoked_serials: In-memory set of revoked certificate serials.
        """
        self._dispatcher = dispatcher
        self._audit = audit
        self._revoked: set[str] = revoked_serials or set()

    async def is_revoked(self, serial: str) -> bool:
        """Check if a certificate serial is revoked.

        Args:
            serial: Certificate serial (hex format).

        Returns:
            True if revoked, False otherwise.
        """
        return serial in self._revoked

    async def load_from_db(self, session: AsyncSession) -> None:
        """Populate in-memory CRL set from DB (called at server startup).

        Args:
            session: Database session.
        """
        rows = await session.execute(select(RevokedCert.serial))
        self._revoked = {r[0] for r in rows.all()}

    async def revoke(
        self,
        session: AsyncSession,
        *,
        host_id: str,
        actor: str,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> RevokedCert:
        """Revoke a host: insert RevokedCert row, set host.status, terminate stream, audit.

        Args:
            session: Database session.
            host_id: Host ID to revoke.
            actor: Actor performing the revocation.
            reason: Optional reason for revocation.
            now: Revocation timestamp (default: now).

        Returns:
            The created RevokedCert row.

        Raises:
            HostNotFoundError: If host not found.
            HostAlreadyRevokedError: If host already revoked.
        """
        # Look up host
        host = await session.get(Host, host_id)
        if host is None:
            raise HostNotFoundError(f"host {host_id} not found")

        # Check status
        if host.status == "revoked":
            raise HostAlreadyRevokedError(f"host {host_id} already revoked")

        # Set timestamp
        if now is None:
            now = datetime.now(timezone.utc)

        # Get cert serial (or generate placeholder)
        serial = host.cert_serial or f"unknown-{host_id}"

        # Insert RevokedCert row
        revoked_cert = RevokedCert(
            serial=serial,
            host_id=host_id,
            revoked_at=now,
            reason=reason,
        )
        session.add(revoked_cert)
        await session.flush()

        # Update host status
        host.status = "revoked"
        await session.flush()

        # Add serial to in-memory CRL
        self._revoked.add(serial)

        # Terminate active stream
        await self._dispatcher.terminate(host_id)

        # Audit entry
        await self._audit.append(
            session,
            actor=actor,
            action="host.revoke",
            subject=host_id,
            payload={"reason": reason, "serial": serial},
            timestamp=now,
        )

        return revoked_cert
