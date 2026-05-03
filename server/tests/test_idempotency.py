import asyncio
import hashlib
import pytest
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from server.app.api.app import create_app
from server.app.idempotency import (
    IdempotencyMiddleware, IdempotencyStore, DEFAULT_TTL, HEADER,
)


def _build_app(store: IdempotencyStore | None = None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware, store=store)
    counter = {"n": 0}

    @app.post("/echo")
    async def echo() -> dict:
        counter["n"] += 1
        return {"call": counter["n"]}

    @app.get("/r")
    async def r() -> dict:
        counter["n"] += 1
        return {"call": counter["n"]}

    app.state.counter = counter
    return app


def test_default_ttl_is_24_hours():
    assert DEFAULT_TTL == timedelta(hours=24)


def test_no_idempotency_key_passes_through():
    app = _build_app()
    with TestClient(app) as c:
        r1 = c.post("/echo")
        r2 = c.post("/echo")
        assert r1.json()["call"] == 1
        assert r2.json()["call"] == 2  # both invocations ran


def test_get_method_bypasses():
    app = _build_app()
    with TestClient(app) as c:
        r1 = c.get("/r", headers={HEADER: "k1"})
        r2 = c.get("/r", headers={HEADER: "k1"})
        assert r1.json()["call"] == 1
        assert r2.json()["call"] == 2  # GET never dedups


def test_replay_returns_cached_response():
    app = FastAPI()
    store = IdempotencyStore()
    app.add_middleware(IdempotencyMiddleware, store=store)
    counter = {"n": 0}

    @app.middleware("http")
    async def set_principal(req, call_next):
        req.state.principal_id = "u-1"
        return await call_next(req)

    @app.post("/echo")
    async def echo() -> dict:
        counter["n"] += 1
        return {"call": counter["n"]}

    with TestClient(app) as c:
        r1 = c.post("/echo", headers={HEADER: "k1"})
        r2 = c.post("/echo", headers={HEADER: "k1"})
        assert r1.json() == r2.json()
        assert counter["n"] == 1  # handler ran ONCE


def test_different_keys_invoke_handler_separately():
    app = _build_app()
    with TestClient(app) as c:
        r1 = c.post("/echo", headers={HEADER: "k1"})
        r2 = c.post("/echo", headers={HEADER: "k2"})
        assert r1.json()["call"] == 1
        assert r2.json()["call"] == 2


def test_different_routes_separate_keyspace():
    app = FastAPI()
    store = IdempotencyStore()
    app.add_middleware(IdempotencyMiddleware, store=store)

    @app.post("/a")
    async def a() -> dict:
        return {"r": "a"}

    @app.post("/b")
    async def b() -> dict:
        return {"r": "b"}

    with TestClient(app) as c:
        r1 = c.post("/a", headers={HEADER: "same"})
        r2 = c.post("/b", headers={HEADER: "same"})
        assert r1.json() == {"r": "a"}
        assert r2.json() == {"r": "b"}


@pytest.mark.asyncio
async def test_store_expiry_purged():
    s = IdempotencyStore(ttl=timedelta(seconds=1))
    now = datetime.now(timezone.utc)
    body_hash = hashlib.sha256(b'{}').hexdigest()
    await s.put("p", "/r", "k", body_hash,
                status_code=200, body=b'{}',
                headers={}, content_type="application/json", now=now)
    # Within TTL → hit
    hit = await s.get("p", "/r", "k", body_hash, now=now)
    assert hit is not None
    # After TTL → miss
    miss = await s.get("p", "/r", "k", body_hash, now=now + timedelta(seconds=2))
    assert miss is None


@pytest.mark.asyncio
async def test_purge_expired_returns_count():
    s = IdempotencyStore(ttl=timedelta(seconds=1))
    now = datetime.now(timezone.utc)
    for i in range(3):
        body_hash = hashlib.sha256(b'').hexdigest()
        await s.put(f"p{i}", "/r", "k", body_hash,
                    status_code=200, body=b'',
                    headers={}, content_type="application/json", now=now)
    purged = await s.purge_expired(now=now + timedelta(seconds=2))
    assert purged == 3


def test_principal_isolation():
    """Same key from different principals must not collide."""
    app = FastAPI()
    store = IdempotencyStore()
    app.add_middleware(IdempotencyMiddleware, store=store)

    counter = {"n": 0}

    @app.middleware("http")
    async def set_principal(req, call_next):
        # Toggle principal based on a header for this test only
        req.state.principal_id = req.headers.get("X-Principal", "anonymous")
        return await call_next(req)

    @app.post("/x")
    async def x() -> dict:
        counter["n"] += 1
        return {"call": counter["n"]}

    with TestClient(app) as c:
        r1 = c.post("/x", headers={HEADER: "k", "X-Principal": "u-1"})
        r2 = c.post("/x", headers={HEADER: "k", "X-Principal": "u-2"})
        assert r1.json()["call"] == 1
        assert r2.json()["call"] == 2  # different principals, separate cache


def test_anonymous_principal_skips_caching():
    """Without principal_id, requests are NOT cached (no cross-request leak)."""
    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)
    counter = {"n": 0}

    @app.post("/x")
    async def x() -> dict:
        counter["n"] += 1
        return {"n": counter["n"]}

    with TestClient(app) as c:
        r1 = c.post("/x", headers={HEADER: "k"})
        r2 = c.post("/x", headers={HEADER: "k"})
        # Both invocations ran — no caching for anon principals
        assert r1.json()["n"] == 1
        assert r2.json()["n"] == 2


@pytest.mark.asyncio
async def test_concurrent_same_key_only_invokes_handler_once():
    """Race: two concurrent requests with same key should result in handler running ONCE."""
    app = FastAPI()
    store = IdempotencyStore()
    app.add_middleware(IdempotencyMiddleware, store=store)
    counter = {"n": 0}

    @app.middleware("http")
    async def set_principal(req, call_next):
        req.state.principal_id = "u-1"
        return await call_next(req)

    @app.post("/x")
    async def x() -> dict:
        await asyncio.sleep(0.05)  # simulate slow handler
        counter["n"] += 1
        return {"n": counter["n"]}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r1, r2 = await asyncio.gather(
            ac.post("/x", headers={HEADER: "k"}),
            ac.post("/x", headers={HEADER: "k"}),
        )
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()
    assert counter["n"] == 1  # only one invocation


def test_5xx_response_not_cached():
    """4xx/5xx responses must not be cached so client can retry."""
    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)

    @app.middleware("http")
    async def set_principal(req, call_next):
        req.state.principal_id = "u-1"
        return await call_next(req)

    counter = {"n": 0}

    @app.post("/fail")
    async def fail() -> dict:
        counter["n"] += 1
        raise HTTPException(503, detail="transient")

    with TestClient(app) as c:
        r1 = c.post("/fail", headers={HEADER: "k"})
        r2 = c.post("/fail", headers={HEADER: "k"})
        assert r1.status_code == r2.status_code == 503
        assert counter["n"] == 2  # handler ran both times


@pytest.mark.asyncio
async def test_store_eviction_at_max_entries():
    """Adding > max_entries items evicts oldest."""
    s = IdempotencyStore(max_entries=3)
    for i in range(5):
        body_hash = hashlib.sha256(b"").hexdigest()
        await s.put(
            "p",
            "/r",
            f"k{i}",
            body_hash,
            status_code=200,
            body=b"",
            headers={},
            content_type="application/json",
        )
    # k0, k1 evicted; k2,k3,k4 remain
    body_hash = hashlib.sha256(b"").hexdigest()
    assert await s.get("p", "/r", "k0", body_hash) is None
    assert await s.get("p", "/r", "k1", body_hash) is None
    assert await s.get("p", "/r", "k4", body_hash) is not None


def test_idempotency_middleware_installed_in_app():
    """Test that IdempotencyMiddleware is installed in FastAPI app."""
    app = create_app()
    # Check that IdempotencyMiddleware is in the middleware stack
    middleware_classes = [m.cls.__name__ for m in app.user_middleware]
    assert "IdempotencyMiddleware" in middleware_classes


def test_different_request_bodies_same_key_returns_409():
    """Two requests with same (principal, route, key) but different bodies return 422 conflict."""
    app = FastAPI()
    store = IdempotencyStore()
    app.add_middleware(IdempotencyMiddleware, store=store)

    call_count = {"n": 0}

    @app.middleware("http")
    async def set_principal(req, call_next):
        req.state.principal_id = "u-1"
        return await call_next(req)

    @app.post("/echo")
    async def echo(data: dict) -> dict:
        call_count["n"] += 1
        return {"call": call_count["n"], "data": data}

    with TestClient(app) as c:
        # First request with body {"a": 1}
        r1 = c.post("/echo", headers={HEADER: "key1"}, json={"a": 1})
        assert r1.status_code == 200
        assert r1.json() == {"call": 1, "data": {"a": 1}}

        # Second request with same key but different body {"a": 2}
        r2 = c.post("/echo", headers={HEADER: "key1"}, json={"a": 2})
        # Should return 409 idempotency_key_conflict (per RFC 7807 Conflict)
        assert r2.status_code == 409
        assert "idempotency_key_conflict" in r2.text


def test_request_body_too_large_returns_413():
    """Request body > max bytes should return 413."""
    app = FastAPI()
    store = IdempotencyStore(max_body_bytes=100)  # Very small for test
    app.add_middleware(IdempotencyMiddleware, store=store)

    @app.middleware("http")
    async def set_principal(req, call_next):
        req.state.principal_id = "u-1"
        return await call_next(req)

    @app.post("/echo")
    async def echo(data: dict) -> dict:
        return {"ok": True}

    with TestClient(app) as c:
        # Large body (> 100 bytes)
        large_body = {"data": "x" * 200}
        r = c.post("/echo", headers={HEADER: "key1"}, json=large_body)
        # Should return 413
        assert r.status_code == 413
        assert "payload too large" in r.text.lower()
