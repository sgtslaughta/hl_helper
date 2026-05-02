import pytest
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    app = _build_app()
    with TestClient(app) as c:
        r1 = c.post("/echo", headers={HEADER: "k1"})
        r2 = c.post("/echo", headers={HEADER: "k1"})
        assert r1.json() == r2.json()
        assert app.state.counter["n"] == 1  # handler ran ONCE


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
    await s.put("p", "/r", "k",
                status_code=200, body=b'{}',
                headers={}, content_type="application/json", now=now)
    # Within TTL → hit
    hit = await s.get("p", "/r", "k", now=now)
    assert hit is not None
    # After TTL → miss
    miss = await s.get("p", "/r", "k", now=now + timedelta(seconds=2))
    assert miss is None


@pytest.mark.asyncio
async def test_purge_expired_returns_count():
    s = IdempotencyStore(ttl=timedelta(seconds=1))
    now = datetime.now(timezone.utc)
    for i in range(3):
        await s.put(f"p{i}", "/r", "k",
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
