"""Misconfig findings — surface host misconfigurations as posture findings."""

from __future__ import annotations

from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.models.host import Host
from server.app.posture.model import Finding


async def collect_misconfig_findings(
    sm: async_sessionmaker[AsyncSession], **ctx
) -> list[Finding]:
    """Collect host misconfig findings.

    Reads Host.survey["facts"] and emits findings for each violation.

    @param sm   Async sessionmaker for database access.
    @param ctx  Context dict (unused).
    @return List of Finding objects.
    """
    findings: list[Finding] = []

    async with sm() as session:
        # Load all hosts with survey data
        stmt = select(Host).where(Host.survey.is_not(None))
        hosts = (await session.execute(stmt)).scalars().all()

    for host in hosts:
        if not host.survey or not host.survey.get("facts"):
            continue

        facts = host.survey["facts"]

        # Rule 1: sshd.permitrootlogin == "yes"
        sshd = facts.get("sshd", {})
        if sshd.get("permitrootlogin") == "yes":
            finding_id = sha256(
                f"misconfig_root_login:{host.id}".encode()
            ).hexdigest()[:16]
            findings.append(
                Finding(
                    id=finding_id,
                    severity="high",
                    title="Root SSH login enabled",
                    summary="SSH root login is enabled, allowing direct root access.",
                    rule="sshd_permitrootlogin",
                    subject_kind="host",
                    subject_id=host.id,
                )
            )

        # Rule 2: sshd.passwordauthentication == "yes"
        if sshd.get("passwordauthentication") == "yes":
            finding_id = sha256(
                f"misconfig_ssh_password:{host.id}".encode()
            ).hexdigest()[:16]
            findings.append(
                Finding(
                    id=finding_id,
                    severity="medium",
                    title="SSH password auth enabled",
                    summary="SSH password authentication is enabled; key-based auth is preferred.",
                    rule="sshd_passwordauth",
                    subject_kind="host",
                    subject_id=host.id,
                )
            )

        # Rule 3: kernel.randomize_va_space != "2"
        sysctl = facts.get("sysctl", {})
        aslr_val = sysctl.get("kernel.randomize_va_space")
        if aslr_val is not None and aslr_val != "2":
            finding_id = sha256(
                f"misconfig_aslr:{host.id}".encode()
            ).hexdigest()[:16]
            findings.append(
                Finding(
                    id=finding_id,
                    severity="medium",
                    title="ASLR not fully enabled",
                    summary="Address Space Layout Randomization (ASLR) is not fully enabled.",
                    rule="kernel_aslr",
                    subject_kind="host",
                    subject_id=host.id,
                )
            )

        # Rule 4: /etc/shadow permissions not in {"0640", "0600"}
        fs_perms = facts.get("fs_perms", {})
        shadow_perms = fs_perms.get("/etc/shadow")
        if shadow_perms is not None and shadow_perms not in ("0640", "0600"):
            finding_id = sha256(
                f"misconfig_shadow_perms:{host.id}".encode()
            ).hexdigest()[:16]
            findings.append(
                Finding(
                    id=finding_id,
                    severity="high",
                    title="/etc/shadow world-readable",
                    summary=f"/etc/shadow has overly permissive permissions: {shadow_perms}.",
                    rule="fs_shadow_perms",
                    subject_kind="host",
                    subject_id=host.id,
                )
            )

    return findings
