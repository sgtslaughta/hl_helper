"""Tests for AgentRelease model."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.models.agent_release import AgentRelease, ReleaseChannel, ReleaseStatus


@pytest.mark.asyncio
async def test_agent_release_persists(sm):
    """Test that AgentRelease persists with auto-generated id and uploaded_at."""
    async with sm() as session:
        rel = AgentRelease(
            version="0.4.2",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="amd64",
            sha256="a" * 64,
            size=12345,
            manifest_json=b"{}",
            manifest_sig=b"\x00" * 64,
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="ci",
        )
        session.add(rel)
        await session.flush()
        assert rel.id is not None
        assert rel.uploaded_at is not None


@pytest.mark.asyncio
async def test_agent_release_unique_per_version_arch(sm):
    """Test that (version, os, arch) is unique."""
    async with sm() as session:
        base = dict(
            version="0.4.2",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="amd64",
            size=1,
            manifest_json=b"{}",
            manifest_sig=b"\x00" * 64,
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="ci",
        )
        session.add(AgentRelease(sha256="a" * 64, **base))
        await session.flush()
        session.add(AgentRelease(sha256="b" * 64, **base))
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_agent_release_defaults(sm):
    """Test that status defaults to STAGED and uploaded_at is set."""
    async with sm() as session:
        rel = AgentRelease(
            version="0.5.0",
            channel=ReleaseChannel.BETA,
            os="windows",
            arch="x86_64",
            sha256="c" * 64,
            size=54321,
            manifest_json=b"{}",
            manifest_sig=b"\x00" * 64,
            uploaded_by="release-bot",
        )
        session.add(rel)
        await session.flush()
        assert rel.status == ReleaseStatus.STAGED
        assert rel.yanked_at is None
        assert rel.yanked_reason is None
