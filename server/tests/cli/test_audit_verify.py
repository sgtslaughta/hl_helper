"""Tests for server.cli.audit_verify."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.sql import text

from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.signing import FileBackend
from server.app.db.session import make_engine, make_sessionmaker
from server.app.models import Base
from server.cli.audit_verify import main


@pytest.fixture
def signing_dir(tmp_path: Path) -> Path:
    """Create a signing key directory."""
    signing_path = tmp_path / "signing"
    FileBackend.bootstrap(signing_path)
    return signing_path


@pytest_asyncio.fixture
async def test_db(tmp_path: Path) -> str:
    """Create a file-based SQLite engine and return its URL."""
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = make_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return url


@pytest_asyncio.fixture
async def chain_with_entries(test_db: str, signing_dir: Path) -> tuple[str, Path, int]:
    """Create a chain with 5 entries."""
    backend = FileBackend(signing_dir)
    engine = make_engine(test_db)
    sm = make_sessionmaker(engine)

    async with sm() as session:
        chain = SqlAuditChain(backend, checkpoint_interval=100)
        for i in range(5):
            await chain.append(
                session,
                actor=f"user{i}",
                action=f"action{i}",
                subject=f"subject{i}",
                payload={"index": i},
            )
        await session.commit()

    await engine.dispose()
    return test_db, signing_dir, 5


class TestVerifyPass:
    """Test verify subcommand with valid chain."""

    @pytest.mark.asyncio
    async def test_verify_pass(
        self, chain_with_entries: tuple[str, Path, int], capsys
    ) -> None:
        """Verify a valid chain returns exit code 0 with PASS."""
        test_db, signing_dir, expected_entries = chain_with_entries

        # Call main with verify subcommand
        exit_code = await main(
            [
                "verify",
                "--db-url",
                test_db,
                "--signing-dir",
                str(signing_dir),
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PASS" in captured.out


class TestVerifyDetectsTampering:
    """Test verify detects tampered entries."""

    @pytest.mark.asyncio
    async def test_verify_detects_tampered_entry(
        self, chain_with_entries: tuple[str, Path, int], capsys
    ) -> None:
        """Verify detects when an entry is tampered."""
        test_db, signing_dir, _ = chain_with_entries

        # Tamper with one entry's entry_hash directly via SQL
        # This will cause verification to fail because recomputed hash won't match
        engine = make_engine(test_db)
        bad_hash = b"\x00" * 32
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE audit_entries SET entry_hash = :hash WHERE sequence = 2").bindparams(
                    hash=bad_hash
                )
            )
        await engine.dispose()

        # Run verify
        exit_code = await main(
            [
                "verify",
                "--db-url",
                test_db,
                "--signing-dir",
                str(signing_dir),
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "FAIL" in captured.out


class TestExportStreamsNdjson:
    """Test export subcommand streams NDJSON."""

    @pytest.mark.asyncio
    async def test_export_streams_ndjson(
        self, chain_with_entries: tuple[str, Path, int], capsys
    ) -> None:
        """Export streams audit entries as NDJSON."""
        test_db, _, expected_entries = chain_with_entries

        # Call export
        exit_code = await main(["export", "--db-url", test_db])

        assert exit_code == 0
        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == expected_entries

        # Parse each line as JSON
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data["sequence"] == i
            assert "timestamp" in data
            assert "actor" in data
            assert "action" in data
            assert "subject" in data
            assert "payload" in data
            assert "prev_hash" in data
            assert "entry_hash" in data


class TestExportSinceSequence:
    """Test export with --since-sequence filter."""

    @pytest.mark.asyncio
    async def test_export_since_sequence(
        self, chain_with_entries: tuple[str, Path, int], capsys
    ) -> None:
        """Export respects --since-sequence filter."""
        test_db, _, total_entries = chain_with_entries

        # Export only entries >= seq 2
        exit_code = await main(
            ["export", "--db-url", test_db, "--since-sequence", "2"]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]

        # Should have 3 entries (2, 3, 4)
        assert len(lines) == 3

        # Verify they are the right sequences
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data["sequence"] == i + 2


class TestExportWithLimit:
    """Test export with --limit filter."""

    @pytest.mark.asyncio
    async def test_export_with_limit(
        self, chain_with_entries: tuple[str, Path, int], capsys
    ) -> None:
        """Export respects --limit parameter."""
        test_db, _, _ = chain_with_entries

        # Export only 2 entries
        exit_code = await main(["export", "--db-url", test_db, "--limit", "2"])

        assert exit_code == 0
        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]

        assert len(lines) == 2
