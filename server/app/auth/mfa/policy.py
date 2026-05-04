"""MFA policy — login requirements, step-up recency, and webauthn-only enforcement."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.app.models.user import User


# Roles that always require MFA at login.
_MFA_REQUIRED_ROLES: frozenset[str] = frozenset({"admin", "owner"})

# High-risk verb prefixes / exact verbs that require fresh MFA recency.
_HIGH_RISK_VERBS: frozenset[str] = frozenset({
    "secret.reveal",
    "host.delete",
    "binding.write",
    "user.delete",
})

# High-risk verb prefixes (anything starting with these).
_HIGH_RISK_PREFIXES: tuple[str, ...] = ("bootstrap.",)

# Default recency window for high-risk verbs: 5 minutes.
_DEFAULT_RECENCY_SECONDS: int = 300


class StepUpRequired(Exception):
    """Raised when a high-risk verb requires fresh MFA but recency is stale."""

    pass


class MfaPolicy:
    """Policy engine for MFA requirements at login and per-verb step-up."""

    def requires_mfa_at_login(self, user: "User", role_names: list[str]) -> bool:
        """Return True if the user must complete MFA at login.

        Admin/owner roles always require MFA. Other users may opt in
        via a future per-user attribute (placeholder).
        """
        for r in role_names:
            if r in _MFA_REQUIRED_ROLES:
                return True
        # TODO(c3-roles): wire from Role.attrs once role-attribute schema lands.
        # Defaults to False (permissive).
        return bool(getattr(user, "mfa_required", False))

    def recency_required_seconds(self, verb: str) -> int | None:
        """Return required MFA recency window in seconds, or None for low-risk."""
        if verb in _HIGH_RISK_VERBS:
            return _DEFAULT_RECENCY_SECONDS
        for prefix in _HIGH_RISK_PREFIXES:
            if verb.startswith(prefix):
                return _DEFAULT_RECENCY_SECONDS
        return None

    def assert_recency(
        self,
        user: "User",
        verb: str,
        last_mfa_ts: datetime | None,
    ) -> None:
        """Assert that MFA recency is fresh enough for `verb`.

        Raises:
            StepUpRequired: if the verb is high-risk and recency is stale or absent.
        """
        window = self.recency_required_seconds(verb)
        if window is None:
            return
        if last_mfa_ts is None:
            raise StepUpRequired(f"mfa_step_up_required for {verb}")
        # Normalize to aware UTC.
        ts = last_mfa_ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - ts > timedelta(seconds=window):
            raise StepUpRequired(f"mfa_step_up_required for {verb}")

    def webauthn_only_satisfied(self, user: "User", methods_used: list[str]) -> bool:
        """If the user is webauthn-only, only "webauthn" satisfies; otherwise any method works."""
        # TODO(c3-roles): wire from Role.attrs once role-attribute schema lands.
        # Defaults to False (permissive).
        if not getattr(user, "webauthn_only", False):
            return True
        return "webauthn" in methods_used
