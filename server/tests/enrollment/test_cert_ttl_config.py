"""Tests for cert TTL configuration."""
from __future__ import annotations

from datetime import timedelta


def test_default_cert_ttl_is_7_days(monkeypatch):
    monkeypatch.delenv("HL_CERT_TTL_DAYS", raising=False)
    from server.app.enrollment.service import default_cert_ttl

    assert default_cert_ttl() == timedelta(days=7)


def test_cert_ttl_env_override(monkeypatch):
    monkeypatch.setenv("HL_CERT_TTL_DAYS", "30")
    from server.app.enrollment.service import default_cert_ttl

    assert default_cert_ttl() == timedelta(days=30)


def test_cert_ttl_fractional_days(monkeypatch):
    monkeypatch.setenv("HL_CERT_TTL_DAYS", "0.5")
    from server.app.enrollment.service import default_cert_ttl

    assert default_cert_ttl() == timedelta(days=0.5)


def test_cert_ttl_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("HL_CERT_TTL_DAYS", "garbage")
    from server.app.enrollment.service import default_cert_ttl

    assert default_cert_ttl() == timedelta(days=7)
