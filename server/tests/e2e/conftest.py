"""Shared pytest fixtures for E2E tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from server.app.crypto.signing import FileBackend
from server.app.grpc._pb import fleet  # noqa: F401  triggers sys.path injection
from server.app.grpc._pb.fleet.v1 import envelope_pb2

# Import grpc fixtures for TLS/enrollment tests
pytest_plugins = ["server.tests.grpc.conftest"]


def make_envelope(
    host_id: str,
    sequence: int,
    nonce: bytes,
    ttl_seconds: int = 3600,
    now: datetime | None = None,
) -> envelope_pb2.CommandEnvelope:
    """Factory to build a CommandEnvelope with PkgUpdate payload."""
    if now is None:
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    expires = now + timedelta(seconds=ttl_seconds)

    env = envelope_pb2.CommandEnvelope()
    env.command_id = f"cmd-{host_id}-{sequence}"
    env.host_id = host_id
    env.sequence = sequence
    env.nonce = nonce
    env.issued_at.FromDatetime(now)
    env.expires_at.FromDatetime(expires)
    env.issued_by = "test-server"

    # Set PkgUpdate payload
    env.pkg_update.classes.append("base")
    env.pkg_update.dry_run = False

    return env
