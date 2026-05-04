"""Posture findings module — surface security/configuration findings."""

from __future__ import annotations

from typing import Awaitable, Callable

from server.app.posture.model import Finding, PostureFindingRow, SEVERITY_ORDER, Severity


def _registry() -> list[Callable[..., Awaitable["Finding | None"]]]:
    # Lazy import to avoid circular imports at package init.
    from server.app.posture import (
        findings_auth_secrets as _auth,
        findings_docker as _docker,
        findings_packaging as _pack,
        findings_plugins as _plugins,
        findings_rbac as _rbac,
        findings_terminal as _term,
        findings_transport as _trans,
        findings_update as _upd,
    )

    return [
        # auth/secrets (C3)
        _auth.local_password_admins_exist,
        _auth.admin_without_webauthn,
        _auth.recovery_codes_never_viewed,
        _auth.passkey_synced,
        _auth.signcount_regression_recent,
        _auth.tls_self_signed,
        _auth.secrets_root_key_colocated,
        _auth.vault_unreachable,
        _auth.mfa_recency_disabled_for_high_risk,
        # transport (C1)
        _trans.hosts_unreachable_recently,
        _trans.hosts_with_expired_certs,
        # rbac/control plane (C2)
        _rbac.no_owner_account,
        _rbac.stale_pending_approvals,
        _rbac.excessive_admin_count,
        # update engine (C4)
        _upd.update_engine_not_configured,
        # docker (C7)
        _docker.docker_management_not_implemented,
        # plugins (C6)
        _plugins.plugin_system_stub_only,
        # terminal (C9)
        _term.terminal_not_implemented,
        # packaging (C11)
        _pack.install_script_template_missing,
        _pack.release_signing_not_configured,
    ]


# Eagerly populate the registry on package import.
ALL_FINDINGS: list[Callable[..., Awaitable["Finding | None"]]] = _registry()


__all__ = ["Finding", "PostureFindingRow", "Severity", "ALL_FINDINGS", "SEVERITY_ORDER"]
