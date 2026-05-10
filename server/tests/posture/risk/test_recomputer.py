"""Tests for RiskRecomputer service."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from server.app.models import Base
from server.app.models.host import Host
from server.app.models.host_risk import HostRisk
from server.app.posture.model import PostureFindingRow
from server.app.posture.risk.recomputer import RiskRecomputer
from server.app.posture.risk.registry import ScorerRegistry
from server.app.posture.risk.types import SubScore


@pytest_asyncio.fixture
async def test_engine() -> AsyncEngine:
    """Create an in-memory SQLite engine and initialize all tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_sm(test_engine: AsyncEngine) -> async_sessionmaker:
    """Create a sessionmaker for the test engine."""
    from server.app.db.session import make_sessionmaker
    return make_sessionmaker(test_engine)


@pytest_asyncio.fixture
async def test_host(test_sm: async_sessionmaker) -> str:
    """Create a test host."""
    async with test_sm() as session:
        host = Host(
            id=str(uuid4()),
            hostname="test-host",
            display_name="test-host",
            agent_pubkey=b"\x00" * 32,
            labels={"os": "linux", "arch": "x86_64"},
            agent_version="0.4.0",
        )
        session.add(host)
        await session.commit()
        return host.id


@pytest_asyncio.fixture
def mock_bus() -> AsyncMock:
    """Create a mock event bus."""
    return AsyncMock()


@pytest_asyncio.fixture
def mock_audit() -> AsyncMock:
    """Create a mock audit chain."""
    audit = AsyncMock()
    audit.append = AsyncMock()
    return audit


@pytest_asyncio.fixture
def mock_scorer_registry() -> ScorerRegistry:
    """Create a mock scorer registry with a single test scorer."""
    registry = ScorerRegistry()

    # Create a minimal test scorer
    class TestScorer:
        name = "test_scorer"
        label = "Test Scorer"
        description = "A test scoring pillar"
        weight_default = 0.5
        enabled_by_default = True

        async def score(self, ctx):
            return SubScore(score=30, confidence=0.8)

    scorer = TestScorer()
    registry.register(scorer)
    return registry


@pytest_asyncio.fixture
async def recomputer(
    test_sm: async_sessionmaker,
    mock_scorer_registry: ScorerRegistry,
    mock_bus: AsyncMock,
    mock_audit: AsyncMock,
) -> RiskRecomputer:
    """Create a RiskRecomputer instance."""
    return RiskRecomputer(
        test_sm,
        mock_scorer_registry,
        bus=mock_bus,
        audit=mock_audit,
    )


class TestRecomputer:
    """Tests for RiskRecomputer."""

    async def test_recompute_writes_host_risk_row(
        self,
        test_sm: async_sessionmaker,
        test_host: str,
        recomputer: RiskRecomputer,
    ):
        """Test that recompute writes a HostRisk row with valid level."""
        await recomputer.recompute(test_host, trigger_reason="test")

        async with test_sm() as session:
            risk = await session.get(HostRisk, test_host)
            assert risk is not None
            assert risk.host_id == test_host
            assert risk.level in [
                "minimal",
                "stable",
                "moderate",
                "elevated",
                "high",
                "severe",
                "unknown",
            ]
            assert risk.inputs_hash is not None
            assert isinstance(risk.inputs_hash, str)
            assert len(risk.inputs_hash) == 64  # SHA256 hex digest
            assert risk.computed_at is not None

    async def test_recompute_skips_when_inputs_hash_matches(
        self,
        test_sm: async_sessionmaker,
        test_host: str,
        recomputer: RiskRecomputer,
    ):
        """Test that recompute skips when input hash hasn't changed."""
        # First recompute
        await recomputer.recompute(test_host, trigger_reason="test")
        writes_after_first = recomputer._writes

        # Second recompute with identical state
        await recomputer.recompute(test_host, trigger_reason="test")
        writes_after_second = recomputer._writes

        # Should not write again
        assert writes_after_second == writes_after_first

    async def test_request_debounces_within_30s(
        self,
        test_host: str,
        recomputer: RiskRecomputer,
    ):
        """Test that request debounces calls within 30 seconds."""
        _ = recomputer._writes

        # Call request twice in rapid succession
        await recomputer.request(test_host, trigger_reason="test1")
        writes_after_first = recomputer._writes

        await recomputer.request(test_host, trigger_reason="test2")
        writes_after_second = recomputer._writes

        # Second call should be debounced and not trigger a new recompute
        assert writes_after_second == writes_after_first

    async def test_recompute_emits_audit_entry(
        self,
        test_sm: async_sessionmaker,
        test_host: str,
        recomputer: RiskRecomputer,
        mock_audit: AsyncMock,
    ):
        """Test that recompute emits an audit entry."""
        await recomputer.recompute(test_host, trigger_reason="test")

        # Verify audit.append was called
        assert mock_audit.append.called
        call_args = mock_audit.append.call_args
        assert call_args is not None
        # Should have session, actor, action, subject, payload arguments
        assert call_args[1]["actor"] == "system"
        assert call_args[1]["action"] == "risk.recomputed"
        assert call_args[1]["subject"] == test_host

    async def test_recompute_includes_findings_in_hash(
        self,
        test_sm: async_sessionmaker,
        test_host: str,
        recomputer: RiskRecomputer,
    ):
        """Test that findings are included in the inputs hash."""
        # First recompute without findings
        await recomputer.recompute(test_host, trigger_reason="test")
        async with test_sm() as session:
            risk1 = await session.get(HostRisk, test_host)
            hash1 = risk1.inputs_hash

        # Add a finding
        async with test_sm() as session:
            finding = PostureFindingRow(
                id="test-finding",
                rule="test_rule",
                severity="high",
                title="Test Finding",
                summary="A test finding",
                subject_kind="host",
                subject_id=test_host,
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            )
            session.add(finding)
            await session.commit()

        # Recompute again
        await recomputer.recompute(test_host, trigger_reason="test")
        async with test_sm() as session:
            risk2 = await session.get(HostRisk, test_host)
            hash2 = risk2.inputs_hash

        # Hashes should be different due to the new finding
        assert hash1 != hash2
