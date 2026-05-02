"""Tests for server.app.crypto.signing.{SigningBackend, FileBackend}."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from server.app.crypto.signing import FileBackend


@pytest.fixture
def backend(tmp_path: Path) -> FileBackend:
    return FileBackend.bootstrap(tmp_path / "signing")


def test_bootstrap_creates_layout(tmp_path: Path) -> None:
    d = tmp_path / "signing"
    FileBackend.bootstrap(d)
    assert (d / "current.key").exists()
    assert (d / "anchors").is_dir()
    assert (d / "anchors" / "current.pub").exists()
    assert (d / "current.key").stat().st_mode & 0o777 == 0o600


def test_sign_verify_roundtrip(backend: FileBackend) -> None:
    sig = backend.sign(b"command-bytes")
    assert backend.verify(b"command-bytes", sig) is True
    assert backend.verify(b"different-bytes", sig) is False


def test_public_key_bytes_is_pem(backend: FileBackend) -> None:
    pub = backend.public_key_bytes()
    assert pub.startswith(b"-----BEGIN PUBLIC KEY-----")


def test_trust_anchors_initially_one(backend: FileBackend) -> None:
    anchors = backend.trust_anchors()
    assert len(anchors) == 1


def test_rotate_dual_publish_within_grace(backend: FileBackend) -> None:
    old_pub = backend.public_key_bytes()
    backend.rotate(grace=timedelta(days=7))
    new_pub = backend.public_key_bytes()
    assert old_pub != new_pub
    # Both anchors trusted during grace window.
    anchors = backend.trust_anchors()
    assert len(anchors) == 2
    assert old_pub in anchors
    assert new_pub in anchors
    # New key signs and verifies.
    sig_new = backend.sign(b"x")
    assert backend.verify(b"x", sig_new) is True


def test_rotate_clears_expired_anchors(backend: FileBackend) -> None:
    backend.rotate(grace=timedelta(seconds=-1))  # already expired
    # Retired anchor's grace already past -> only current remains.
    anchors = backend.trust_anchors()
    assert len(anchors) == 1


def test_rotate_then_signature_with_old_key_no_longer_verifiable_after_grace(
    tmp_path: Path,
) -> None:
    backend = FileBackend.bootstrap(tmp_path / "s")
    sig_old = backend.sign(b"payload")
    # Capture old anchor.
    old_pub = backend.public_key_bytes()
    backend.rotate(grace=timedelta(days=7))
    # Within grace: old sig still verifies via old anchor.
    assert backend.verify(b"payload", sig_old) is True
    # Force expiry by rotating again with negative grace (drops the just-retired
    # anchor whose own grace has not expired yet — so we must skip directly to
    # writing an expired retired anchor file). Instead: simulate elapsed time by
    # rewriting the grace marker with a past expiry.
    grace_file = tmp_path / "s" / "anchors" / "grace.json"
    import json
    data = json.loads(grace_file.read_text())
    for entry in data.get("retired", []):
        entry["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    grace_file.write_text(json.dumps(data))
    backend.reload()
    assert backend.verify(b"payload", sig_old) is False
    assert old_pub not in backend.trust_anchors()


def test_load_round_trips(tmp_path: Path) -> None:
    d = tmp_path / "s"
    b1 = FileBackend.bootstrap(d)
    sig = b1.sign(b"hello")
    pub = b1.public_key_bytes()
    b2 = FileBackend(d)
    assert b2.verify(b"hello", sig) is True
    assert b2.public_key_bytes() == pub
