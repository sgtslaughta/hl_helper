"""Tests for TLS 1.3 cipher pin enforcement in gRPC server."""

from __future__ import annotations

import os
from unittest import mock

import grpc
import pytest

import logging

from server.app.grpc.tls import (
    ALLOWED_TLS13_CIPHERS,
    enforce_tls_pin,
    extract_spiffe_id,
    probe_tls_version,
)


def test_grpc_ssl_cipher_suites_env_set() -> None:
    """Verify GRPC_SSL_CIPHER_SUITES env var contains allowed ciphers."""
    # The env var should be set at module import time
    env_val = os.environ.get("GRPC_SSL_CIPHER_SUITES", "")
    assert ALLOWED_TLS13_CIPHERS in env_val, (
        f"GRPC_SSL_CIPHER_SUITES not set with allowed ciphers. "
        f"Expected: {ALLOWED_TLS13_CIPHERS}, Got: {env_val}"
    )


def test_enforce_tls_pin_passes_on_modern_grpcio() -> None:
    """enforce_tls_pin() should not raise on grpcio >= 1.50."""
    # Current version is 1.80.0, so this should pass
    enforce_tls_pin()  # Should not raise


def test_enforce_tls_pin_raises_on_old_grpcio() -> None:
    """enforce_tls_pin() raises RuntimeError if grpcio < 1.50."""
    with mock.patch.object(grpc, "__version__", "1.40.0"):
        with pytest.raises(RuntimeError, match="grpcio >= 1.50"):
            enforce_tls_pin()


def test_enforce_tls_pin_checks_exact_old_version() -> None:
    """enforce_tls_pin() should reject grpcio 1.49.x."""
    with mock.patch.object(grpc, "__version__", "1.49.9"):
        with pytest.raises(RuntimeError, match="grpcio >= 1.50"):
            enforce_tls_pin()


def test_enforce_tls_pin_accepts_version_boundary() -> None:
    """enforce_tls_pin() should accept grpcio 1.50.0."""
    with mock.patch.object(grpc, "__version__", "1.50.0"):
        enforce_tls_pin()  # Should not raise


def test_probe_tls_version_no_raise(caplog: pytest.LogCaptureFixture) -> None:
    """probe_tls_version() never raises; logs at most warning."""
    with caplog.at_level(logging.DEBUG, logger="server.app.grpc.tls"):
        probe_tls_version()


def test_extract_spiffe_id_logs_on_invalid_pem(caplog: pytest.LogCaptureFixture) -> None:
    """extract_spiffe_id() returns None and logs warning on invalid PEM."""
    with caplog.at_level(logging.WARNING, logger="server.app.grpc.tls"):
        result = extract_spiffe_id(b"not a real cert")
    assert result is None
    assert any("spiffe extract failed" in r.message for r in caplog.records)
