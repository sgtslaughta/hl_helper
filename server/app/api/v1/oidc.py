"""OIDC HTTP endpoints (Phase 4.4).

Routes:
  GET    /v1/oidc/providers           — public list of enabled providers
  POST   /v1/oidc/providers           — admin: create/update
  POST   /v1/oidc/providers/{id}/test — admin: discovery + jwks diagnostics
  GET    /v1/auth/oidc/{id}/start     — start authorization code flow
  GET    /v1/auth/oidc/{id}/callback  — finish authorization code flow
  POST   /v1/auth/oidc/link           — authenticated user begins link flow
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.auth.oidc.claims import (
    OidcLinkError,
    apply_claim_mappings,
    jit_provision,
)
from server.app.auth.oidc.client import (
    OidcClient,
    OidcError,
    OidcStateStore,
    StateRecord,
)
from server.app.auth.sessions import make_request_meta
from server.app.deps import current_principal
from server.app.models import OidcProvider, User
from server.app.rbac.provider import Principal
from server.app.settings.config import load_settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["oidc"])


# --------------------------------------------------------------------------- #
# Pydantic
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _get_client(request: Request) -> OidcClient:
    """Lazy singleton OidcClient bound to app.state."""
    app = request.app
    client = getattr(app.state, "oidc_client", None)
    if client is None:
        client = OidcClient()
        app.state.oidc_client = client
    return client


def _get_state_store(request: Request) -> OidcStateStore:
    app = request.app
    store = getattr(app.state, "oidc_state_store", None)
    if store is None:
        store = OidcStateStore()
        app.state.oidc_state_store = store
    return store


async def _audit(
    app_state: Any, *, actor: str, action: str, subject: str, payload: dict[str, Any]
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


async def _resolve_endpoints(client: OidcClient, provider: OidcProvider) -> dict[str, Any]:
    """Return discovery doc dict (synthetic for oauth2_only)."""
    return await client.discover(provider)


def _default_redirect_uri(request: Request, provider_id: str) -> str:
    """Build the OIDC callback URL.

    Pin the host from ``settings.public_url`` if configured to avoid
    Host-header injection (an attacker setting ``Host:`` on the start
    request would otherwise control the redirect_uri the IdP receives,
    which is part of the security boundary of the auth code flow).
    """
    settings = load_settings()
    base = (settings.public_url or "").rstrip("/")
    if not base:
        log.warning("oidc_redirect_uri_uses_request_base_url")
        base = f"{request.base_url}".rstrip("/")
    return f"{base}/v1/auth/oidc/{provider_id}/callback"


# --------------------------------------------------------------------------- #
# Provider management
# --------------------------------------------------------------------------- #


@router.get("/oidc/providers", status_code=200)
async def list_providers(request: Request) -> list[ProviderPublic]:
    """Public list of enabled providers (id, name, button_asset)."""
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as s:
        rows = (
            await s.execute(
                select(OidcProvider).where(OidcProvider.enabled.is_(True))
            )
        ).scalars().all()
    return [
        ProviderPublic(
            id=p.id, name=p.name, button_asset=p.button_asset, preset_kind=p.preset_kind
        )
        for p in rows
    ]


@router.post(
    "/oidc/providers",
    status_code=201,
    dependencies=[Depends(admin_required)],
)
async def create_provider(body: ProviderCreate, request: Request) -> ProviderPublic:
    """Create an OIDC provider (admin)."""
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as s:
        existing = await s.scalar(select(OidcProvider).where(OidcProvider.name == body.name))
        if existing is not None:
            raise HTTPException(status_code=409, detail="provider_name_taken")
        prov = OidcProvider(
            name=body.name,
            issuer=body.issuer,
            client_id=body.client_id,
            client_secret_ref=body.client_secret_ref,
            scopes=body.scopes or ["openid", "email", "profile"],
            claim_mappings=body.claim_mappings or {},
            enabled=body.enabled,
            preset_kind=body.preset_kind,
            oauth2_only=body.oauth2_only,
            authorization_endpoint=body.authorization_endpoint,
            token_endpoint=body.token_endpoint,
            userinfo_endpoint=body.userinfo_endpoint,
            jwks_uri=body.jwks_uri,
            button_asset=body.button_asset,
        )
        s.add(prov)
        await s.commit()
        await s.refresh(prov)
    await _audit(
        app_state,
        actor="admin",
        action="oidc.provider.create",
        subject=prov.id,
        payload={"name": prov.name, "issuer": prov.issuer},
    )
    return ProviderPublic(
        id=prov.id, name=prov.name, button_asset=prov.button_asset, preset_kind=prov.preset_kind
    )


@router.post(
    "/oidc/providers/{provider_id}/test",
    status_code=200,
    dependencies=[Depends(admin_required)],
)
async def test_provider(provider_id: str, request: Request) -> ProviderTestResult:
    """Run discovery + JWKS fetch and return diagnostics (admin)."""
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as s:
        prov = await s.scalar(select(OidcProvider).where(OidcProvider.id == provider_id))
    if prov is None:
        raise HTTPException(status_code=404, detail="provider_not_found")
    client = _get_client(request)
    try:
        doc = await client.discover(prov, force=True)
        if prov.oauth2_only:
            return ProviderTestResult(
                discovery_ok=True, jwks_ok=False, issuer=doc.get("issuer"), n_keys=0
            )
        jwks = await client.jwks(prov, force=True)
        return ProviderTestResult(
            discovery_ok=True,
            jwks_ok=True,
            issuer=doc.get("issuer"),
            n_keys=len(jwks.get("keys", [])),
        )
    except OidcError as e:
        return ProviderTestResult(discovery_ok=False, jwks_ok=False, error=str(e))


# --------------------------------------------------------------------------- #
# Auth flow
# --------------------------------------------------------------------------- #


@router.get("/auth/oidc/{provider_id}/start", status_code=302)
async def auth_start(provider_id: str, request: Request) -> Response:
    """Begin authorization code flow — redirect to IdP authorize URL."""
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as s:
        prov = await s.scalar(
            select(OidcProvider).where(
                OidcProvider.id == provider_id, OidcProvider.enabled.is_(True)
            )
        )
    if prov is None:
        raise HTTPException(status_code=404, detail="provider_not_found")

    client = _get_client(request)
    store = _get_state_store(request)

    try:
        doc = await _resolve_endpoints(client, prov)
    except OidcError as e:
        raise HTTPException(status_code=502, detail=f"discovery_failed:{e}") from e

    auth_endpoint = doc.get("authorization_endpoint") or prov.authorization_endpoint
    if not auth_endpoint:
        raise HTTPException(status_code=500, detail="no_authorization_endpoint")

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    redirect_uri = _default_redirect_uri(request, prov.id)
    url, code_verifier = client.auth_url(
        prov,
        state=state,
        nonce=nonce,
        redirect_uri=redirect_uri,
        authorization_endpoint=auth_endpoint,
    )
    await store.put(
        state,
        StateRecord(
            provider_id=prov.id,
            code_verifier=code_verifier,
            nonce=nonce,
            redirect_uri=redirect_uri,
            created_at=time.time(),
            mode="login",
        ),
    )
    return Response(status_code=302, headers={"Location": url})


@router.get("/auth/oidc/{provider_id}/callback", status_code=302)
async def auth_callback(
    provider_id: str,
    request: Request,
) -> Response:
    """Finish authorization code flow."""
    app_state = get_app_state(request)
    qs = request.query_params
    code = qs.get("code")
    state = qs.get("state")
    err = qs.get("error")
    if err:
        await _audit(
            app_state, actor="anonymous", action="auth.oidc.failed", subject=provider_id,
            payload={"reason": "idp_error", "error": err},
        )
        raise HTTPException(status_code=400, detail=f"idp_error:{err}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing_code_or_state")

    store = _get_state_store(request)
    try:
        rec = await store.consume(state)
    except OidcError as e:
        await _audit(
            app_state, actor="anonymous", action="auth.oidc.failed", subject=provider_id,
            payload={"reason": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e

    if rec.provider_id != provider_id:
        raise HTTPException(status_code=400, detail="provider_mismatch")

    async with app_state.sessionmaker() as s:
        prov = await s.scalar(select(OidcProvider).where(OidcProvider.id == provider_id))
    if prov is None:
        raise HTTPException(status_code=404, detail="provider_not_found")

    client = _get_client(request)
    try:
        doc = await _resolve_endpoints(client, prov)
        token_endpoint = doc.get("token_endpoint") or prov.token_endpoint
        # Resolve confidential-client secret if the provider has a SecretRef.
        # Public clients (PKCE-only) leave client_secret_ref unset.
        client_secret: str | None = None
        if prov.client_secret_ref:
            backend = app_state.secrets_broker
            if backend is None:
                raise HTTPException(
                    status_code=503, detail="secrets_broker_unavailable"
                )
            from server.app.secrets.ref import SecretRef
            ref = SecretRef.parse(prov.client_secret_ref)
            path = f"{ref.path}#{ref.field}" if ref.field else ref.path
            # Server-side lookup — bypass the user-facing handle / re-auth gate.
            value = await backend.get(path)
            client_secret = value.decode("utf-8")
        tokens = await client.exchange(
            prov,
            code=code,
            code_verifier=rec.code_verifier,
            redirect_uri=rec.redirect_uri,
            token_endpoint=token_endpoint,
            client_secret=client_secret,
        )
        id_token = tokens.get("id_token")
        if id_token is None and not prov.oauth2_only:
            raise OidcError("no_id_token")

        if id_token is not None:
            claims = await client.verify_id_token(prov, id_token, nonce=rec.nonce)
        else:
            # OAuth2-only providers (GitHub) — claims via userinfo
            access_token = tokens.get("access_token")
            if not access_token:
                raise OidcError("no_access_token")
            claims = await client.get_userinfo(prov, access_token)
            if "sub" not in claims:
                # GitHub returns numeric "id"
                gh_id = claims.get("id")
                if gh_id is None:
                    raise OidcError("missing_subject")
                claims["sub"] = str(gh_id)

        mapped = apply_claim_mappings(claims, prov.claim_mappings or {})

        sub = claims.get("sub")
        if not sub:
            raise OidcError("missing_subject")

        # Link mode → just create link for current user
        if rec.mode == "link" and rec.user_id:
            from server.app.auth.oidc.claims import link_account
            async with app_state.sessionmaker() as s:
                user = await s.scalar(select(User).where(User.id == rec.user_id))
            if user is None:
                raise HTTPException(status_code=404, detail="user_not_found")
            try:
                await link_account(
                    app_state.sessionmaker, user, prov, subject=str(sub), email=mapped.email
                )
            except OidcLinkError as e:
                raise HTTPException(status_code=409, detail=str(e)) from e
            await _audit(
                app_state, actor=user.id, action="auth.oidc.link", subject=user.id,
                payload={"provider_id": prov.id, "subject": str(sub)},
            )
            return Response(status_code=302, headers={"Location": "/"})

        # Login mode — JIT provision + issue session
        user = await jit_provision(app_state.sessionmaker, prov, claims, mapped)
    except OidcError as e:
        await _audit(
            app_state, actor="anonymous", action="auth.oidc.failed", subject=provider_id,
            payload={"reason": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OidcLinkError as e:
        await _audit(
            app_state, actor="anonymous", action="auth.oidc.failed", subject=provider_id,
            payload={"reason": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e

    settings = load_settings()
    if app_state.session_service is None:
        raise HTTPException(status_code=503, detail="session_service_unavailable")
    meta = make_request_meta(
        ip=request.client.host if request.client else "0.0.0.0",
        ua=request.headers.get("user-agent", ""),
    )
    issue = await app_state.session_service.issue(user, "oidc", meta)
    csrf = secrets.token_urlsafe(32)
    await _audit(
        app_state, actor=user.id, action="auth.oidc.success", subject=user.id,
        payload={"provider_id": prov.id, "subject": str(sub)},
    )

    # Coerce expires_at to UTC for cookie max_age computation; SQLite/legacy
    # rows can return naive datetimes which would crash the subtraction.
    expires_at = issue.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())

    response = Response(status_code=302, headers={"Location": "/"})
    response.set_cookie(
        key=settings.session_cookie_name,
        value=issue.raw,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=max_age,
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=max_age,
    )
    return response


@router.post("/auth/oidc/link", status_code=200)
async def auth_link(
    body: LinkStartRequest,
    request: Request,
    principal: Annotated[Principal | None, Depends(current_principal)],
) -> LinkStartResponse:
    """Authenticated user begins an OIDC account-link flow."""
    if principal is None or principal.user_id is None:
        raise HTTPException(status_code=401, detail="unauthenticated")
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as s:
        prov = await s.scalar(
            select(OidcProvider).where(
                OidcProvider.id == body.provider_id, OidcProvider.enabled.is_(True)
            )
        )
    if prov is None:
        raise HTTPException(status_code=404, detail="provider_not_found")

    client = _get_client(request)
    store = _get_state_store(request)
    doc = await _resolve_endpoints(client, prov)
    auth_endpoint = doc.get("authorization_endpoint") or prov.authorization_endpoint
    if not auth_endpoint:
        raise HTTPException(status_code=500, detail="no_authorization_endpoint")

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    redirect_uri = body.redirect_uri or _default_redirect_uri(request, prov.id)
    url, code_verifier = client.auth_url(
        prov,
        state=state,
        nonce=nonce,
        redirect_uri=redirect_uri,
        authorization_endpoint=auth_endpoint,
    )
    await store.put(
        state,
        StateRecord(
            provider_id=prov.id,
            code_verifier=code_verifier,
            nonce=nonce,
            redirect_uri=redirect_uri,
            created_at=time.time(),
            mode="link",
            user_id=principal.user_id,
        ),
    )
    return LinkStartResponse(auth_url=url)
