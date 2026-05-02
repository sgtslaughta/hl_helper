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


@pytest.fixture
def host_schema_with_dt() -> SearchSchema:
    """Schema with a datetime field for since/before testing."""
    return SearchSchema(
        fields={
            "id": Host.id,
            "hostname": Host.hostname,
            "created_at": Host.created_at,
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
    """Test that depth limit is enforced at max_depth boundary."""
    # max_depth=4 means depths 0,1,2,3 are OK; depth 4 raises
    nested = {"eq": {"hostname": "h"}}
    # Build {"and": [{"and": [{"and": [{"and": [nested]}]}]}]}
    for _ in range(4):
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


def test_depth_at_limit_passes(host_schema):
    """Nesting exactly at max_depth must succeed."""
    nested = {"eq": {"hostname": "h"}}
    # max_depth=4 means we can nest up to depth 3 (depths 0,1,2,3)
    for _ in range(3):
        nested = {"and": [nested]}
    # Should not raise
    parse(nested, host_schema)


def test_depth_at_limit_plus_one_fails(host_schema):
    """Nesting at max_depth + 1 must fail."""
    nested = {"eq": {"hostname": "h"}}
    for _ in range(4):
        nested = {"and": [nested]}
    with pytest.raises(SearchError, match="depth_exceeded"):
        parse(nested, host_schema)


def test_since_clause(host_schema_with_dt):
    """since (>=) operator with ISO datetime."""
    clause = parse(
        {"since": {"created_at": "2026-01-01T00:00:00"}}, host_schema_with_dt
    )
    assert clause is not None


def test_before_clause(host_schema_with_dt):
    """before (<) operator with ISO datetime."""
    clause = parse(
        {"before": {"created_at": "2026-12-31T23:59:59"}}, host_schema_with_dt
    )
    assert clause is not None


def test_invalid_iso_datetime_rejected(host_schema_with_dt):
    """Invalid datetime strings must be rejected."""
    with pytest.raises(SearchError, match="invalid_datetime"):
        parse(
            {"since": {"created_at": "not-a-date"}}, host_schema_with_dt
        )


def test_datetime_must_be_string(host_schema_with_dt):
    """Datetime values must be strings, not numbers."""
    with pytest.raises(SearchError, match="datetime_must_be_iso_string"):
        parse({"since": {"created_at": 12345}}, host_schema_with_dt)


def test_not_with_non_dict_rejected(host_schema):
    """The 'not' operator requires a dict body, not a list."""
    with pytest.raises(SearchError, match="not_requires_object"):
        parse({"not": [{"eq": {"id": "x"}}]}, host_schema)


def test_max_depth_configurable():
    """max_depth can be customized per schema."""
    schema = SearchSchema(fields={"id": Host.id}, max_depth=2)
    nested = {"eq": {"id": "x"}}
    nested = {"and": [nested]}  # depth 1
    parse(nested, schema)  # ok
    nested = {"and": [nested]}  # depth 2 → raises with new strict boundary
    with pytest.raises(SearchError, match="depth_exceeded"):
        parse(nested, schema)


@pytest.mark.asyncio
async def test_contains_escapes_like_wildcards(sm, host_schema):
    """User input '%' and '_' must NOT act as SQL LIKE wildcards."""
    async with sm() as session:
        session.add_all([
            Host(id="lit-1", hostname="foo%bar", agent_pubkey=b"\x00" * 32),
            Host(id="lit-2", hostname="fooXbar", agent_pubkey=b"\x00" * 32),
        ])
        await session.commit()
        clause = parse({"contains": {"hostname": "foo%bar"}}, host_schema)
        rows = (await session.execute(select(Host).where(clause))).scalars().all()
        ids = {r.id for r in rows}
        # Only literal 'foo%bar' matches — wildcard 'fooXbar' must NOT
        assert "lit-1" in ids
        assert "lit-2" not in ids


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
