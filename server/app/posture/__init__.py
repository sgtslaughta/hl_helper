"""Posture findings module — surface security/configuration findings."""

from __future__ import annotations

from typing import Awaitable, Callable

from server.app.posture.model import Finding, PostureFindingRow, SEVERITY_ORDER, Severity


def _registry() -> list[Callable[..., Awaitable["Finding | None"]]]:
    # Lazy import to avoid circular imports at package init.
    from server.app.posture import findings_auth_secrets as _f

    return [
        _f.local_password_admins_exist,
        _f.admin_without_webauthn,
        _f.recovery_codes_never_viewed,
        _f.passkey_synced,
        _f.signcount_regression_recent,
        _f.tls_self_signed,
        _f.secrets_root_key_colocated,
        _f.vault_unreachable,
        _f.mfa_recency_disabled_for_high_risk,
    ]


# Eagerly populate the registry on package import.
ALL_FINDINGS: list[Callable[..., Awaitable["Finding | None"]]] = _registry()


__all__ = ["Finding", "PostureFindingRow", "Severity", "ALL_FINDINGS", "SEVERITY_ORDER"]
