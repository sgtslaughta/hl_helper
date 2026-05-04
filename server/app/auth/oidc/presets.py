"""OIDC provider presets for major IdPs.

Each preset = dict with:
  - kind: identifier string (matches preset_kind on OidcProvider)
  - name: default display name
  - issuer: issuer URL (or for oauth2_only, the brand base URL)
  - scopes: list of scopes
  - claim_mappings: dict mapping {email,groups,display_name} -> claim path or list of paths
  - button_asset: relative path to a brand button asset
  - oauth2_only: True for OAuth2-only providers (e.g. GitHub) — endpoints explicit
  - authorization_endpoint / token_endpoint / userinfo_endpoint / jwks_uri:
      provided when oauth2_only is True

Claim paths support nested JSONPath-lite via dotted notation, e.g.
``realm_access.roles``.
"""

from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "github": {
        "kind": "github",
        "name": "GitHub",
        "issuer": "https://github.com",
        "scopes": ["read:user", "user:email", "read:org"],
        "claim_mappings": {
            "email": "email",
            "display_name": "name",
            "groups": [],  # GitHub orgs/teams require separate API call
        },
        "button_asset": "/static/oidc/github.svg",
        "oauth2_only": True,
        "authorization_endpoint": "https://github.com/login/oauth/authorize",
        "token_endpoint": "https://github.com/login/oauth/access_token",
        "userinfo_endpoint": "https://api.github.com/user",
        "jwks_uri": None,
    },
    "gitlab": {
        "kind": "gitlab",
        "name": "GitLab",
        "issuer": "https://gitlab.com",
        "scopes": ["openid", "email", "profile"],
        "claim_mappings": {
            "email": "email",
            "display_name": "name",
            "groups": "groups_direct",
        },
        "button_asset": "/static/oidc/gitlab.svg",
        "oauth2_only": False,
    },
    "google": {
        "kind": "google",
        "name": "Google",
        "issuer": "https://accounts.google.com",
        "scopes": ["openid", "email", "profile"],
        "claim_mappings": {
            "email": "email",
            "display_name": "name",
            "groups": [],
        },
        "button_asset": "/static/oidc/google.svg",
        "oauth2_only": False,
    },
    "microsoft": {
        "kind": "microsoft",
        "name": "Microsoft",
        "issuer": "https://login.microsoftonline.com/common/v2.0",
        "scopes": ["openid", "email", "profile"],
        "claim_mappings": {
            "email": "email",
            "display_name": "name",
            "groups": "groups",
        },
        "button_asset": "/static/oidc/microsoft.svg",
        "oauth2_only": False,
    },
    "authentik": {
        "kind": "authentik",
        "name": "Authentik",
        "issuer": "",  # tenant-specific; admin must fill
        "scopes": ["openid", "email", "profile"],
        "claim_mappings": {
            "email": "email",
            "display_name": "name",
            "groups": "groups",
        },
        "button_asset": "/static/oidc/authentik.svg",
        "oauth2_only": False,
    },
    "keycloak": {
        "kind": "keycloak",
        "name": "Keycloak",
        "issuer": "",  # tenant-specific; admin must fill (e.g. https://kc.example/realms/foo)
        "scopes": ["openid", "email", "profile"],
        "claim_mappings": {
            "email": "email",
            "display_name": "name",
            "groups": "realm_access.roles",
        },
        "button_asset": "/static/oidc/keycloak.svg",
        "oauth2_only": False,
    },
    "authelia": {
        "kind": "authelia",
        "name": "Authelia",
        "issuer": "",  # tenant-specific; admin must fill
        "scopes": ["openid", "email", "profile", "groups"],
        "claim_mappings": {
            "email": "email",
            "display_name": "name",
            "groups": "groups",
        },
        "button_asset": "/static/oidc/authelia.svg",
        "oauth2_only": False,
    },
    "pocket_id": {
        "kind": "pocket_id",
        "name": "Pocket ID",
        "issuer": "",  # tenant-specific
        "scopes": ["openid", "email", "profile", "groups"],
        "claim_mappings": {
            "email": "email",
            "display_name": "name",
            "groups": "groups",
        },
        "button_asset": "/static/oidc/pocket_id.svg",
        "oauth2_only": False,
    },
    "zitadel": {
        "kind": "zitadel",
        "name": "ZITADEL",
        "issuer": "",  # tenant-specific
        "scopes": ["openid", "email", "profile", "urn:zitadel:iam:org:project:roles"],
        "claim_mappings": {
            "email": "email",
            "display_name": "name",
            "groups": "urn:zitadel:iam:org:project:roles",
        },
        "button_asset": "/static/oidc/zitadel.svg",
        "oauth2_only": False,
    },
}


REQUIRED_PRESET_KEYS = {
    "kind",
    "name",
    "issuer",
    "scopes",
    "claim_mappings",
    "button_asset",
    "oauth2_only",
}


def get_preset(kind: str) -> dict[str, Any]:
    """Return preset dict by kind. Raises KeyError if unknown."""
    return PRESETS[kind]


def list_presets() -> list[str]:
    """Return list of preset kinds."""
    return list(PRESETS.keys())
