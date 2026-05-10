"""Tests for log policy CRUD and scope resolution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from server.app.logs.policy import (
    apply_ttl_expiry,
    delete_policy,
    get_policy,
    resolve,
    upsert_policy,
)
from server.app.logs.schemas import CategoryRuleDoc, LogPolicyDoc


def test_upsert_and_get(db_session):
    p = LogPolicyDoc(default_level="debug")
    upsert_policy(db_session, "global", p)
    got = get_policy(db_session, "global")
    assert got is not None
    assert got.default_level == "debug"


def test_upsert_replaces_existing(db_session):
    upsert_policy(db_session, "global", LogPolicyDoc(default_level="info"))
    upsert_policy(db_session, "global", LogPolicyDoc(default_level="warn"))
    got = get_policy(db_session, "global")
    assert got.default_level == "warn"


def test_delete(db_session):
    upsert_policy(db_session, "global", LogPolicyDoc())
    assert delete_policy(db_session, "global") is True
    assert get_policy(db_session, "global") is None
    assert delete_policy(db_session, "global") is False


def test_resolve_no_rows_returns_defaults(db_session):
    eff = resolve(db_session, host_id="h1")
    assert eff.default_level == "info"


def test_resolve_global_only(db_session):
    upsert_policy(
        db_session,
        "global",
        LogPolicyDoc(default_level="debug", batch_max_bytes=128 * 1024),
    )
    eff = resolve(db_session, host_id="h1")
    assert eff.default_level == "debug"
    assert eff.batch_max_bytes == 128 * 1024


def test_resolve_host_overrides_global(db_session):
    upsert_policy(db_session, "global", LogPolicyDoc(default_level="info"))
    upsert_policy(db_session, "host:h1", LogPolicyDoc(default_level="debug"))
    eff = resolve(db_session, host_id="h1")
    assert eff.default_level == "debug"
    # other host unaffected
    eff2 = resolve(db_session, host_id="h2")
    assert eff2.default_level == "info"


def test_resolve_tag_between_global_and_host(db_session):
    upsert_policy(
        db_session,
        "global",
        LogPolicyDoc(default_level="info", batch_max_bytes=65536),
    )
    upsert_policy(
        db_session,
        "tag:noisy",
        LogPolicyDoc(default_level="warn", batch_max_bytes=128 * 1024),
    )
    upsert_policy(db_session, "host:h1", LogPolicyDoc(default_level="error"))
    eff = resolve(db_session, host_id="h1", host_tags=["noisy"])
    assert eff.default_level == "error"  # host wins
    assert eff.batch_max_bytes == 128 * 1024  # tag overrode global; host did not set


def test_resolve_merges_categories(db_session):
    upsert_policy(
        db_session,
        "global",
        LogPolicyDoc(
            categories=[CategoryRuleDoc(category="task", sample_rate=0.1)]
        ),
    )
    upsert_policy(
        db_session,
        "host:h1",
        LogPolicyDoc(
            categories=[
                CategoryRuleDoc(category="task", sample_rate=1.0),
                CategoryRuleDoc(category="update", level="debug"),
            ]
        ),
    )
    eff = resolve(db_session, host_id="h1")
    by_name = {c.category: c for c in eff.categories}
    assert by_name["task"].sample_rate == 1.0  # host overrode
    assert "update" in by_name


def test_apply_ttl_expiry_removes_expired(db_session):
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    upsert_policy(
        db_session, "host:h1", LogPolicyDoc(default_level="debug"), expires_at=past
    )
    upsert_policy(db_session, "host:h2", LogPolicyDoc(default_level="debug"))  # no expiry
    removed = apply_ttl_expiry(db_session)
    assert removed == 1
    assert get_policy(db_session, "host:h1") is None
    assert get_policy(db_session, "host:h2") is not None
