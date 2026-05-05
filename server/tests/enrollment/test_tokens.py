"""Tests for server.app.enrollment.tokens."""

from __future__ import annotations

import base64

import pytest

from server.app.enrollment.tokens import (
    clamp_ttl_seconds,
    generate_token,
    hash_token,
    validate_token_shape,
)


def test_generate_token_has_hlb_prefix() -> None:
    """Verify generated token starts with hlb_ prefix."""
    token = generate_token()
    assert token.startswith("hlb_"), f"Token should start with 'hlb_', got {token}"


def test_generate_token_unique() -> None:
    """Verify 100 generated tokens are distinct."""
    tokens = {generate_token() for _ in range(100)}
    assert len(tokens) == 100, "All 100 tokens should be unique"


def test_generate_token_decodes_back_to_32_bytes() -> None:
    """Verify generated token encodes 32 bytes of entropy."""
    token = generate_token()
    # Remove prefix
    suffix = token[4:]
    # Re-pad base32 (each char encodes 5 bits, so 32 bytes = 256 bits = 51.2 chars ≈ 52 chars with padding)
    # Base32 pads to multiple of 8: 256 bits / 5 bits per char = 51.2 ≈ 52 chars, needs 1 padding = 8 chars
    # Actually: 32 bytes = 256 bits, 256/5 = 51.2, round up to 55 (next multiple of 5), decode needs padding to 8 chars
    # Let's compute: base32 alphabet size = 32, so 5 bits per char
    # 32 bytes * 8 bits/byte = 256 bits, 256 bits / 5 bits per char = 51.2 chars
    # Base32 padding brings it to multiple of 8: ceil(51.2 / 8) * 8 = 56, so 56 - 51.2 = 4.8 = 5 padding chars
    # Re-add padding (number of '=' to add is (8 - len(suffix) % 8) % 8)
    padding_needed = (8 - len(suffix) % 8) % 8
    padded = suffix + "=" * padding_needed

    decoded = base64.b32decode(padded.upper())
    assert len(decoded) == 32, f"Decoded bytes should be 32, got {len(decoded)}"


def test_validate_token_shape_accepts_generated() -> None:
    """Verify validate_token_shape accepts a generated token."""
    token = generate_token()
    # Should not raise
    validate_token_shape(token)


def test_validate_token_shape_rejects_no_prefix() -> None:
    """Verify validate_token_shape rejects token without hlb_ prefix."""
    with pytest.raises(ValueError, match="must start with 'hlb_'"):
        validate_token_shape("abcdefghijklmnopqrstuvwxyz234567")


def test_validate_token_shape_rejects_uppercase() -> None:
    """Verify validate_token_shape rejects uppercase characters."""
    with pytest.raises(ValueError, match="only lowercase a-z and 2-7"):
        validate_token_shape("hlb_ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")


def test_validate_token_shape_rejects_invalid_chars() -> None:
    """Verify validate_token_shape rejects invalid base32 characters."""
    with pytest.raises(ValueError, match="only lowercase a-z and 2-7"):
        validate_token_shape("hlb_abcdefghijklmnopqrstuvwxyz189")  # '1', '8', '9' are invalid


def test_hash_token_produces_32_bytes() -> None:
    """Verify hash_token returns 32-byte SHA-256 digest."""
    token = generate_token()
    token_hash = hash_token(token)
    assert len(token_hash) == 32, "SHA-256 digest should be 32 bytes"


def test_hash_token_deterministic() -> None:
    """Verify hash_token is deterministic."""
    token = "hlb_abcdefghijklmnopqrstuvwxyz234567"
    hash1 = hash_token(token)
    hash2 = hash_token(token)
    assert hash1 == hash2, "Hashing same token should produce same hash"


def test_clamp_ttl_below_min_raises() -> None:
    """Verify clamp_ttl_seconds raises ValueError below minimum."""
    with pytest.raises(ValueError):
        clamp_ttl_seconds(30)


def test_clamp_ttl_above_max_clamps() -> None:
    """Verify clamp_ttl_seconds clamps values above maximum."""
    assert clamp_ttl_seconds(999_999) == 86_400


def test_clamp_ttl_within_range_returns_value() -> None:
    """Verify clamp_ttl_seconds returns value within valid range."""
    assert clamp_ttl_seconds(900) == 900


def test_clamp_ttl_default_when_none() -> None:
    """Verify clamp_ttl_seconds returns default when None."""
    assert clamp_ttl_seconds(None) == 900
