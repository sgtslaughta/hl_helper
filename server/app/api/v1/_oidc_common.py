"""Shared schemas + helpers for OIDC endpoints (provider mgmt, auth flow, link)."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import Request
from pydantic import BaseModel

from server.app.auth.oidc.client import OidcClient, OidcStateStore
from server.app.models import OidcProvider
from server.app.settings.config import load_settings

log = structlog.get_logger(__name__)


# Pydantic schemas


class ProviderPublic(BaseModel):
    id: str
    name: str
    button_asset: str | None = None
    preset_kind: str | None = None


class ProviderCreate(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    issuer: str
    client_id: str
    client_secret_ref: str | None = None
    scopes: list[str] | None = None
    claim_mappings: dict[str, Any] | None = None
    enabled: bool = True
    preset_kind: str | None = None
    oauth2_only: bool = False
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None
    button_asset: str | None = None


class ProviderTestResult(BaseModel):
    discovery_ok: bool
    jwks_ok: bool
    issuer: str | None = None
    n_keys: int = 0
    error: str | None = None


class LinkStartRequest(BaseModel):
    model_config = {"extra": "forbid"}
    provider_id: str
    redirect_uri: str | None = None


class LinkStartResponse(BaseModel):
    auth_url: str


# Helpers


def get_client(request: Request) -> OidcClient:
    """Lazy singleton OidcClient bound to app.state."""
    app = request.app
    client = getattr(app.state, "oidc_client", None)
    if client is None:
        client = OidcClient()
        app.state.oidc_client = client
    return client


def get_state_store(request: Request) -> OidcStateStore:
    app = request.app
    store = getattr(app.state, "oidc_state_store", None)
    if store is None:
        store = OidcStateStore()
        app.state.oidc_state_store = store
    return store


async def audit(
    app_state: Any,
    *,
    actor: str,
    action: str,
    subject: str,
    payload: dict[str, Any],
) -> None:
    if app_state.audit_chain is None:
        return
    async with app_state.sessionmaker() as s:
        try:
            await app_state.audit_chain.append(
                s, actor=actor, action=action, subject=subject, payload=payload
            )
            await s.commit()
        except Exception as e:  # pragma: no cover
            log.exception("audit_append_failed", exc=e)


async def resolve_endpoints(
    client: OidcClient, provider: OidcProvider
) -> dict[str, Any]:
    """Return discovery doc dict (synthetic for oauth2_only)."""
    return await client.discover(provider)


def default_redirect_uri(request: Request, provider_id: str) -> str:
    """Build the OIDC callback URL.

    Pin host from settings.public_url to avoid Host-header injection.
    """
    settings = load_settings()
    base = (settings.public_url or "").rstrip("/")
    if not base:
        log.warning("oidc_redirect_uri_uses_request_base_url")
        base = f"{request.base_url}".rstrip("/")
    return f"{base}/v1/auth/oidc/{provider_id}/callback"
