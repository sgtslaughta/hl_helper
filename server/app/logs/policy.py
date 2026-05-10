"""Policy CRUD and scope-based resolution for agent log collection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from server.app.logs.models import AgentLogPolicy
from server.app.logs.schemas import CategoryRuleDoc, LogPolicyDoc


def _policy_to_json(p: LogPolicyDoc) -> dict:
    """Convert LogPolicyDoc to JSON-serializable dict."""
    return p.model_dump(mode="json")


def _policy_from_json(j: dict) -> LogPolicyDoc:
    """Reconstruct LogPolicyDoc from JSON dict."""
    return LogPolicyDoc.model_validate(j)


def upsert_policy(
    session: Session,
    scope: str,
    policy: LogPolicyDoc,
    *,
    created_by: str | None = None,
    expires_at: datetime | None = None,
) -> AgentLogPolicy:
    """Insert or replace a policy at the given scope.

    Args:
        session: Database session.
        scope: Policy scope (e.g., "global", "tag:name", "host:id").
        policy: Policy document.
        created_by: Optional creator identifier.
        expires_at: Optional expiration timestamp.

    Returns:
        The inserted or updated AgentLogPolicy row.
    """
    existing = session.execute(
        select(AgentLogPolicy).where(AgentLogPolicy.scope == scope)
    ).scalar_one_or_none()
    body = _policy_to_json(policy)
    if existing:
        existing.policy_json = body
        existing.policy_version = (existing.policy_version or 1) + 1
        existing.expires_at = expires_at
        if created_by is not None:
            existing.created_by = created_by
        session.commit()
        return existing
    row = AgentLogPolicy(
        scope=scope,
        policy_json=body,
        policy_version=policy.policy_version or 1,
        expires_at=expires_at,
        created_by=created_by,
    )
    session.add(row)
    session.commit()
    return row


def get_policy(session: Session, scope: str) -> LogPolicyDoc | None:
    """Retrieve the policy at a given scope.

    Args:
        session: Database session.
        scope: Policy scope.

    Returns:
        The LogPolicyDoc if found, None otherwise.
    """
    row = session.execute(
        select(AgentLogPolicy).where(AgentLogPolicy.scope == scope)
    ).scalar_one_or_none()
    if row is None:
        return None
    doc = _policy_from_json(row.policy_json)
    doc.policy_version = row.policy_version
    return doc


def delete_policy(session: Session, scope: str) -> bool:
    """Delete the policy at a given scope.

    Args:
        session: Database session.
        scope: Policy scope.

    Returns:
        True if a row was deleted, False otherwise.
    """
    res = session.execute(delete(AgentLogPolicy).where(AgentLogPolicy.scope == scope))
    session.commit()
    return res.rowcount > 0


def _merge_policy(base: LogPolicyDoc, override: LogPolicyDoc) -> LogPolicyDoc:
    """Merge override policy into base, with override winning.

    Scalar fields: override wins if not the Pydantic default.
    Categories: merged by name, with override entries winning per-category.

    Args:
        base: Base policy to start from.
        override: Policy whose non-default values override base.

    Returns:
        Merged LogPolicyDoc.
    """
    merged = base.model_copy(deep=True)
    # Heuristic: override fields that are NOT the Pydantic default
    defaults = LogPolicyDoc().model_dump()
    over = override.model_dump()
    for k, v in over.items():
        if k == "categories":
            continue
        if v != defaults.get(k):
            setattr(merged, k, v)
    # Merge categories by name; override wins
    by_name: dict[str, CategoryRuleDoc] = {c.category: c for c in merged.categories}
    for c in override.categories:
        by_name[c.category] = c
    merged.categories = list(by_name.values())
    return merged


def resolve(
    session: Session, host_id: str, host_tags: list[str] | None = None
) -> LogPolicyDoc:
    """Resolve the effective policy for a host by scope priority.

    Resolution order (low to high priority):
    1. global
    2. tag:<name> (alphabetically by tag name)
    3. host:<host_id>

    Each scope level is merged with preceding levels, with later scopes
    winning for scalar fields. Categories are merged by name.

    Args:
        session: Database session.
        host_id: Host identifier.
        host_tags: Optional list of tags assigned to the host.

    Returns:
        Effective LogPolicyDoc for the host.
    """
    host_tags = sorted(host_tags or [])
    scopes_ordered: list[str] = ["global"]
    for tag in host_tags:
        scopes_ordered.append(f"tag:{tag}")
    scopes_ordered.append(f"host:{host_id}")

    eff = LogPolicyDoc()
    for scope in scopes_ordered:
        doc = get_policy(session, scope)
        if doc is None:
            continue
        eff = _merge_policy(eff, doc)
    return eff


def apply_ttl_expiry(session: Session, now: datetime | None = None) -> int:
    """Remove all policies that have expired.

    Args:
        session: Database session.
        now: Current time for comparison (defaults to utcnow).

    Returns:
        Count of removed rows.
    """
    now = now or datetime.now(timezone.utc)
    res = session.execute(
        delete(AgentLogPolicy).where(
            AgentLogPolicy.expires_at.isnot(None)
        ).where(AgentLogPolicy.expires_at < now)
    )
    session.commit()
    return int(res.rowcount or 0)
