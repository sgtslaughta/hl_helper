"""CLI for audit chain verification and export."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

from server.app.audit.chain import ChainBrokenError, CheckpointError
from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.signing import FileBackend
from server.app.db.session import make_engine, make_sessionmaker
from server.app.models.audit import AuditEntry


async def main(argv: list[str] | None = None) -> int:
    """Parse args and execute verify or export subcommand.

    Args:
        argv: Command-line arguments (for testing). If None, uses sys.argv[1:].

    Returns:
        0 on success, 1 on verification failure, 2 on usage error.
    """
    parser = argparse.ArgumentParser(
        prog="python -m server.cli.audit_verify",
        description="Verify and export audit chain",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand")

    # verify subcommand
    verify_parser = subparsers.add_parser("verify", help="Verify audit chain integrity")
    verify_parser.add_argument(
        "--db-url",
        required=True,
        help="SQLAlchemy database URL (e.g. sqlite+aiosqlite:///./fleet.db)",
    )
    verify_parser.add_argument(
        "--signing-dir",
        required=True,
        type=Path,
        help="Path to FileBackend signing key directory",
    )

    # export subcommand
    export_parser = subparsers.add_parser("export", help="Export audit entries as NDJSON")
    export_parser.add_argument(
        "--db-url",
        required=True,
        help="SQLAlchemy database URL (e.g. sqlite+aiosqlite:///./fleet.db)",
    )
    export_parser.add_argument(
        "--since-sequence",
        type=int,
        default=None,
        help="Only export entries with sequence >= this value",
    )
    export_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of entries exported",
    )

    try:
        if argv is None:
            argv = sys.argv[1:]
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code != 0 else 0

    if args.command == "verify":
        return await _verify(args.db_url, args.signing_dir)
    elif args.command == "export":
        return await _export(args.db_url, args.since_sequence, args.limit)
    else:
        return 2


async def _verify(db_url: str, signing_dir: Path) -> int:
    """Verify audit chain integrity.

    Returns 0 if chain is valid, 1 if verification fails.
    """
    try:
        engine = make_engine(db_url)
    except Exception as e:
        print(f"ERROR: invalid --db-url: {e}", file=sys.stderr)
        return 2

    sm = make_sessionmaker(engine)
    backend = FileBackend(signing_dir)

    try:
        async with sm() as session:
            chain = SqlAuditChain(backend)
            await chain.verify(session)
            num_entries = await chain.length(session)

        print(f"PASS: Verified {num_entries} entries")
        return 0

    except (ChainBrokenError, CheckpointError) as e:
        # Surface sequence/locator from the exception when present.
        seq = getattr(e, "sequence", None)
        if seq is not None:
            print(f"FAIL at sequence={seq}: {e}")
        else:
            print(f"FAIL: {e}")
        return 1
    finally:
        await engine.dispose()


async def _export(
    db_url: str, since_sequence: int | None = None, limit: int | None = None
) -> int:
    """Export audit entries as NDJSON.

    Returns:
        0 on success.
    """
    engine = make_engine(db_url)
    sm = make_sessionmaker(engine)

    try:
        async with sm() as session:
            stmt = select(AuditEntry).order_by(AuditEntry.sequence.asc())

            if since_sequence is not None:
                stmt = stmt.where(AuditEntry.sequence >= since_sequence)

            if limit is not None:
                stmt = stmt.limit(limit)

            result = await session.stream_scalars(stmt)
            async for entry in result:
                entry_dict = {
                    "sequence": entry.sequence,
                    "timestamp": entry.timestamp.isoformat(),
                    "actor": entry.actor,
                    "action": entry.action,
                    "subject": entry.subject,
                    "payload": entry.payload,
                    "prev_hash": entry.prev_hash.hex(),
                    "entry_hash": entry.entry_hash.hex(),
                }
                print(json.dumps(entry_dict, ensure_ascii=False, default=str))

        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
