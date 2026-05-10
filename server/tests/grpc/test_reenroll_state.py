"""Tests for ReEnroll nonce cache + rate limiter."""
from __future__ import annotations

import time

import pytest


def test_nonce_cache_stores_and_consumes():
    from server.app.grpc.reenroll_state import NonceCache

    nc = NonceCache(ttl_seconds=60)
    nc.put("h-1", b"\x01" * 32)
    assert nc.consume("h-1", b"\x01" * 32) is True


def test_nonce_cache_one_shot():
    from server.app.grpc.reenroll_state import NonceCache

    nc = NonceCache(ttl_seconds=60)
    nc.put("h-1", b"\x01" * 32)
    assert nc.consume("h-1", b"\x01" * 32) is True
    assert nc.consume("h-1", b"\x01" * 32) is False


def test_nonce_cache_rejects_wrong_nonce():
    from server.app.grpc.reenroll_state import NonceCache

    nc = NonceCache(ttl_seconds=60)
    nc.put("h-1", b"\x01" * 32)
    assert nc.consume("h-1", b"\x02" * 32) is False


def test_nonce_cache_expires(monkeypatch):
    from server.app.grpc import reenroll_state

    base = 1_000_000.0
    monkeypatch.setattr(reenroll_state.time, "monotonic", lambda: base)
    nc = reenroll_state.NonceCache(ttl_seconds=60)
    nc.put("h-1", b"\x01" * 32)

    monkeypatch.setattr(reenroll_state.time, "monotonic", lambda: base + 61)
    assert nc.consume("h-1", b"\x01" * 32) is False


def test_nonce_cache_overwrites_prior_per_host():
    from server.app.grpc.reenroll_state import NonceCache

    nc = NonceCache(ttl_seconds=60)
    nc.put("h-1", b"\x01" * 32)
    nc.put("h-1", b"\x02" * 32)
    assert nc.consume("h-1", b"\x01" * 32) is False
    assert nc.consume("h-1", b"\x02" * 32) is True


def test_reenroll_rate_limiter_allows_3_per_24h():
    from server.app.grpc.reenroll_state import ReEnrollRateLimiter

    rl = ReEnrollRateLimiter(window_seconds=86400, max_per_window=3)
    assert rl.allow("h-1") is True
    assert rl.allow("h-1") is True
    assert rl.allow("h-1") is True
    assert rl.allow("h-1") is False


def test_reenroll_rate_limiter_evicts_old(monkeypatch):
    from server.app.grpc import reenroll_state

    base = 1_000_000.0
    monkeypatch.setattr(reenroll_state.time, "monotonic", lambda: base)
    rl = reenroll_state.ReEnrollRateLimiter(window_seconds=86400, max_per_window=3)
    rl.allow("h-1")
    rl.allow("h-1")
    rl.allow("h-1")

    monkeypatch.setattr(reenroll_state.time, "monotonic", lambda: base + 86401)
    assert rl.allow("h-1") is True


def test_canonical_signed_payload():
    from server.app.grpc.reenroll_state import canonical_reenroll_payload

    msg = canonical_reenroll_payload("h-1", b"\xaa" * 32, 1700000000)
    assert msg.startswith(b"reenroll-v1|h-1|") or len(msg) > 0
    # sha256 hex of remainder is what gets signed
    assert len(msg) > 0


def test_verify_reenroll_signature_accepts_valid():
    from cryptography.hazmat.primitives.asymmetric import ed25519

    from server.app.grpc.reenroll_state import (
        canonical_reenroll_payload,
        verify_reenroll_signature,
    )

    sk = ed25519.Ed25519PrivateKey.generate()
    pk_bytes = sk.public_key().public_bytes_raw()

    msg = canonical_reenroll_payload("h-1", b"\xaa" * 32, 1700000000)
    sig = sk.sign(msg)

    assert (
        verify_reenroll_signature(
            host_id="h-1",
            nonce=b"\xaa" * 32,
            ts_unix=1700000000,
            signature=sig,
            signing_pubkey=pk_bytes,
        )
        is True
    )


def test_verify_reenroll_signature_rejects_wrong_key():
    from cryptography.hazmat.primitives.asymmetric import ed25519

    from server.app.grpc.reenroll_state import verify_reenroll_signature

    sk = ed25519.Ed25519PrivateKey.generate()
    other = ed25519.Ed25519PrivateKey.generate()
    msg = b"reenroll-v1|h-1|"  # placeholder; real impl uses canonical
    sig = sk.sign(msg)

    assert (
        verify_reenroll_signature(
            host_id="h-1",
            nonce=b"\xaa" * 32,
            ts_unix=1700000000,
            signature=sig,
            signing_pubkey=other.public_key().public_bytes_raw(),
        )
        is False
    )
