"""Server signing key abstraction.

Holds the Ed25519 keypair used to sign every CommandEnvelope sent to agents.
Separate from the TLS keystore (CA) so that compromise of TLS material alone
cannot forge commands.

Provides rotation with dual-publish: after rotation, the previous public key
remains a trust anchor for a configurable grace window so signatures emitted
just before rotation still verify until in-flight commands clear.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


class SigningBackend(Protocol):
    """Protocol for signing-key backends.

    Implementations: FileBackend (default), VaultBackend (C3), PKCS11Backend (later).
    """

    def sign(self, data: bytes) -> bytes: ...
    def verify(self, data: bytes, sig: bytes) -> bool: ...
    def public_key_bytes(self) -> bytes: ...
    def trust_anchors(self) -> list[bytes]: ...
    def rotate(self, grace: timedelta) -> None: ...


@dataclass
class _RetiredAnchor:
    file: str
    expires_at: datetime


class FileBackend:
    """Filesystem-backed Ed25519 signing key with rotation + dual-publish anchors."""

    GRACE_FILE = "anchors/grace.json"
    CURRENT_KEY = "current.key"
    CURRENT_PUB = "anchors/current.pub"

    def __init__(self, dir: Path | str) -> None:
        self.dir = Path(dir)
        self._current: ed25519.Ed25519PrivateKey
        self._retired: list[_RetiredAnchor] = []
        self.reload()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    @classmethod
    def bootstrap(cls, dir: Path | str) -> FileBackend:
        d = Path(dir)
        (d / "anchors").mkdir(parents=True, exist_ok=True)
        key = ed25519.Ed25519PrivateKey.generate()
        cls._write_private(d / cls.CURRENT_KEY, key)
        cls._write_public(d / cls.CURRENT_PUB, key.public_key())
        (d / cls.GRACE_FILE).write_text(json.dumps({"retired": []}))
        return cls(d)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def sign(self, data: bytes) -> bytes:
        return self._current.sign(data)

    def verify(self, data: bytes, sig: bytes) -> bool:
        for anchor_pem in self.trust_anchors():
            try:
                pub = serialization.load_pem_public_key(anchor_pem)
                # Ed25519 public key has .verify(sig, data); raises on failure.
                if not isinstance(pub, ed25519.Ed25519PublicKey):
                    continue
                pub.verify(sig, data)
                return True
            except Exception:
                continue
        return False

    def public_key_bytes(self) -> bytes:
        return (self.dir / self.CURRENT_PUB).read_bytes()

    def trust_anchors(self) -> list[bytes]:
        anchors: list[bytes] = [self.public_key_bytes()]
        now = datetime.now(timezone.utc)
        for r in self._retired:
            if r.expires_at > now:
                p = self.dir / "anchors" / r.file
                if p.exists():
                    anchors.append(p.read_bytes())
        return anchors

    def rotate(self, grace: timedelta) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        retired_name = f"retired-{ts}.pub"
        # Move current pub aside.
        (self.dir / "anchors" / retired_name).write_bytes(self.public_key_bytes())
        # Generate new keypair, overwrite current.
        new_key = ed25519.Ed25519PrivateKey.generate()
        self._write_private(self.dir / self.CURRENT_KEY, new_key)
        self._write_public(self.dir / self.CURRENT_PUB, new_key.public_key())
        # Update grace.
        expires = datetime.now(timezone.utc) + grace
        data = json.loads((self.dir / self.GRACE_FILE).read_text())
        data["retired"].append(
            {"file": retired_name, "expires_at": expires.isoformat()}
        )
        # GC expired entries.
        now = datetime.now(timezone.utc)
        kept = []
        for entry in data["retired"]:
            ent_exp = datetime.fromisoformat(entry["expires_at"])
            if ent_exp > now:
                kept.append(entry)
            else:
                stale = self.dir / "anchors" / entry["file"]
                if stale.exists():
                    stale.unlink()
        data["retired"] = kept
        (self.dir / self.GRACE_FILE).write_text(json.dumps(data))
        self.reload()

    def reload(self) -> None:
        key_bytes = (self.dir / self.CURRENT_KEY).read_bytes()
        loaded = serialization.load_pem_private_key(key_bytes, password=None)
        if not isinstance(loaded, ed25519.Ed25519PrivateKey):
            raise ValueError("current.key is not Ed25519")
        self._current = loaded
        grace_path = self.dir / self.GRACE_FILE
        retired: list[_RetiredAnchor] = []
        if grace_path.exists():
            data = json.loads(grace_path.read_text())
            for entry in data.get("retired", []):
                retired.append(
                    _RetiredAnchor(
                        file=entry["file"],
                        expires_at=datetime.fromisoformat(entry["expires_at"]),
                    )
                )
        self._retired = retired

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _write_private(path: Path, key: ed25519.Ed25519PrivateKey) -> None:
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        path.write_bytes(pem)
        os.chmod(path, 0o600)

    @staticmethod
    def _write_public(path: Path, key: ed25519.Ed25519PublicKey) -> None:
        pem = key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        path.write_bytes(pem)
        os.chmod(path, 0o644)
