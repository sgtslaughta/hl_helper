"""Claim mapping + JIT user provisioning for OIDC.

Claim path syntax (JSONPath-lite):
  - Dotted: ``a.b.c`` walks dict keys
  - ``$``-prefixed allowed (stripped)
  - Literal dots in keys are not supported (matches legacy JSONPath '.')

Group claims may be a list of paths; each is resolved and the union returned.
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.models.binding import Binding, PrincipalType, ScopeKind
from server.app.models.oidc_account_link import OidcAccountLink
from server.app.models.oidc_provider import OidcProvider
from server.app.models.role import Role
from server.app.models.user import User, UserKind


def _scope_hash(kind: str, value: dict[str, object]) -> str:
    """Canonical scope_hash for Binding rows. Mirrors api.v1.bindings.compute_scope_hash."""
    canon = _json.dumps({"kind": kind, "value": value}, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# JSONPath-lite
# --------------------------------------------------------------------------- #


def _resolve_path(claims: dict[str, Any], path: str) -> Any:
    """Walk a dotted path. Returns None if any segment missing.

    A leading ``$.`` or ``$`` is stripped.
    """
    if not path:
        return None
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]
    cur: Any = claims
    for seg in path.split("."):
        if seg == "":
            continue
        if isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
        if cur is None:
            return None
    return cur


def _coerce_groups(value: Any) -> list[str]:
    """Coerce a claim value into a list[str] of group names."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return []


@dataclass
class MappedClaims:
    """Result of applying claim mappings."""

    email: str | None
    display_name: str | None
    groups: list[str]


def apply_claim_mappings(claims: dict[str, Any], mappings: dict[str, Any]) -> MappedClaims:
    """Apply claim mappings to an OIDC claims dict.

    ``mappings`` keys: ``email``, ``display_name``, ``groups``.

    For ``groups`` the value may be a string path *or* a list of paths; the
    union of resolved values is returned (deduplicated, order preserved).
    """
    email_path = mappings.get("email") or "email"
    name_path = mappings.get("display_name") or "name"
    groups_spec = mappings.get("groups", [])

    email = _resolve_path(claims, email_path) if isinstance(email_path, str) else None
    name = _resolve_path(claims, name_path) if isinstance(name_path, str) else None

    group_paths: list[str]
    if isinstance(groups_spec, str):
        group_paths = [groups_spec]
    elif isinstance(groups_spec, list):
        group_paths = [g for g in groups_spec if isinstance(g, str)]
    else:
        group_paths = []

    seen: set[str] = set()
    groups: list[str] = []
    for gp in group_paths:
        for g in _coerce_groups(_resolve_path(claims, gp)):
            if g not in seen:
                seen.add(g)
                groups.append(g)

    return MappedClaims(
        email=email if isinstance(email, str) else None,
        display_name=name if isinstance(name, str) else None,
        groups=groups,
    )


# --------------------------------------------------------------------------- #
# JIT provisioning + linking
# --------------------------------------------------------------------------- #


class OidcLinkError(Exception):
    """Raised on link errors (e.g. duplicate)."""


async def jit_provision(
    sm: async_sessionmaker[Any],
    provider: OidcProvider,
    claims: dict[str, Any],
    mapped: MappedClaims,
) -> User:
    """Idempotently create or fetch a User + OidcAccountLink for OIDC sign-in.

    Lookup order:
      1. Existing OidcAccountLink (provider_id, sub) → return that user.
      2. Existing User by email → create link, return user.
      3. Create new User + link.

    Group claims are best-effort bound to existing built-in Roles via
    Binding rows (global scope). Unknown groups are skipped.
    """
    sub = claims.get("sub")
    if not sub:
        raise OidcLinkError("missing_sub")
    email = mapped.email
    if not email:
        raise OidcLinkError("missing_email")

    email_verified = claims.get("email_verified") is True

    async with sm() as session:
        # 1. existing link?
        link = await session.scalar(
            select(OidcAccountLink).where(
                OidcAccountLink.provider_id == provider.id,
                OidcAccountLink.subject == sub,
            )
        )
        if link is not None:
            user = await session.scalar(select(User).where(User.id == link.user_id))
            if user is None:
                raise OidcLinkError("link_user_missing")
            link.last_login_at = datetime.now(timezone.utc)
            link.email = email
            await session.commit()
            return cast(User, user)

        # 2. existing user by email — only if IdP asserted email_verified.
        # Otherwise an attacker could register at the IdP with the victim's
        # email and take over the account on first sign-in.
        existing_user = await session.scalar(select(User).where(User.email == email))
        if existing_user is not None and not email_verified:
            raise OidcLinkError("email_not_verified")
        user = existing_user
        if user is None:
            user = User(
                id=str(uuid4()),
                email=email,
                display_name=mapped.display_name,
                kind=UserKind.OIDC,
                oidc_subject=sub,
                oidc_issuer=provider.issuer,
            )
            session.add(user)
            await session.flush()

        link = OidcAccountLink(
            id=str(uuid4()),
            user_id=user.id,
            provider_id=provider.id,
            subject=sub,
            email=email,
            last_login_at=datetime.now(timezone.utc),
        )
        session.add(link)

        # 3. best-effort group bindings
        if mapped.groups:
            for gname in mapped.groups:
                role = await session.scalar(select(Role).where(Role.name == gname))
                if role is None:
                    logger.debug("oidc_group_unknown", extra={"group": gname})
                    continue
                # check existing binding
                existing = await session.scalar(
                    select(Binding).where(
                        Binding.principal_type == PrincipalType.USER,
                        Binding.principal_id == user.id,
                        Binding.role_id == role.id,
                        Binding.scope_kind == ScopeKind.GLOBAL,
                    )
                )
                if existing is None:
                    session.add(
                        Binding(
                            id=str(uuid4()),
                            principal_type=PrincipalType.USER,
                            principal_id=user.id,
                            role_id=role.id,
                            scope_kind=ScopeKind.GLOBAL,
                            scope_value={},
                            scope_hash=_scope_hash("global", {}),
                        )
                    )

        try:
            await session.commit()
        except IntegrityError:
            # Concurrent JIT for the same (provider_id, sub) — another worker
            # already created the link. Roll back, look it up, and return
            # that user so the caller observes a consistent result.
            await session.rollback()
            link = await session.scalar(
                select(OidcAccountLink).where(
                    OidcAccountLink.provider_id == provider.id,
                    OidcAccountLink.subject == sub,
                )
            )
            if link is None:
                raise
            existing = await session.scalar(
                select(User).where(User.id == link.user_id)
            )
            if existing is None:
                raise OidcLinkError("link_user_missing")
            return cast(User, existing)
        await session.refresh(user)
        return cast(User, user)


async def link_account(
    sm: async_sessionmaker[Any],
    user: User,
    provider: OidcProvider,
    subject: str,
    email: str | None,
) -> OidcAccountLink:
    """Admin-link flow: associate an OIDC subject with an existing user.

    Raises OidcLinkError if (provider, subject) is already linked.
    """
    async with sm() as session:
        existing = await session.scalar(
            select(OidcAccountLink).where(
                OidcAccountLink.provider_id == provider.id,
                OidcAccountLink.subject == subject,
            )
        )
        if existing is not None:
            raise OidcLinkError("already_linked")
        link = OidcAccountLink(
            id=str(uuid4()),
            user_id=user.id,
            provider_id=provider.id,
            subject=subject,
            email=email,
            last_login_at=datetime.now(timezone.utc),
        )
        session.add(link)
        await session.commit()
        await session.refresh(link)
        return link
