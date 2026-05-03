"""Search-expression parser → SQLAlchemy WHERE clause.

Bounded depth (default 4), limited operators, per-collection field allowlist.

Example:
    clause = parse(
        {"and": [
            {"contains": {"hostname": "prod"}},
            {"since": {"enrolled_at": "2026-01-01T00:00:00"}}
        ]},
        SearchSchema(fields={"hostname": Host.hostname, "enrolled_at": Host.enrolled_at})
    )
    rows = await session.execute(select(Host).where(clause))
"""

from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from typing import Any, Mapping, cast

from sqlalchemy import and_, or_, not_, func
from sqlalchemy.sql.elements import ColumnElement


class SearchError(ValueError):
    """Raised when the search expression is malformed, too deep, or uses a
    disallowed operator/field."""


_BOOL_OPS = {"and", "or", "not"}
_LEAF_OPS = {"eq", "in", "contains", "since", "before"}


def _escape_like(s: str) -> str:
    """Escape SQL LIKE wildcards (% and _) so they match literally."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class SearchSchema:
    """Per-collection allowlist + column resolver.

    `fields` maps a public field name (e.g. "hostname") to a SQLAlchemy
    column object. Only listed fields are queryable.
    """

    fields: Mapping[str, ColumnElement[Any]]
    max_depth: int = 4


def parse(expr: Mapping[str, Any], schema: SearchSchema) -> ColumnElement[Any]:
    """Convert `expr` into a SQLAlchemy boolean expression.

    Raises SearchError on any depth, operator, or field violation.
    """
    return _parse_node(expr, schema, depth=0)


def _parse_node(
    node: Any, schema: SearchSchema, *, depth: int
) -> ColumnElement[Any]:
    if depth >= schema.max_depth:
        raise SearchError(f"depth_exceeded: {depth} >= {schema.max_depth}")
    if not isinstance(node, dict) or len(node) != 1:
        raise SearchError(f"malformed_node: {node!r}")
    (op, body) = next(iter(node.items()))
    if op in _BOOL_OPS:
        return _parse_bool(op, body, schema, depth)
    if op in _LEAF_OPS:
        return _parse_leaf(op, body, schema)
    raise SearchError(f"unknown_op: {op!r}")


def _parse_bool(
    op: str, body: Any, schema: SearchSchema, depth: int
) -> ColumnElement[Any]:
    if op == "not":
        if not isinstance(body, dict):
            raise SearchError("not_requires_object")
        return not_(_parse_node(body, schema, depth=depth + 1))
    if not isinstance(body, list) or not body:
        raise SearchError(f"{op}_requires_nonempty_list")
    children = [_parse_node(c, schema, depth=depth + 1) for c in body]
    return (and_ if op == "and" else or_)(*children)


def _parse_leaf(op: str, body: Any, schema: SearchSchema) -> ColumnElement[Any]:
    if not isinstance(body, dict) or len(body) != 1:
        raise SearchError(f"{op}_requires_single_field_object")
    field, value = next(iter(body.items()))
    if field not in schema.fields:
        raise SearchError(f"field_not_allowed: {field!r}")
    col = schema.fields[field]
    if op == "eq":
        return cast(ColumnElement[Any], col == value)
    if op == "in":
        if not isinstance(value, list) or not value:
            raise SearchError("in_requires_nonempty_list")
        if len(value) > 100:
            raise SearchError("in_list_too_long")
        return cast(ColumnElement[Any], col.in_(value))
    if op == "contains":
        if not isinstance(value, str):
            raise SearchError("contains_requires_string")
        safe = _escape_like(value.lower())
        return cast(ColumnElement[Any], func.lower(col).like(f"%{safe}%", escape="\\"))
    if op == "since":
        return cast(ColumnElement[Any], col >= _parse_dt(value))
    if op == "before":
        return cast(ColumnElement[Any], col < _parse_dt(value))
    raise SearchError(f"unknown_leaf_op: {op}")


def _parse_dt(s: Any) -> datetime:
    if not isinstance(s, str):
        raise SearchError("datetime_must_be_iso_string")
    try:
        return datetime.fromisoformat(s)
    except ValueError as e:
        raise SearchError(f"invalid_datetime: {s}") from e
