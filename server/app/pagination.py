"""Cursor pagination helper.

Why a cursor + last_id pair: with naive offset paging (`LIMIT N OFFSET M`),
inserts before the offset shift rows; users see duplicates or skips. Pairing
the sort key with the row id lets us issue `(sort_key, id) > (?, ?)` predicates
that are stable under concurrent insert.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import and_, or_
from sqlalchemy.sql import Select


@dataclass(frozen=True)
class Cursor:
    sort_value: Any
    last_id: str

    def encode(self) -> str:
        # Default-encode datetime / date by isoformat
        sv = self.sort_value
        if hasattr(sv, "isoformat"):
            sv = sv.isoformat()
        payload = json.dumps({"v": sv, "i": self.last_id}, separators=(",", ":"))
        return base64.urlsafe_b64encode(payload.encode("utf-8")).rstrip(b"=").decode("ascii")

    @classmethod
    def decode(cls, raw: str) -> "Cursor":
        pad = "=" * ((4 - len(raw) % 4) % 4)
        data = base64.urlsafe_b64decode(raw + pad).decode("utf-8")
        d = json.loads(data)
        return cls(sort_value=d["v"], last_id=d["i"])


@dataclass(frozen=True)
class Page:
    items: list[Any]
    next_cursor: str | None  # None = no more


def apply_cursor(
    stmt: Select[tuple[Any, ...]],
    *,
    sort_column: Any,         # SQLAlchemy column for the primary sort key
    id_column: Any,           # SQLAlchemy column for the tiebreaker (typically PK)
    cursor: str | None,
    limit: int,
    descending: bool = False,
) -> Select[tuple[Any, ...]]:
    """Return `stmt` with cursor predicate applied + ORDER BY + LIMIT.

    Always selects `limit + 1` rows so the caller can detect a next page;
    use `build_page()` on the resulting query rows.
    """
    if cursor:
        c = Cursor.decode(cursor)
        if descending:
            stmt = stmt.where(
                or_(
                    sort_column < c.sort_value,
                    and_(sort_column == c.sort_value, id_column < c.last_id),
                )
            )
        else:
            stmt = stmt.where(
                or_(
                    sort_column > c.sort_value,
                    and_(sort_column == c.sort_value, id_column > c.last_id),
                )
            )
    if descending:
        stmt = stmt.order_by(sort_column.desc(), id_column.desc())
    else:
        stmt = stmt.order_by(sort_column.asc(), id_column.asc())
    return stmt.limit(limit + 1)


def build_page(
    rows: Sequence[Any],
    *,
    limit: int,
    sort_attr: str,
    id_attr: str,
) -> Page:
    """Trim the limit+1 result set into a Page with optional next_cursor."""
    if len(rows) > limit:
        kept = list(rows[:limit])
        last = kept[-1]
        next_cursor = Cursor(getattr(last, sort_attr), getattr(last, id_attr)).encode()
    else:
        kept = list(rows)
        next_cursor = None
    return Page(items=kept, next_cursor=next_cursor)
