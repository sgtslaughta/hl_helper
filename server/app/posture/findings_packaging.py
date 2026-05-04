"""C11 packaging + release posture findings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.posture.model import Finding


async def install_script_template_missing(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """High: agent install.sh template absent -> enrollment install path broken."""
    candidates = [
        Path("server/templates/install.sh.j2"),
        Path("/home/user/code/hl_helper/server/templates/install.sh.j2"),
    ]
    if any(p.exists() for p in candidates):
        return None
    return Finding(
        id="install_script_template_missing",
        rule="install_script_template_missing",
        severity="high",
        title="Agent install script template missing",
        summary="server/templates/install.sh.j2 not found. "
        "Bootstrap enrollment via install script will fail until the template is restored.",
        docs_url="/docs/packaging/install-script",
        subject_kind="global",
    )


async def release_signing_not_configured(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Info: no Cosign release pipeline detected (release.yml absent)."""
    candidates = [
        Path(".github/workflows/release.yml"),
        Path("/home/user/code/hl_helper/.github/workflows/release.yml"),
    ]
    if any(p.exists() for p in candidates):
        return None
    return Finding(
        id="release_signing_not_configured",
        rule="release_signing_not_configured",
        severity="info",
        title="Release signing pipeline missing",
        summary="No release.yml workflow detected. Agent binaries are not Cosign-signed "
        "and no SBOM is published. Add release pipeline before public distribution.",
        docs_url="/docs/packaging/release",
        subject_kind="global",
    )
