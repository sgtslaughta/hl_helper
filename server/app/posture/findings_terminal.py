"""C9 terminal posture findings (component not yet implemented)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.posture.model import Finding


async def terminal_not_implemented(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Info: C9 terminal access is not yet implemented."""
    return Finding(
        id="terminal_not_implemented",
        rule="terminal_not_implemented",
        severity="info",
        title="Interactive terminal unavailable",
        summary="C9 interactive terminal (PTY over WS) is not yet implemented. "
        "Use `host:exec` capability with bounded sudo for now.",
        docs_url="/docs/components/c9-terminal",
        subject_kind="global",
    )
