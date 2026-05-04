"""OIDC client core — discovery, JWKS, PKCE auth code, ID-token verify.

Self-contained implementation using httpx + cryptography (no authlib/pyjwt
dependency to avoid adding install-time dependencies).

JWT signature verification supports the algorithms most public IdPs use:
RS256 / RS384 / RS512 and ES256.

NOTE: ``OidcStateStore`` is in-process only and assumes a single worker.
Multi-worker deployments must replace it with a shared store (Redis/DB).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlencode

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

logger = logging.getLogger(__name__)

DISCOVERY_TTL_SECONDS = 3600
JWKS_TTL_SECONDS = 3600
STATE_TTL_SECONDS = 600


class OidcError(Exception):
    """Raised on any OIDC validation/protocol failure."""


# --------------------------------------------------------------------------- #
# Helpers — base64url + JWT
# --------------------------------------------------------------------------- #


def _b64u_decode(s: str) -> bytes:
    pad = 4 - (len(s) % 4)
    if pad and pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_int(s: str) -> int:
    return int.from_bytes(_b64u_decode(s), "big")


def _split_jwt(token: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    """Split a JWS compact token. Returns (header, payload, signing_input, signature)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise OidcError("malformed_jwt")
    h_b, p_b, s_b = parts
    try:
        header = json.loads(_b64u_decode(h_b))
        payload = json.loads(_b64u_decode(p_b))
    except Exception as e:
        raise OidcError(f"malformed_jwt: {e}") from e
    signing_input = f"{h_b}.{p_b}".encode("ascii")
    signature = _b64u_decode(s_b)
    return header, payload, signing_input, signature


def _jwk_to_public_key(jwk: dict[str, Any]) -> Any:
    """Convert a JWK dict to a cryptography public key object."""
    kty = jwk.get("kty")
    if kty == "RSA":
        n = _b64u_int(jwk["n"])
        e = _b64u_int(jwk["e"])
        return rsa.RSAPublicNumbers(e, n).public_key()
    if kty == "EC":
        crv = jwk.get("crv")
        curve_map = {"P-256": ec.SECP256R1(), "P-384": ec.SECP384R1(), "P-521": ec.SECP521R1()}
        if crv not in curve_map:
            raise OidcError(f"unsupported_ec_curve:{crv}")
        x = _b64u_int(jwk["x"])
        y = _b64u_int(jwk["y"])
        return ec.EllipticCurvePublicNumbers(x, y, curve_map[crv]).public_key()
    raise OidcError(f"unsupported_kty:{kty}")


_HASH_MAP = {
    "RS256": hashes.SHA256(),
    "RS384": hashes.SHA384(),
    "RS512": hashes.SHA512(),
    "ES256": hashes.SHA256(),
}

# Raw-signature half-length (one of r/s) per ES alg.
_ES_COORD_SIZE = {
    "ES256": 32,  # P-256 — 32-byte r and s
}


def _verify_jwt_signature(
    alg: str, public_key: Any, signing_input: bytes, signature: bytes
) -> None:
    h = _HASH_MAP.get(alg)
    if h is None:
        raise OidcError(f"unsupported_alg:{alg}")
    try:
        if alg.startswith("RS"):
            public_key.verify(signature, signing_input, padding.PKCS1v15(), h)
        elif alg == "ES256":
            coord = _ES_COORD_SIZE[alg]
            if len(signature) != 2 * coord:
                raise OidcError("invalid_signature")
            r = int.from_bytes(signature[:coord], "big")
            s = int.from_bytes(signature[coord:], "big")
            der = encode_dss_signature(r, s)
            public_key.verify(der, signing_input, ec.ECDSA(h))
        else:
            raise OidcError(f"unsupported_alg:{alg}")
    except InvalidSignature as e:
        raise OidcError("invalid_signature") from e


# --------------------------------------------------------------------------- #
# State store
# --------------------------------------------------------------------------- #


@dataclass
class StateRecord:
    """Authorization-flow state."""

    provider_id: str
    code_verifier: str
    nonce: str
    redirect_uri: str
    created_at: float
    mode: str = "login"  # or "link"
    user_id: str | None = None  # set when mode == "link"


class OidcStateStore:
    """In-process state store with TTL.

    Single-use: ``consume()`` removes the record on access. Records past TTL
    are rejected.
    """

    _GC_EVERY = 100

    def __init__(self, ttl_seconds: int = STATE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._records: dict[str, StateRecord] = {}
        self._lock = asyncio.Lock()
        self._call_count = 0

    async def _maybe_gc(self) -> None:
        self._call_count += 1
        if self._call_count % self._GC_EVERY == 0:
            await self.gc()

    async def put(self, state: str, rec: StateRecord) -> None:
        async with self._lock:
            self._records[state] = rec
        await self._maybe_gc()

    async def consume(self, state: str) -> StateRecord:
        async with self._lock:
            rec = self._records.pop(state, None)
        await self._maybe_gc()
        if rec is None:
            raise OidcError("state_not_found")
        if time.time() - rec.created_at > self._ttl:
            raise OidcError("state_expired")
        return rec

    async def gc(self) -> None:
        """Drop expired records."""
        now = time.time()
        async with self._lock:
            stale = [k for k, r in self._records.items() if now - r.created_at > self._ttl]
            for k in stale:
                del self._records[k]


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


@dataclass
class _Cached:
    value: dict[str, Any]
    fetched_at: float


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    cv = _b64u_encode(secrets.token_bytes(32))
    digest = hashlib.sha256(cv.encode("ascii")).digest()
    cc = _b64u_encode(digest)
    return cv, cc


class OidcClient:
    """OIDC/OAuth2 client.

    A single instance is fine for the whole process; per-provider state lives
    on the provider row + the in-memory state store.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        discovery_ttl_s: int = DISCOVERY_TTL_SECONDS,
        jwks_ttl_s: int = JWKS_TTL_SECONDS,
        clock_skew_s: int = 60,
    ) -> None:
        self._http = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http_client is None
        self._discovery_ttl = discovery_ttl_s
        self._jwks_ttl = jwks_ttl_s
        self._skew = clock_skew_s
        self._discovery_cache: dict[str, _Cached] = {}
        self._jwks_cache: dict[str, _Cached] = {}

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # --- discovery / jwks --------------------------------------------------

    async def discover(self, provider: Any, *, force: bool = False) -> dict[str, Any]:
        """Fetch the provider's OIDC discovery document with TTL caching.

        For OAuth2-only providers (e.g. GitHub) returns a synthetic dict from
        the explicit endpoints stored on the provider row.
        """
        if getattr(provider, "oauth2_only", False):
            synth: dict[str, Any] = {
                "issuer": provider.issuer,
                "authorization_endpoint": provider.authorization_endpoint,
                "token_endpoint": provider.token_endpoint,
                "userinfo_endpoint": provider.userinfo_endpoint,
                "jwks_uri": provider.jwks_uri,
            }
            return synth
        key = provider.id
        cached = self._discovery_cache.get(key)
        if not force and cached and time.time() - cached.fetched_at < self._discovery_ttl:
            return cached.value
        url = provider.issuer.rstrip("/") + "/.well-known/openid-configuration"
        resp = await self._http.get(url)
        if resp.status_code != 200:
            raise OidcError(f"discovery_failed:{resp.status_code}")
        doc = cast("dict[str, Any]", resp.json())
        self._discovery_cache[key] = _Cached(value=doc, fetched_at=time.time())
        return doc

    async def jwks(self, provider: Any, *, force: bool = False) -> dict[str, Any]:
        """Fetch JWKS for a provider with TTL caching."""
        key = provider.id
        cached = self._jwks_cache.get(key)
        if not force and cached and time.time() - cached.fetched_at < self._jwks_ttl:
            return cached.value
        doc = await self.discover(provider)
        jwks_uri = doc.get("jwks_uri") or getattr(provider, "jwks_uri", None)
        if not jwks_uri:
            raise OidcError("no_jwks_uri")
        resp = await self._http.get(jwks_uri)
        if resp.status_code != 200:
            raise OidcError(f"jwks_failed:{resp.status_code}")
        jwks = cast("dict[str, Any]", resp.json())
        self._jwks_cache[key] = _Cached(value=jwks, fetched_at=time.time())
        return jwks

    def _select_jwk(self, jwks: dict[str, Any], kid: str | None) -> dict[str, Any]:
        keys: list[dict[str, Any]] = jwks.get("keys", [])
        if not keys:
            raise OidcError("jwks_empty")
        if kid is None:
            if len(keys) > 1:
                raise OidcError("kid required when multiple JWKs present")
            return keys[0]
        for k in keys:
            if k.get("kid") == kid:
                return k
        raise OidcError(f"jwk_not_found:{kid}")

    # --- auth url + exchange ----------------------------------------------

    def auth_url(
        self,
        provider: Any,
        state: str,
        nonce: str,
        redirect_uri: str,
        *,
        authorization_endpoint: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Build authorization URL using PKCE S256.

        Returns ``(url, code_verifier)``. The verifier MUST be persisted with
        the state record and presented at exchange time.
        """
        if authorization_endpoint is None:
            raise OidcError("missing_authorization_endpoint")
        cv, cc = _pkce_pair()
        params = {
            "response_type": "code",
            "client_id": provider.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(provider.scopes or ["openid", "email", "profile"]),
            "state": state,
            "nonce": nonce,
            "code_challenge": cc,
            "code_challenge_method": "S256",
        }
        if extra_params:
            params.update(extra_params)
        return f"{authorization_endpoint}?{urlencode(params)}", cv

    async def exchange(
        self,
        provider: Any,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        *,
        token_endpoint: str | None = None,
        client_secret: str | None = None,
    ) -> dict[str, Any]:
        """Exchange an authorization code for tokens."""
        if token_endpoint is None:
            raise OidcError("missing_token_endpoint")
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": provider.client_id,
            "code_verifier": code_verifier,
        }
        if client_secret:
            data["client_secret"] = client_secret
        resp = await self._http.post(
            token_endpoint, data=data, headers={"Accept": "application/json"}
        )
        if resp.status_code != 200:
            raise OidcError(f"token_exchange_failed:{resp.status_code}:{resp.text[:200]}")
        return cast("dict[str, Any]", resp.json())

    # --- ID token verification --------------------------------------------

    async def get_userinfo(self, provider: Any, access_token: str) -> dict[str, Any]:
        """Fetch the OIDC userinfo / OAuth user resource for the given access token.

        Resolves the ``userinfo_endpoint`` via discovery (or the explicit
        provider-row override for OAuth2-only providers).
        """
        doc = await self.discover(provider)
        ui_url = doc.get("userinfo_endpoint") or getattr(provider, "userinfo_endpoint", None)
        if not ui_url:
            raise OidcError("no_userinfo_endpoint")
        resp = await self._http.get(
            ui_url, headers={"Authorization": f"Bearer {access_token}"}
        )
        if resp.status_code != 200:
            raise OidcError(f"userinfo_failed:{resp.status_code}")
        return cast("dict[str, Any]", resp.json())

    async def verify_id_token(
        self,
        provider: Any,
        id_token: str,
        nonce: str,
        *,
        access_token: str | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Validate an ID token and return its claims dict.

        Checks: signature (via JWKS), iss matches provider.issuer, aud contains
        provider.client_id, exp/nbf within skew, nonce matches, optional at_hash
        if access_token provided.
        """
        header, payload, signing_input, signature = _split_jwt(id_token)
        alg_raw = header.get("alg")
        if alg_raw in (None, "none") or not isinstance(alg_raw, str):
            raise OidcError("alg_none_disallowed")
        alg: str = alg_raw
        kid = header.get("kid")

        jwks = await self.jwks(provider)
        try:
            jwk = self._select_jwk(jwks, kid)
        except OidcError:
            # Try forced refresh in case of rotation
            jwks = await self.jwks(provider, force=True)
            jwk = self._select_jwk(jwks, kid)
        pubkey = _jwk_to_public_key(jwk)
        _verify_jwt_signature(alg, pubkey, signing_input, signature)

        # iss
        issuer = payload.get("iss")
        if issuer != provider.issuer:
            raise OidcError(f"iss_mismatch:{issuer}")
        # aud
        aud = payload.get("aud")
        aud_list = [aud] if isinstance(aud, str) else (aud or [])
        if provider.client_id not in aud_list:
            raise OidcError("aud_mismatch")
        if isinstance(aud, list) and len(aud) > 1:
            azp = payload.get("azp")
            if azp != provider.client_id:
                raise OidcError("azp_mismatch")
        # exp / nbf
        ts = now if now is not None else time.time()
        exp = payload.get("exp")
        if exp is None or ts > exp + self._skew:
            raise OidcError("token_expired")
        nbf = payload.get("nbf")
        if nbf is not None and ts + self._skew < nbf:
            raise OidcError("token_not_yet_valid")
        iat = payload.get("iat")
        if iat is not None and ts + self._skew < iat:
            raise OidcError("token_iat_in_future")
        # nonce — required
        if payload.get("nonce") != nonce:
            raise OidcError("nonce_mismatch")
        # at_hash (optional)
        if access_token and "at_hash" in payload:
            digest = hashlib.sha256(access_token.encode("ascii")).digest()
            expected = _b64u_encode(digest[: len(digest) // 2])
            if expected != payload["at_hash"]:
                raise OidcError("at_hash_mismatch")
        return payload
