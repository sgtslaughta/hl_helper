"""Tests for the search expression parser."""

import pytest
from sqlalchemy import select

from server.app.search.parser import parse, SearchSchema, SearchError
from server.app.models import Host


@pytest.fixture
def host_schema() -> SearchSchema:
    return SearchSchema(
        fields={
            "id": Host.id,
            "hostname": Host.hostname,
        },
        max_depth=4,
    )


def test_eq_clause_compiles(host_schema):
    """Test that eq operator produces a valid SQLAlchemy clause."""
    clause = parse({"eq": {"hostname": "h-1"}}, host_schema)
    assert clause is not None


def test_unknown_op_rejected(host_schema):
    """Test that unknown operators are rejected."""
    with pytest.raises(SearchError, match="unknown_op"):
        parse({"unknownop": {}}, host_schema)


def test_unknown_field_rejected(host_schema):
    """Test that fields not in schema are rejected."""
    with pytest.raises(SearchError, match="field_not_allowed"):
        parse({"eq": {"agent_pubkey": "x"}}, host_schema)


def test_depth_limit_enforced(host_schema):
    """Test that depth limit is enforced."""
    # Build {"and": [{"and": [{"and": [{"and": [{"eq": ...}]}]}]}]} → depth=4 root, deeper inside
    nested = {"eq": {"hostname": "h"}}
    # Each {"and": [...]} adds one level
    for _ in range(5):
        nested = {"and": [nested]}
    with pytest.raises(SearchError, match="depth_exceeded"):
        parse(nested, host_schema)


def test_in_clause(host_schema):
    """Test that in operator produces a valid clause."""
    clause = parse({"in": {"id": ["h-1", "h-2", "h-3"]}}, host_schema)
    assert clause is not None


def test_in_empty_list_rejected(host_schema):
    """Test that empty list for in is rejected."""
    with pytest.raises(SearchError, match="in_requires_nonempty_list"):
        parse({"in": {"id": []}}, host_schema)


def test_contains_clause(host_schema):
    """Test that contains operator produces a valid clause."""
    clause = parse({"contains": {"hostname": "prod"}}, host_schema)
    assert clause is not None


def test_and_or_not_combo(host_schema):
    """Test combining and, or, not operators."""
    clause = parse({
        "and": [
            {"or": [{"eq": {"hostname": "a"}}, {"eq": {"hostname": "b"}}]},
            {"not": {"eq": {"id": "x"}}},
        ]
    }, host_schema)
    assert clause is not None


def test_malformed_node_rejected(host_schema):
    """Test that malformed nodes are rejected."""
    with pytest.raises(SearchError, match="malformed_node"):
        parse({"and": [{}, {}]}, host_schema)  # empty leaf node


@pytest.mark.asyncio
async def test_parse_clause_executes_against_db(sm, host_schema):
    """End-to-end: build clause, run query, get expected row."""
    async with sm() as session:
        session.add(Host(id="srch-1", hostname="apple", agent_pubkey=b"\x00" * 32))
        session.add(Host(id="srch-2", hostname="banana", agent_pubkey=b"\x00" * 32))
        await session.commit()

        clause = parse({"contains": {"hostname": "appl"}}, host_schema)
        rows = (await session.execute(select(Host).where(clause))).scalars().all()
        ids = {r.id for r in rows}
        assert "srch-1" in ids
        assert "srch-2" not in ids
