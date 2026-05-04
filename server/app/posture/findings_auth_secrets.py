"""Auth & secrets posture findings.

Each `async` function returns a `Finding | None`. Functions accept the
sessionmaker as the first positional arg and ignore unknown keyword args
so the dispatcher can pass extras (broker, settings) uniformly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.models import Binding, Role, User
from server.app.models.binding import PrincipalType
from server.app.models.recovery_code import RecoveryCode
from server.app.models.user import UserKind
from server.app.models.webauthn_credential import WebAuthnCredential
from server.app.posture.model import Finding
from server.app.settings.config import FleetSettings, load_settings

log = structlog.get_logger(__name__)

_ADMIN_ROLE_NAMES = ("owner", "admin")


# ---------------------------------------------------------------------------
# Finding implementations
# ---------------------------------------------------------------------------


async def local_password_admins_exist(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Flag when any admin/owner is a local-password user (kind == 'local')."""
    async with sessionmaker() as s:
        stmt = (
            select(User.id)
            .join(Binding, Binding.principal_id == User.id)
            .join(Role, Role.id == Binding.role_id)
            .where(
                Binding.principal_type == PrincipalType.USER,
                Role.name.in_(_ADMIN_ROLE_NAMES),
                User.kind == UserKind.LOCAL,
            )
            .limit(1)
        )
        row = (await s.execute(stmt)).first()
    if row is None:
        return None
    return Finding(
        id="local_password_admins_exist",
        severity="medium",
        title="Local-password admin accounts present",
        summary="One or more admin/owner users authenticate with a local password. "
        "Prefer SSO + WebAuthn for privileged accounts.",
        docs_url="/docs/auth/local-password-admins",
    )


async def admin_without_webauthn(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Flag admin users who have no WebAuthn credential registered."""
    async with sessionmaker() as s:
        admin_users = (
            await s.execute(
                select(User.id)
                .join(Binding, Binding.principal_id == User.id)
                .join(Role, Role.id == Binding.role_id)
                .where(
                    Binding.principal_type == PrincipalType.USER,
                    Role.name.in_(_ADMIN_ROLE_NAMES),
                )
            )
        ).scalars().all()
        if not admin_users:
            return None
        for uid in admin_users:
            cred = (
                await s.execute(
                    select(WebAuthnCredential.id)
                    .where(WebAuthnCredential.user_id == uid)
                    .limit(1)
                )
            ).first()
            if cred is None:
                return Finding(
                    id="admin_without_webauthn",
                    severity="medium",
                    title="Admin without WebAuthn credential",
                    summary="At least one admin user has no WebAuthn / passkey "
                    "credential. Enroll a hardware-backed authenticator.",
                    docs_url="/docs/auth/webauthn",
                )
    return None


async def recovery_codes_never_viewed(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Flag when any RecoveryCode rows have viewed_at IS NULL."""
    async with sessionmaker() as s:
        row = (
            await s.execute(
                select(RecoveryCode.id)
                .where(RecoveryCode.viewed_at.is_(None))
                .limit(1)
            )
        ).first()
    if row is None:
        return None
    return Finding(
        id="recovery_codes_never_viewed",
        severity="low",
        title="Recovery codes generated but never viewed",
        summary="One or more recovery code sets exist that the owner never "
        "viewed/recorded. Prompt users to download or rotate them.",
        docs_url="/docs/auth/recovery-codes",
    )


async def passkey_synced(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Informational: any synced (cloud-backed) passkeys present.

    Best-effort: relies on `backup_state == "synced"` recorded at registration.
    """
    async with sessionmaker() as s:
        row = (
            await s.execute(
                select(WebAuthnCredential.id)
                .where(WebAuthnCredential.backup_state == "synced")
                .limit(1)
            )
        ).first()
    if row is None:
        return None
    return Finding(
        id="passkey_synced",
        severity="info",
        title="Cloud-synced passkey detected",
        summary="One or more registered WebAuthn credentials are reported as "
        "synced (cloud-backed). Confirm this matches your policy.",
        docs_url="/docs/auth/passkeys",
    )


async def signcount_regression_recent(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Flag WebAuthn credentials flagged within the last 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    async with sessionmaker() as s:
        row = (
            await s.execute(
                select(WebAuthnCredential.id)
                .where(WebAuthnCredential.flagged_at.is_not(None))
                .where(WebAuthnCredential.flagged_at >= cutoff)
                .limit(1)
            )
        ).first()
    if row is None:
        return None
    return Finding(
        id="signcount_regression_recent",
        severity="high",
        title="WebAuthn sign-count regression detected",
        summary="A WebAuthn credential was flagged for a sign-count regression "
        "in the last 7 days (possible cloning). Investigate and disable.",
        docs_url="/docs/auth/webauthn-cloning",
    )


async def tls_self_signed(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Stub: cert chain inspection not yet implemented.

    TODO(c3-tls): inspect server cert chain for self-signed leaves.
    """
    return None


async def secrets_root_key_colocated(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    settings: FleetSettings | None = None,
    **_: Any,
) -> Finding | None:
    """Heuristic: flag if local secrets root key is set AND its dir shares
    a parent prefix with the database file path.
    """
    s = settings or load_settings()
    if not s.secrets_root_key_b64 or not s.secrets_root_dir:
        return None

    # Parse db path from db_url. Best-effort; only sqlite local files matter.
    db_path = _extract_sqlite_path(s.db_url)
    if db_path is None:
        return None

    secrets_dir = Path(s.secrets_root_dir).resolve(strict=False)
    db_parent = db_path.parent.resolve(strict=False)

    # Heuristic: same parent dir, or one is a prefix of the other.
    if (
        secrets_dir == db_parent
        or _is_prefix(secrets_dir, db_parent)
        or _is_prefix(db_parent, secrets_dir)
    ):
        return Finding(
            id="secrets_root_key_colocated",
            severity="high",
            title="Secrets root key colocated with database",
            summary="The local secrets root key directory shares a path prefix "
            "with the database file. A single host compromise exposes both. "
            "Place the key on a separate filesystem / mount.",
            docs_url="/docs/secrets/root-key-isolation",
        )
    return None


async def vault_unreachable(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    broker: Any | None = None,
    **_: Any,
) -> Finding | None:
    """Flag if vault backend is configured but health_check fails or is sealed."""
    if broker is None:
        return None
    backends = getattr(broker, "backends", None) or {}
    vault = backends.get("vault")
    if vault is None:
        return None
    try:
        h = await vault.health_check()
    except Exception as e:
        log.warning("posture_vault_health_failed", exc=str(e))
        return Finding(
            id="vault_unreachable",
            severity="critical",
            title="Vault backend unreachable",
            summary="Vault health-check failed. Secrets routed to vault will be "
            "unavailable. Check server logs for details.",
            docs_url="/docs/secrets/vault",
        )
    if h.get("sealed"):
        return Finding(
            id="vault_unreachable",
            severity="critical",
            title="Vault backend is sealed",
            summary="Vault reports sealed=true. Unseal the cluster to restore "
            "access to vault-backed secrets.",
            docs_url="/docs/secrets/vault",
        )
    return None


async def mfa_recency_disabled_for_high_risk(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Flag if MFA policy has no high-risk verbs or prefixes configured for step-up."""
    from server.app.auth.mfa import policy as policy_mod

    has_verbs = bool(getattr(policy_mod, "_HIGH_RISK_VERBS", None))
    has_prefixes = bool(getattr(policy_mod, "_HIGH_RISK_PREFIXES", None))
    if has_verbs or has_prefixes:
        return None
    return Finding(
        id="mfa_recency_disabled_for_high_risk",
        severity="medium",
        title="MFA step-up disabled for all verbs",
        summary="No verbs or verb prefixes are configured to require fresh MFA. "
        "High-risk actions will not prompt for re-authentication.",
        docs_url="/docs/auth/step-up",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_sqlite_path(db_url: str) -> Path | None:
    """Return Path for a sqlite[+driver] URL, or None for non-sqlite/in-memory."""
    if "sqlite" not in db_url:
        return None
    # Strip scheme up to ':///'
    idx = db_url.find(":///")
    if idx < 0:
        return None
    raw = db_url[idx + 3 :]
    # SQLAlchemy uses sqlite:////abs/path (4 slashes) for absolute paths.
    # After ":///" we have "/abs/path" or "rel/path".
    if not raw or raw == "/" or ":memory:" in raw:
        return None
    return Path(raw)


def _is_prefix(a: Path, b: Path) -> bool:
    """Return True if `a` is an ancestor of (or equal to) `b`."""
    try:
        b.relative_to(a)
        return True
    except ValueError:
        return False


__all__ = [
    "local_password_admins_exist",
    "admin_without_webauthn",
    "recovery_codes_never_viewed",
    "passkey_synced",
    "signcount_regression_recent",
    "tls_self_signed",
    "secrets_root_key_colocated",
    "vault_unreachable",
    "mfa_recency_disabled_for_high_risk",
]
