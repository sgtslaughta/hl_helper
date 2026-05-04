"""Tests for MfaPolicy — login MFA requirement, recency, webauthn-only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from server.app.auth.mfa.policy import MfaPolicy, StepUpRequired
from server.app.models.user import User, UserKind


def _user() -> User:
    return User(id="u1", email="u1@example.com", kind=UserKind.LOCAL)


def test_admin_role_requires_mfa_at_login() -> None:
    p = MfaPolicy()
    assert p.requires_mfa_at_login(_user(), ["admin"]) is True


def test_owner_role_requires_mfa_at_login() -> None:
    p = MfaPolicy()
    assert p.requires_mfa_at_login(_user(), ["owner"]) is True


def test_regular_user_does_not_require_mfa_at_login() -> None:
    p = MfaPolicy()
    assert p.requires_mfa_at_login(_user(), ["viewer"]) is False
    assert p.requires_mfa_at_login(_user(), []) is False


def test_recency_required_high_risk_verbs() -> None:
    p = MfaPolicy()
    assert p.recency_required_seconds("secret.reveal") == 300
    assert p.recency_required_seconds("host.delete") == 300
    assert p.recency_required_seconds("binding.write") == 300
    assert p.recency_required_seconds("user.delete") == 300
    assert p.recency_required_seconds("bootstrap.create") == 300


def test_recency_required_low_risk_returns_none() -> None:
    p = MfaPolicy()
    assert p.recency_required_seconds("host.read") is None
    assert p.recency_required_seconds("audit.read") is None


def test_assert_recency_stale_raises_step_up() -> None:
    p = MfaPolicy()
    user = _user()
    stale = datetime.now(timezone.utc) - timedelta(minutes=10)
    with pytest.raises(StepUpRequired):
        p.assert_recency(user, "secret.reveal", stale)


def test_assert_recency_none_raises_step_up_for_high_risk() -> None:
    p = MfaPolicy()
    user = _user()
    with pytest.raises(StepUpRequired):
        p.assert_recency(user, "secret.reveal", None)


def test_assert_recency_fresh_does_not_raise() -> None:
    p = MfaPolicy()
    user = _user()
    fresh = datetime.now(timezone.utc) - timedelta(minutes=2)
    p.assert_recency(user, "secret.reveal", fresh)  # no exception


def test_assert_recency_low_risk_verb_skipped() -> None:
    p = MfaPolicy()
    user = _user()
    # No last_mfa_at, but low-risk verb → no raise
    p.assert_recency(user, "host.read", None)


def test_webauthn_only_role_with_only_totp_returns_false() -> None:
    p = MfaPolicy()
    user = _user()
    # Mark as webauthn-only via attr
    user.webauthn_only = True  # type: ignore[attr-defined]
    assert p.webauthn_only_satisfied(user, ["totp"]) is False


def test_webauthn_only_role_with_webauthn_returns_true() -> None:
    p = MfaPolicy()
    user = _user()
    user.webauthn_only = True  # type: ignore[attr-defined]
    assert p.webauthn_only_satisfied(user, ["webauthn"]) is True


def test_webauthn_only_user_without_attr_any_method_satisfies() -> None:
    p = MfaPolicy()
    user = _user()
    assert p.webauthn_only_satisfied(user, ["totp"]) is True
