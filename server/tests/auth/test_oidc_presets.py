"""Tests for OIDC presets (Phase 4.2)."""

from __future__ import annotations

import pytest

from server.app.auth.oidc.presets import (
    PRESETS,
    REQUIRED_PRESET_KEYS,
    get_preset,
    list_presets,
)
from server.app.models.oidc_provider import OidcProvider


EXPECTED_KINDS = {
    "github",
    "gitlab",
    "google",
    "microsoft",
    "authentik",
    "keycloak",
    "authelia",
    "pocket_id",
    "zitadel",
}


def test_preset_count_and_names() -> None:
    assert set(PRESETS.keys()) == EXPECTED_KINDS
    assert set(list_presets()) == EXPECTED_KINDS


@pytest.mark.parametrize("kind", sorted(EXPECTED_KINDS))
def test_required_keys_present(kind: str) -> None:
    p = get_preset(kind)
    assert REQUIRED_PRESET_KEYS.issubset(p.keys())
    assert isinstance(p["scopes"], list) and p["scopes"]
    assert isinstance(p["claim_mappings"], dict)
    # All claim_mappings target keys must be present
    assert {"email", "display_name", "groups"}.issubset(p["claim_mappings"].keys())


def test_github_is_oauth2_only_with_explicit_endpoints() -> None:
    p = get_preset("github")
    assert p["oauth2_only"] is True
    assert p["authorization_endpoint"].startswith("https://")
    assert p["token_endpoint"].startswith("https://")


def test_oidc_providers_are_not_oauth2_only() -> None:
    for kind in EXPECTED_KINDS - {"github"}:
        assert get_preset(kind)["oauth2_only"] is False


def test_preset_instantiates_oidc_provider() -> None:
    for kind in EXPECTED_KINDS:
        p = get_preset(kind)
        prov = OidcProvider(
            name=p["name"] + f"-test-{kind}",
            issuer=p["issuer"] or "https://example/",
            client_id="cid",
            scopes=list(p["scopes"]),
            claim_mappings=dict(p["claim_mappings"]),
            preset_kind=p["kind"],
            oauth2_only=p["oauth2_only"],
            authorization_endpoint=p.get("authorization_endpoint"),
            token_endpoint=p.get("token_endpoint"),
            userinfo_endpoint=p.get("userinfo_endpoint"),
            jwks_uri=p.get("jwks_uri"),
            button_asset=p["button_asset"],
        )
        assert prov.preset_kind == kind
        assert prov.scopes == list(p["scopes"])


def test_unknown_preset_raises() -> None:
    with pytest.raises(KeyError):
        get_preset("not-a-real-idp")
