"""C6 plugin system posture findings."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.posture.model import Finding


async def plugin_system_stub_only(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Info: only plugin hook stubs are wired; no runtime registry yet."""
    return Finding(
        id="plugin_system_stub_only",
        rule="plugin_system_stub_only",
        severity="info",
        title="Plugin system not fully implemented",
        summary="Only plugin hook stubs are present (auth/mfa, secrets backends). "
        "C6 runtime registry, isolation, and lifecycle controls are pending.",
        docs_url="/docs/components/c6-plugins",
        subject_kind="global",
    )
