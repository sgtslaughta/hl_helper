"""Advisory findings — surface host advisories as posture findings."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.models.host_advisory import HostAdvisory
from server.app.models.advisory import Advisory
from server.app.posture.model import Finding


async def collect_advisory_findings(
    sm: async_sessionmaker[AsyncSession], **ctx
) -> list[Finding]:
    """Collect advisory findings grouped by host.

    Emits one Finding per host with open critical/high advisories. Uses two
    queries (fleet → catalog) so the same code path works for SQLite split
    files and a unified Postgres deployment.
    """
    catalog_sm: async_sessionmaker[AsyncSession] | None = ctx.get("catalog_sm")
    findings: list[Finding] = []

    async with sm() as session:
        host_rows = list(
            (
                await session.execute(
                    select(HostAdvisory).where(HostAdvisory.status == "open")
                )
            ).scalars().all()
        )

    if not host_rows:
        return findings

    advisory_ids = list({ha.advisory_id for ha in host_rows})
    catalog = catalog_sm or sm
    async with catalog() as cat_session:
        adv_rows = list(
            (
                await cat_session.execute(
                    select(Advisory).where(Advisory.id.in_(advisory_ids))
                )
            ).scalars().all()
        )
    by_id = {a.id: a for a in adv_rows}

    by_host: dict[str, list[tuple[HostAdvisory, Advisory]]] = defaultdict(list)
    for ha in host_rows:
        adv = by_id.get(ha.advisory_id)
        if adv is not None:
            by_host[ha.host_id].append((ha, adv))

    # Emit one Finding per host
    for host_id, advisories in by_host.items():
        # Count by severity
        critical_count = sum(1 for _, adv in advisories if adv.severity == "critical")
        high_count = sum(1 for _, adv in advisories if adv.severity == "high")

        if critical_count > 0:
            severity = "critical"
            count = critical_count
        elif high_count > 0:
            severity = "high"
            count = high_count
        else:
            # Skip if no critical/high
            continue

        # Create stable ID
        finding_id = sha256(f"host_advisory:{host_id}:{severity}".encode()).hexdigest()[:16]

        finding = Finding(
            id=finding_id,
            severity=severity,
            title=f"{count} {severity} advisories",
            summary=f"Host has {count} {severity} security advisories requiring attention.",
            rule="host_advisory_summary",
            subject_kind="host",
            subject_id=host_id,
        )
        findings.append(finding)

    return findings
