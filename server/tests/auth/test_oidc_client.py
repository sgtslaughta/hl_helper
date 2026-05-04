"""Tests for OIDC client core (Phase 4.1).

Uses httpx.MockTransport to simulate an IdP and cryptography to mint real
RS256 JWTs.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import time
from typing import Callable

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from server.app.auth.oidc.client import (
    OidcClient,
    OidcError,
    OidcStateStore,
    StateRecord,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_uint(n: int) -> str:
    blen = (n.bit_length() + 7) // 8
    return _b64u(n.to_bytes(blen, "big"))


def _make_jwk(key: rsa.RSAPrivateKey, kid: str) -> dict:
    pub = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64u_uint(pub.n),
        "e": _b64u_uint(pub.e),
    }


def _sign_rs256(key: rsa.RSAPrivateKey, header: dict, payload: dict) -> str:
    h_b = _b64u(json.dumps(header, separators=(",", ":")).encode())
    p_b = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h_b}.{p_b}".encode("ascii")
    sig = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{h_b}.{p_b}.{_b64u(sig)}"


@dataclasses.dataclass
class FakeProvider:
    id: str = "p1"
    issuer: str = "https://idp.example"
    client_id: str = "client-abc"
    scopes: list[str] | None = None
    oauth2_only: bool = False
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None

    def __post_init__(self) -> None:
        if self.scopes is None:
            self.scopes = ["openid", "email", "profile"]


class IdP:
    """Tiny in-memory IdP. Mounted via httpx.MockTransport."""

    def __init__(self) -> None:
        self.kid = "kid-1"
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.issuer = "https://idp.example"
        self.discovery_calls = 0
        self.jwks_calls = 0
        self.jwks_extra_keys: list[dict] = []
        self.next_token: dict | None = None

    def discovery_doc(self) -> dict:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "userinfo_endpoint": f"{self.issuer}/userinfo",
            "jwks_uri": f"{self.issuer}/jwks",
        }

    def jwks_doc(self) -> dict:
        return {"keys": [_make_jwk(self.key, self.kid), *self.jwks_extra_keys]}

    def mint_id_token(
        self,
        *,
        sub: str = "user-1",
        aud: str = "client-abc",
        nonce: str | None = "n1",
        exp_in: int = 300,
        kid: str | None = None,
        extra: dict | None = None,
    ) -> str:
        header = {"alg": "RS256", "kid": kid or self.kid, "typ": "JWT"}
        payload = {
            "iss": self.issuer,
            "sub": sub,
            "aud": aud,
            "iat": int(time.time()),
            "exp": int(time.time()) + exp_in,
        }
        if nonce is not None:
            payload["nonce"] = nonce
        if extra:
            payload.update(extra)
        return _sign_rs256(self.key, header, payload)

    def handler(self) -> Callable[[httpx.Request], httpx.Response]:
        def _h(req: httpx.Request) -> httpx.Response:
            url = str(req.url)
            if url.endswith("/.well-known/openid-configuration"):
                self.discovery_calls += 1
                return httpx.Response(200, json=self.discovery_doc())
            if url.endswith("/jwks"):
                self.jwks_calls += 1
                return httpx.Response(200, json=self.jwks_doc())
            if url.endswith("/token"):
                if self.next_token is None:
                    return httpx.Response(400, json={"error": "no_token"})
                tok, self.next_token = self.next_token, None
                return httpx.Response(200, json=tok)
            return httpx.Response(404)
        return _h


@pytest.fixture
def idp() -> IdP:
    return IdP()


@pytest.fixture
def client(idp: IdP) -> OidcClient:
    transport = httpx.MockTransport(idp.handler())
    http = httpx.AsyncClient(transport=transport)
    return OidcClient(http_client=http)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_discovery_caches_and_refreshes(client: OidcClient, idp: IdP, provider: FakeProvider) -> None:
    doc1 = await client.discover(provider)
    doc2 = await client.discover(provider)
    assert idp.discovery_calls == 1
    assert doc1["issuer"] == idp.issuer == doc2["issuer"]
    # Force refresh — should re-fetch
    await client.discover(provider, force=True)
    assert idp.discovery_calls == 2


@pytest.mark.asyncio
async def test_discovery_cache_expires(idp: IdP, provider: FakeProvider) -> None:
    transport = httpx.MockTransport(idp.handler())
    c = OidcClient(http_client=httpx.AsyncClient(transport=transport), discovery_ttl_s=0)
    await c.discover(provider)
    await c.discover(provider)
    assert idp.discovery_calls == 2


@pytest.mark.asyncio
async def test_jwks_rotate(client: OidcClient, idp: IdP, provider: FakeProvider) -> None:
    # First fetch caches kid-1
    await client.jwks(provider)
    assert idp.jwks_calls == 1
    # Rotate — issuer publishes new kid; first lookup should miss cache and refetch
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    idp.kid = "kid-2"
    idp.key = new_key
    token = idp.mint_id_token()
    claims = await client.verify_id_token(provider, token, nonce="n1")
    assert claims["sub"] == "user-1"
    # Original cache had only kid-1; verify forced a refresh
    assert idp.jwks_calls >= 2


@pytest.mark.asyncio
async def test_auth_url_pkce(client: OidcClient, provider: FakeProvider) -> None:
    url, cv = client.auth_url(
        provider,
        state="s1",
        nonce="n1",
        redirect_uri="https://app/cb",
        authorization_endpoint="https://idp.example/authorize",
    )
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "state=s1" in url
    assert "nonce=n1" in url
    assert len(cv) >= 40


@pytest.mark.asyncio
async def test_exchange_happy(client: OidcClient, idp: IdP, provider: FakeProvider) -> None:
    idp.next_token = {"access_token": "at", "id_token": idp.mint_id_token(), "token_type": "Bearer"}
    tokens = await client.exchange(
        provider,
        code="auth-code",
        code_verifier="cv",
        redirect_uri="https://app/cb",
        token_endpoint="https://idp.example/token",
    )
    assert tokens["access_token"] == "at"


@pytest.mark.asyncio
async def test_id_token_iss_mismatch(client: OidcClient, idp: IdP, provider: FakeProvider) -> None:
    bad = idp.mint_id_token()
    # Build a fresh provider with different issuer
    p = FakeProvider(issuer="https://other.example")
    with pytest.raises(OidcError, match="iss_mismatch"):
        await client.verify_id_token(p, bad, nonce="n1")


@pytest.mark.asyncio
async def test_id_token_aud_mismatch(client: OidcClient, idp: IdP, provider: FakeProvider) -> None:
    bad = idp.mint_id_token(aud="someone-else")
    with pytest.raises(OidcError, match="aud_mismatch"):
        await client.verify_id_token(provider, bad, nonce="n1")


@pytest.mark.asyncio
async def test_id_token_nonce_mismatch(client: OidcClient, idp: IdP, provider: FakeProvider) -> None:
    tok = idp.mint_id_token(nonce="n1")
    with pytest.raises(OidcError, match="nonce_mismatch"):
        await client.verify_id_token(provider, tok, nonce="other")


@pytest.mark.asyncio
async def test_id_token_expired(client: OidcClient, idp: IdP, provider: FakeProvider) -> None:
    tok = idp.mint_id_token(exp_in=-3600)
    with pytest.raises(OidcError, match="token_expired"):
        await client.verify_id_token(provider, tok, nonce="n1")


@pytest.mark.asyncio
async def test_id_token_alg_none_rejected(client: OidcClient, idp: IdP, provider: FakeProvider) -> None:
    header = {"alg": "none", "kid": idp.kid, "typ": "JWT"}
    payload = {"iss": idp.issuer, "sub": "u", "aud": provider.client_id, "exp": int(time.time()) + 60, "nonce": "n1"}
    h_b = _b64u(json.dumps(header, separators=(",", ":")).encode())
    p_b = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    bad = f"{h_b}.{p_b}."
    with pytest.raises(OidcError, match="alg_none_disallowed"):
        await client.verify_id_token(provider, bad, nonce="n1")


@pytest.mark.asyncio
async def test_state_store_consume_once(client: OidcClient) -> None:
    store = OidcStateStore(ttl_seconds=60)
    rec = StateRecord(
        provider_id="p1",
        code_verifier="cv",
        nonce="n1",
        redirect_uri="https://app/cb",
        created_at=time.time(),
    )
    await store.put("state-x", rec)
    got = await store.consume("state-x")
    assert got.code_verifier == "cv"
    with pytest.raises(OidcError, match="state_not_found"):
        await store.consume("state-x")  # replay


@pytest.mark.asyncio
async def test_state_store_expiry() -> None:
    store = OidcStateStore(ttl_seconds=1)
    rec = StateRecord(
        provider_id="p1",
        code_verifier="cv",
        nonce="n1",
        redirect_uri="https://app/cb",
        created_at=time.time() - 2,  # already past TTL
    )
    await store.put("state-y", rec)
    with pytest.raises(OidcError, match="state_expired"):
        await store.consume("state-y")


@pytest.mark.asyncio
async def test_kid_required_when_multiple_jwks(
    client: OidcClient, idp: IdP, provider: FakeProvider
) -> None:
    """If the token has no kid and the JWKS has >1 key, refuse to guess."""
    # Add a second key so JWKS has 2 entries
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    idp.jwks_extra_keys = [_make_jwk(other, "kid-2")]

    # Mint a token signed by idp.key but without a kid header
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": idp.issuer,
        "sub": "u",
        "aud": provider.client_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
        "nonce": "n1",
    }
    h_b = _b64u(json.dumps(header, separators=(",", ":")).encode())
    p_b = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    sig = idp.key.sign(f"{h_b}.{p_b}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    tok = f"{h_b}.{p_b}.{_b64u(sig)}"
    with pytest.raises(OidcError, match="kid required"):
        await client.verify_id_token(provider, tok, nonce="n1")


@pytest.mark.asyncio
async def test_invalid_signature(client: OidcClient, idp: IdP, provider: FakeProvider) -> None:
    """Tampered payload triggers signature failure."""
    tok = idp.mint_id_token()
    h, p, s = tok.split(".")
    # Flip one byte of payload
    bad_payload = json.loads(base64.urlsafe_b64decode(p + "==").decode())
    bad_payload["sub"] = "tampered"
    p_new = _b64u(json.dumps(bad_payload, separators=(",", ":")).encode())
    bad_tok = f"{h}.{p_new}.{s}"
    with pytest.raises(OidcError, match="invalid_signature"):
        await client.verify_id_token(provider, bad_tok, nonce="n1")
