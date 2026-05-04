"""C7 docker management posture findings (component not yet implemented)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.posture.model import Finding


async def docker_management_not_implemented(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Info: C7 Docker management has not shipped yet."""
    return Finding(
        id="docker_management_not_implemented",
        rule="docker_management_not_implemented",
        severity="info",
        title="Docker management unavailable",
        summary="C7 docker management is not yet implemented. "
        "Container exec, image scan, and registry actions will report as unsupported.",
        docs_url="/docs/components/c7-docker",
        subject_kind="global",
    )
