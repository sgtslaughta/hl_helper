"""C4 update engine posture findings.

C4 ships only the model scaffolding. These findings flag common update-engine
hygiene issues; expand as handlers come online.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.posture.model import Finding


async def update_engine_not_configured(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Info: update_policy table empty -> no auto-update strategy defined."""
    try:
        from server.app.models.update_policy import UpdatePolicy
    except Exception:
        return None
    async with sessionmaker() as s:
        n = await s.scalar(select(func.count(UpdatePolicy.id)))
    if n and n > 0:
        return None
    return Finding(
        id="update_engine_not_configured",
        rule="update_engine_not_configured",
        severity="info",
        title="No update policies configured",
        summary="No UpdatePolicy rows exist. Define cadence, scope, and approval gates "
        "before enabling fleet-wide updates.",
        docs_url="/docs/update-engine/policies",
        subject_kind="global",
    )
