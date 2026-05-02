"""Tests for API key generation, hashing, and verification."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.auth.api_key import (
    ApiKeyError,
    ApiKeyExpired,
    ApiKeyIPDenied,
    ApiKeyRevoked,
    ApiKeyService,
    generate_plaintext,
    hash_plaintext,
    parse_prefix,
)
from server.app.models.api_key import ApiKey
from server.app.models.base import Base


@pytest.fixture
async def async_session_maker(tmp_path: Path):
    """Create in-memory aiosqlite database with tables."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def session(async_session_maker) -> AsyncIterator[AsyncSession]:
    """Create a fresh session for each test."""
    async with async_session_maker() as s:
        yield s


class TestPlaintextGeneration:
    """Test plaintext generation."""

    def test_generate_plaintext_format(self):
        """Generate plaintext starts with hlk_ and is urlsafe."""
        plaintext = generate_plaintext()
        assert plaintext.startswith("hlk_")
        assert len(plaintext) >= 36
        # Check urlsafe chars only (alphanumeric, -, _)
        body = plaintext[4:]
        assert all(c.isalnum() or c in "-_" for c in body)

    def test_generate_plaintext_random(self):
        """Two generated plaintexts should be different."""
        p1 = generate_plaintext()
        p2 = generate_plaintext()
        assert p1 != p2

    def test_parse_prefix(self):
        """Parse prefix returns first 8 chars."""
        plaintext = generate_plaintext()
        prefix = parse_prefix(plaintext)
        assert prefix == plaintext[:8]
        assert len(prefix) == 8

    def test_hash_plaintext(self):
        """Hash matches SHA-256 of plaintext."""
        plaintext = generate_plaintext()
        digest = hash_plaintext(plaintext)
        expected = hashlib.sha256(plaintext.encode("ascii")).digest()
        assert digest == expected
        assert len(digest) == 32


class TestApiKeyIssue:
    """Test ApiKeyService.issue()."""

    @pytest.mark.asyncio
    async def test_issue_creates_key(self, session: AsyncSession):
        """Issue creates a key in the database."""
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
        )
        await session.commit()

        # Verify plaintext is returned
        assert issued.plaintext.startswith("hlk_")
        assert len(issued.plaintext) >= 36

        # Verify api_key_id is returned
        assert len(issued.api_key_id) > 0

        # Verify row was created
        key = await session.get(ApiKey, issued.api_key_id)
        assert key is not None
        assert key.principal_id == "user-123"
        assert key.principal_kind == "user"
        assert key.name == "my-key"
        assert key.prefix == issued.plaintext[:8]
        assert key.last_4 == issued.plaintext[-4:]

    @pytest.mark.asyncio
    async def test_issue_with_expiry(self, session: AsyncSession):
        """Issue with expires_at."""
        svc = ApiKeyService(session)
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
            expires_at=expires,
        )
        await session.commit()

        key = await session.get(ApiKey, issued.api_key_id)
        # DB may strip timezone info, so compare without it
        assert key.expires_at.replace(tzinfo=None) == expires.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_issue_with_ip_allowlist(self, session: AsyncSession):
        """Issue with IP allowlist."""
        svc = ApiKeyService(session)
        ip_list = ["10.0.0.0/8", "192.168.0.0/16"]
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
            ip_allowlist=ip_list,
        )
        await session.commit()

        key = await session.get(ApiKey, issued.api_key_id)
        assert key.ip_allowlist == ip_list


class TestApiKeyVerify:
    """Test ApiKeyService.verify()."""

    @pytest.mark.asyncio
    async def test_verify_valid_key(self, session: AsyncSession):
        """Verify with correct plaintext returns the key."""
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
        )
        await session.commit()

        # Verify with same plaintext
        key = await svc.verify(issued.plaintext)
        assert key.id == issued.api_key_id
        assert key.principal_id == "user-123"

    @pytest.mark.asyncio
    async def test_verify_wrong_plaintext(self, session: AsyncSession):
        """Verify with wrong plaintext raises ApiKeyError."""
        svc = ApiKeyService(session)
        await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
        )
        await session.commit()

        # Verify with wrong plaintext
        with pytest.raises(ApiKeyError):
            await svc.verify("hlk_" + "x" * 40)

    @pytest.mark.asyncio
    async def test_verify_after_revoke(self, session: AsyncSession):
        """Verify after revoke raises ApiKeyRevoked."""
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
        )
        await session.commit()

        # Revoke the key
        await svc.revoke(issued.api_key_id)
        await session.commit()

        # Verify should raise ApiKeyRevoked
        with pytest.raises(ApiKeyRevoked):
            await svc.verify(issued.plaintext)

    @pytest.mark.asyncio
    async def test_verify_after_expiry(self, session: AsyncSession):
        """Verify after expiry raises ApiKeyExpired."""
        svc = ApiKeyService(session)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=1)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
            expires_at=expires,
        )
        await session.commit()

        # Verify before expiry should work
        key = await svc.verify(issued.plaintext, now=now)
        assert key.id == issued.api_key_id

        # Verify at/after expiry should raise ApiKeyExpired
        future = expires + timedelta(seconds=1)
        with pytest.raises(ApiKeyExpired):
            await svc.verify(issued.plaintext, now=future)

    @pytest.mark.asyncio
    async def test_verify_with_ip_in_allowlist(self, session: AsyncSession):
        """Verify with IP in allowlist succeeds."""
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
            ip_allowlist=["10.0.0.0/8"],
        )
        await session.commit()

        # Verify with IP in allowlist
        key = await svc.verify(issued.plaintext, source_ip="10.0.0.5")
        assert key.id == issued.api_key_id

    @pytest.mark.asyncio
    async def test_verify_with_ip_not_in_allowlist(self, session: AsyncSession):
        """Verify with IP not in allowlist raises ApiKeyIPDenied."""
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
            ip_allowlist=["10.0.0.0/8"],
        )
        await session.commit()

        # Verify with IP not in allowlist
        with pytest.raises(ApiKeyIPDenied):
            await svc.verify(issued.plaintext, source_ip="192.168.1.1")

    @pytest.mark.asyncio
    async def test_verify_with_allowlist_but_no_source_ip_denies(self, session: AsyncSession):
        """Verify with allowlist set but source_ip=None raises ApiKeyIPDenied."""
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
            ip_allowlist=["10.0.0.0/8"],
        )
        await session.commit()

        # Verify without source_ip when allowlist is set should deny
        with pytest.raises(ApiKeyIPDenied):
            await svc.verify(issued.plaintext, source_ip=None)

    @pytest.mark.asyncio
    async def test_verify_without_allowlist_and_no_source_ip_succeeds(self, session: AsyncSession):
        """Verify without allowlist and source_ip=None succeeds."""
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
            ip_allowlist=[],
        )
        await session.commit()

        # Verify without source_ip when allowlist is empty should succeed
        key = await svc.verify(issued.plaintext, source_ip=None)
        assert key.id == issued.api_key_id

    @pytest.mark.asyncio
    async def test_verify_updates_last_used_at(self, session: AsyncSession):
        """Verify updates last_used_at."""
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
        )
        await session.commit()

        key_before = await session.get(ApiKey, issued.api_key_id)
        assert key_before.last_used_at is None

        now = datetime.now(timezone.utc)
        await svc.verify(issued.plaintext, now=now)
        await session.commit()

        key_after = await session.get(ApiKey, issued.api_key_id)
        assert key_after.last_used_at == now


class TestApiKeyRevoke:
    """Test ApiKeyService.revoke()."""

    @pytest.mark.asyncio
    async def test_revoke_sets_revoked_at(self, session: AsyncSession):
        """Revoke sets revoked_at."""
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
        )
        await session.commit()

        key_before = await session.get(ApiKey, issued.api_key_id)
        assert key_before.revoked_at is None

        now = datetime.now(timezone.utc)
        await svc.revoke(issued.api_key_id, now=now)
        await session.commit()

        key_after = await session.get(ApiKey, issued.api_key_id)
        assert key_after.revoked_at == now

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key_no_error(self, session: AsyncSession):
        """Revoke of nonexistent key does not error."""
        svc = ApiKeyService(session)
        # Should not raise
        await svc.revoke("nonexistent-id")

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_key_no_error(self, session: AsyncSession):
        """Revoke of already-revoked key does not error."""
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id="user-123",
            principal_kind="user",
            name="my-key",
        )
        await session.commit()

        # Revoke once
        await svc.revoke(issued.api_key_id)
        await session.commit()

        # Revoke again should not error
        await svc.revoke(issued.api_key_id)


@pytest.mark.asyncio
async def test_issue_rejects_invalid_cidr(session: AsyncSession):
    """Issue rejects invalid CIDR strings."""
    svc = ApiKeyService(session)
    with pytest.raises(ValueError):
        await svc.issue(
            principal_id="u-1", principal_kind="user",
            name="bad", ip_allowlist=["not-a-cidr"],
        )


@pytest.mark.asyncio
async def test_verify_skips_malformed_stored_cidr(session: AsyncSession):
    """If a stored allowlist entry is malformed, verify treats it as no-match."""
    from server.app.auth.api_key import generate_plaintext, hash_plaintext
    plaintext = generate_plaintext()
    # Manually create a row with a corrupt allowlist (simulates schema drift)
    row = ApiKey(
        id="k-bad-cidr", prefix=plaintext[:8], last_4=plaintext[-4:],
        key_hash=hash_plaintext(plaintext), principal_id="u-1",
        principal_kind="user", name="legacy",
        ip_allowlist=["not-a-cidr", "10.0.0.0/8"],
    )
    session.add(row)
    await session.commit()

    svc = ApiKeyService(session)
    # IP in 10.0.0.0/8 → still matches via the second valid entry
    match = await svc.verify(plaintext, source_ip="10.0.0.5")
    assert match.id == "k-bad-cidr"


@pytest.mark.asyncio
async def test_last_used_at_not_updated_on_failed_verify(session: AsyncSession):
    """If verify raises (revoked/expired/IP-denied), last_used_at must NOT change."""
    svc = ApiKeyService(session)
    issued = await svc.issue(
        principal_id="u-1", principal_kind="user", name="t",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    await session.commit()
    before = (await session.get(ApiKey, issued.api_key_id)).last_used_at
    with pytest.raises(ApiKeyExpired):
        await svc.verify(issued.plaintext)
    await session.rollback()
    after = (await session.get(ApiKey, issued.api_key_id)).last_used_at
    assert after == before


@pytest.mark.asyncio
async def test_multiple_keys_same_prefix_disambiguated_by_hash(session: AsyncSession):
    """Multiple rows with same prefix are disambiguated by constant-time hash compare."""
    from server.app.auth.api_key import generate_plaintext, hash_plaintext
    # Generate two plaintexts; we'll force them to share a prefix for this test
    plain1 = generate_plaintext()
    plain2 = generate_plaintext()
    shared_prefix = parse_prefix(plain1)

    # Create two rows with the same prefix but different hashes
    row1 = ApiKey(id="k1", prefix=shared_prefix, last_4=plain1[-4:],
                  key_hash=hash_plaintext(plain1), principal_id="u-1",
                  principal_kind="user", name="a", ip_allowlist=[])
    row2 = ApiKey(id="k2", prefix=shared_prefix, last_4=plain2[-4:],
                  key_hash=hash_plaintext(plain2), principal_id="u-2",
                  principal_kind="user", name="b", ip_allowlist=[])
    session.add_all([row1, row2])
    await session.commit()

    svc = ApiKeyService(session)
    # Verifying plain1 should match row1 despite row2 having the same prefix
    m1 = await svc.verify(plain1)
    assert m1.id == "k1"

    # Verify constant-time comparison works correctly when multiple rows
    # share the same prefix: row1 matches plain1's hash, row2 doesn't
    assert secrets.compare_digest(row1.key_hash, hash_plaintext(plain1))
    assert not secrets.compare_digest(row1.key_hash, hash_plaintext(plain2))
