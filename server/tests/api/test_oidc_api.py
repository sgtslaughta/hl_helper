"""API-level tests for OIDC endpoints (Phase 4.4)."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import AsyncGenerator, Callable
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.app.api.app import create_app
from server.app.auth.oidc.client import OidcClient, OidcStateStore
from server.app.auth.sessions import SessionService
from server.app.events.bus import Bus
from server.app.models import OidcAccountLink, OidcProvider, User
from server.app.models.base import Base
from server.app.models.user import UserKind
from server.app.settings.config import load_settings
from server.tests._helpers.app_state import make_test_app_state


# --------------------------------------------------------------------------- #
# Mock IdP
# --------------------------------------------------------------------------- #


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_uint(n: int) -> str:
    blen = (n.bit_length() + 7) // 8
    return _b64u(n.to_bytes(blen, "big"))


class IdP:
    def __init__(self, issuer: str = "https://idp.test") -> None:
        self.issuer = issuer
        self.kid = "kid-1"
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.next_token: dict | None = None
        self.audience = "client-abc"
        self.next_id_token_kwargs: dict = {}

    def _jwks(self) -> dict:
        pub = self.key.public_key().public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": self.kid,
                    "use": "sig",
                    "alg": "RS256",
                    "n": _b64u_uint(pub.n),
                    "e": _b64u_uint(pub.e),
                }
            ]
        }

    def mint_id_token(self, *, sub: str, nonce: str, email: str, name: str = "Test User") -> str:
        header = {"alg": "RS256", "kid": self.kid, "typ": "JWT"}
        payload = {
            "iss": self.issuer,
            "sub": sub,
            "aud": self.audience,
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "nonce": nonce,
            "email": email,
            "name": name,
        }
        h_b = _b64u(json.dumps(header, separators=(",", ":")).encode())
        p_b = _b64u(json.dumps(payload, separators=(",", ":")).encode())
        sig = self.key.sign(f"{h_b}.{p_b}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
        return f"{h_b}.{p_b}.{_b64u(sig)}"

    def handler(self) -> Callable[[httpx.Request], httpx.Response]:
        def _h(req: httpx.Request) -> httpx.Response:
            url = str(req.url)
            if url.endswith("/.well-known/openid-configuration"):
                return httpx.Response(
                    200,
                    json={
                        "issuer": self.issuer,
                        "authorization_endpoint": f"{self.issuer}/authorize",
                        "token_endpoint": f"{self.issuer}/token",
                        "userinfo_endpoint": f"{self.issuer}/userinfo",
                        "jwks_uri": f"{self.issuer}/jwks",
                    },
                )
            if url.endswith("/jwks"):
                return httpx.Response(200, json=self._jwks())
            if url.endswith("/token"):
                if self.next_token is None:
                    return httpx.Response(400, json={"error": "no_token"})
                t, self.next_token = self.next_token, None
                return httpx.Response(200, json=t)
            return httpx.Response(404)
        return _h


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
async def sm(tmp_path: Path) -> async_sessionmaker:
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'oidc.db'}", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def idp() -> IdP:
    return IdP()


@pytest.fixture
async def app_with_state(sm: async_sessionmaker, idp: IdP, monkeypatch: pytest.MonkeyPatch):
    """FastAPI app wired with an in-memory IdP-backed OidcClient."""
    # Force admin token to a known value for tests
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", "test-admin-token")

    app = create_app()
    bus = Bus()
    session_service = SessionService(sessionmaker=sm, bus=bus)
    await session_service.start()
    app.state.app_state = make_test_app_state(
        sessionmaker=sm,
        session_service=session_service,
        bus=bus,
        create_session_service=False,
    )
    # Inject IdP-backed httpx client
    transport = httpx.MockTransport(idp.handler())
    app.state.oidc_client = OidcClient(http_client=httpx.AsyncClient(transport=transport))
    app.state.oidc_state_store = OidcStateStore()
    yield app
    await session_service.stop()


@pytest.fixture
async def client(app_with_state) -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_state),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.fixture
async def provider_row(sm: async_sessionmaker, idp: IdP) -> OidcProvider:
    p = OidcProvider(
        name="test-idp",
        issuer=idp.issuer,
        client_id=idp.audience,
        scopes=["openid", "email", "profile"],
        claim_mappings={"email": "email", "display_name": "name", "groups": []},
        button_asset="/static/test.svg",
    )
    async with sm() as s:
        s.add(p)
        await s.commit()
        await s.refresh(p)
    return p


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_list_providers_public(client: httpx.AsyncClient, provider_row: OidcProvider) -> None:
    r = await client.get("/v1/oidc/providers")
    assert r.status_code == 200
    rows = r.json()
    assert any(p["id"] == provider_row.id and p["name"] == "test-idp" for p in rows)


@pytest.mark.asyncio
async def test_list_providers_excludes_disabled(
    client: httpx.AsyncClient, sm: async_sessionmaker, idp: IdP
) -> None:
    p = OidcProvider(
        name="disabled-idp",
        issuer=idp.issuer,
        client_id="cid",
        scopes=["openid"],
        claim_mappings={},
        enabled=False,
    )
    async with sm() as s:
        s.add(p)
        await s.commit()
    r = await client.get("/v1/oidc/providers")
    assert r.status_code == 200
    assert all(p["name"] != "disabled-idp" for p in r.json())


@pytest.mark.asyncio
async def test_create_provider_requires_admin(client: httpx.AsyncClient, idp: IdP) -> None:
    body = {"name": "new", "issuer": idp.issuer, "client_id": "cid"}
    r = await client.post("/v1/oidc/providers", json=body)
    assert r.status_code == 401  # missing bearer
    r = await client.post(
        "/v1/oidc/providers", json=body, headers={"Authorization": "Bearer wrong"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_provider_admin_ok(client: httpx.AsyncClient, idp: IdP) -> None:
    body = {"name": "new-idp", "issuer": idp.issuer, "client_id": "cid"}
    r = await client.post(
        "/v1/oidc/providers",
        json=body,
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["name"] == "new-idp"


@pytest.mark.asyncio
async def test_test_provider_diagnostics(
    client: httpx.AsyncClient, provider_row: OidcProvider
) -> None:
    r = await client.post(
        f"/v1/oidc/providers/{provider_row.id}/test",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["discovery_ok"] is True
    assert j["jwks_ok"] is True
    assert j["n_keys"] >= 1


@pytest.mark.asyncio
async def test_auth_start_redirects(client: httpx.AsyncClient, provider_row: OidcProvider) -> None:
    r = await client.get(f"/v1/auth/oidc/{provider_row.id}/start", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    parts = urlparse(loc)
    qs = parse_qs(parts.query)
    assert qs["code_challenge_method"] == ["S256"]
    assert "state" in qs and "nonce" in qs


@pytest.mark.asyncio
async def test_auth_start_unknown_provider(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/auth/oidc/unknown/start", follow_redirects=False)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_callback_jit_login(
    client: httpx.AsyncClient,
    provider_row: OidcProvider,
    idp: IdP,
    sm: async_sessionmaker,
    app_with_state,
) -> None:
    # Step 1: start, capture state + verifier from state store
    r = await client.get(f"/v1/auth/oidc/{provider_row.id}/start", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    qs = parse_qs(urlparse(loc).query)
    state = qs["state"][0]
    nonce = qs["nonce"][0]

    # Step 2: arrange IdP token response
    id_token = idp.mint_id_token(sub="ext-1", nonce=nonce, email="newuser@x", name="New U")
    idp.next_token = {"access_token": "at", "id_token": id_token, "token_type": "Bearer"}

    # Step 3: hit callback
    r2 = await client.get(
        f"/v1/auth/oidc/{provider_row.id}/callback",
        params={"code": "the-code", "state": state},
        follow_redirects=False,
    )
    assert r2.status_code == 302, r2.text
    assert r2.headers["location"] == "/"
    settings = load_settings()
    assert settings.session_cookie_name in r2.cookies

    # User created
    from sqlalchemy import select
    async with sm() as s:
        u = await s.scalar(select(User).where(User.email == "newuser@x"))
        assert u is not None
        link = await s.scalar(
            select(OidcAccountLink).where(OidcAccountLink.subject == "ext-1")
        )
        assert link is not None and link.user_id == u.id


@pytest.mark.asyncio
async def test_callback_state_replay_rejected(
    client: httpx.AsyncClient,
    provider_row: OidcProvider,
    idp: IdP,
) -> None:
    r = await client.get(f"/v1/auth/oidc/{provider_row.id}/start", follow_redirects=False)
    qs = parse_qs(urlparse(r.headers["location"]).query)
    state = qs["state"][0]
    nonce = qs["nonce"][0]
    idp.next_token = {
        "access_token": "at",
        "id_token": idp.mint_id_token(sub="ext-2", nonce=nonce, email="dupe@x"),
    }
    r2 = await client.get(
        f"/v1/auth/oidc/{provider_row.id}/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    assert r2.status_code in (302, 400)
    # Replay
    r3 = await client.get(
        f"/v1/auth/oidc/{provider_row.id}/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    assert r3.status_code == 400
    assert "state_not_found" in r3.text


@pytest.mark.asyncio
async def test_callback_missing_state(
    client: httpx.AsyncClient, provider_row: OidcProvider
) -> None:
    r = await client.get(
        f"/v1/auth/oidc/{provider_row.id}/callback",
        params={"code": "c"},
        follow_redirects=False,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_link_endpoint_requires_auth(client: httpx.AsyncClient, provider_row: OidcProvider) -> None:
    r = await client.post(
        "/v1/auth/oidc/link", json={"provider_id": provider_row.id}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_link_endpoint_authenticated(
    client: httpx.AsyncClient,
    provider_row: OidcProvider,
    sm: async_sessionmaker,
    app_with_state,
) -> None:
    # Pre-create user + session
    from uuid import uuid4
    user = User(id=str(uuid4()), email="linkuser@x", kind=UserKind.LOCAL, password_hash="pw")
    async with sm() as s:
        s.add(user)
        await s.commit()
    svc = app_with_state.state.app_state.session_service
    from server.app.auth.sessions import make_request_meta
    issue = await svc.issue(user, "none", make_request_meta("127.0.0.1", "ua"))
    r = await client.post(
        "/v1/auth/oidc/link",
        json={"provider_id": provider_row.id},
        headers={"Authorization": f"Bearer {issue.raw}"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["auth_url"].startswith("https://idp.test/authorize?")
