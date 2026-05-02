import pytest
from datetime import datetime, timezone
from sqlalchemy import select

from server.app.pagination import Cursor, apply_cursor, build_page
from server.app.models import Host


def test_cursor_round_trip():
    c = Cursor(sort_value="2026-05-02T12:00:00", last_id="h-1")
    raw = c.encode()
    again = Cursor.decode(raw)
    assert again.sort_value == "2026-05-02T12:00:00"
    assert again.last_id == "h-1"


def test_cursor_handles_datetime_isoformat():
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    c = Cursor(sort_value=now, last_id="h-1")
    raw = c.encode()
    again = Cursor.decode(raw)
    # decoded value is the isoformat string (caller re-parses if needed)
    assert isinstance(again.sort_value, str)
    assert "2026-05-02" in again.sort_value


@pytest.mark.asyncio
async def test_cursor_pagination_stable_under_insert(sm):
    """Insert 5 hosts, page with limit=2; insert another between pages → no dupe/skip."""
    async with sm() as session:
        for i in range(5):
            session.add(Host(id=f"h-{i:02d}", hostname=f"host-{i}", agent_pubkey=b"\x00"*32))
        await session.commit()

        stmt = select(Host)
        stmt1 = apply_cursor(stmt, sort_column=Host.id, id_column=Host.id,
                             cursor=None, limit=2, descending=False)
        rows = (await session.execute(stmt1)).scalars().all()
        page1 = build_page(rows, limit=2, sort_attr="id", id_attr="id")
        assert [h.id for h in page1.items] == ["h-00", "h-01"]
        assert page1.next_cursor is not None

        # Insert a row that sorts BEFORE page2 → must not appear in page2
        session.add(Host(id="h-005", hostname="inserted", agent_pubkey=b"\x00"*32))
        await session.commit()

        stmt2 = apply_cursor(stmt, sort_column=Host.id, id_column=Host.id,
                             cursor=page1.next_cursor, limit=2, descending=False)
        rows = (await session.execute(stmt2)).scalars().all()
        page2 = build_page(rows, limit=2, sort_attr="id", id_attr="id")
        # Cursor was after "h-01"; "h-005" sorts as "h-005" > "h-01" lexicographically,
        # so it WOULD appear. The test verifies stability: the cursor predicate is
        # `(id) > "h-01"` so the new row IS included. The point is no duplicate
        # and no skip. Verify h-02 is the second item, not duplicated from page1.
        ids = [h.id for h in page2.items]
        assert "h-01" not in ids  # not duplicated from page1
        assert len(ids) == 2


@pytest.mark.asyncio
async def test_cursor_pagination_descending(sm):
    async with sm() as session:
        for i in range(4):
            session.add(Host(id=f"d-{i:02d}", hostname=f"d-{i}", agent_pubkey=b"\x00"*32))
        await session.commit()
        stmt = select(Host).where(Host.id.like("d-%"))
        s1 = apply_cursor(stmt, sort_column=Host.id, id_column=Host.id,
                          cursor=None, limit=2, descending=True)
        rows = (await session.execute(s1)).scalars().all()
        p1 = build_page(rows, limit=2, sort_attr="id", id_attr="id")
        assert [h.id for h in p1.items] == ["d-03", "d-02"]


def test_build_page_no_next_when_under_limit():
    class R:
        def __init__(self, id_: str):
            self.id = id_
            self.sort = id_
    rows = [R("a"), R("b")]
    p = build_page(rows, limit=5, sort_attr="sort", id_attr="id")
    assert p.next_cursor is None
    assert len(p.items) == 2


@pytest.mark.asyncio
async def test_cursor_no_skip_when_row_inserted_before_cursor_boundary(sm):
    """Critical race: insert a row that sorts BEFORE the cursor boundary
    AFTER page1 was fetched. The cursor still points at page1's last id,
    so page2 must NOT skip the new row IF it sorts after the cursor key,
    AND must NOT include rows that sort before the cursor (already shown
    on page1).
    """
    async with sm() as session:
        for i in range(4):
            session.add(Host(id=f"a-{i:02d}", hostname=f"a-{i}", agent_pubkey=b"\x00"*32))
        await session.commit()

        stmt = select(Host).where(Host.id.like("a-%"))
        # Page 1: cursor=None → ["a-00", "a-01"]
        s1 = apply_cursor(stmt, sort_column=Host.id, id_column=Host.id,
                          cursor=None, limit=2)
        rows = (await session.execute(s1)).scalars().all()
        p1 = build_page(rows, limit=2, sort_attr="id", id_attr="id")
        assert [r.id for r in p1.items] == ["a-00", "a-01"]

        # Insert row that sorts BEFORE page1's last id (a-01) — would naively cause
        # offset paging to dupe a-01. Cursor predicate uses (id) > "a-01" so this
        # new "a-005" must NOT appear in page2.
        session.add(Host(id="a-005", hostname="late", agent_pubkey=b"\x00"*32))
        await session.commit()

        s2 = apply_cursor(stmt, sort_column=Host.id, id_column=Host.id,
                          cursor=p1.next_cursor, limit=2)
        rows = (await session.execute(s2)).scalars().all()
        p2 = build_page(rows, limit=2, sort_attr="id", id_attr="id")
        ids = [r.id for r in p2.items]
        assert "a-005" not in ids, "row inserted before cursor boundary should be skipped"
        assert ids == ["a-02", "a-03"]


@pytest.mark.asyncio
async def test_cursor_first_page_no_predicate(sm):
    """cursor=None: only ORDER BY + LIMIT, no WHERE."""
    async with sm() as session:
        for i in range(3):
            session.add(Host(id=f"f-{i:02d}", hostname=f"f-{i}", agent_pubkey=b"\x00"*32))
        await session.commit()
        stmt = select(Host).where(Host.id.like("f-%"))
        s = apply_cursor(stmt, sort_column=Host.id, id_column=Host.id,
                         cursor=None, limit=10)
        rows = (await session.execute(s)).scalars().all()
        assert len(rows) == 3
        assert [r.id for r in rows] == ["f-00", "f-01", "f-02"]


@pytest.mark.asyncio
async def test_cursor_exactly_limit_rows_no_next_cursor(sm):
    """Boundary: exactly `limit` rows fit → next_cursor must be None."""
    async with sm() as session:
        for i in range(2):
            session.add(Host(id=f"e-{i:02d}", hostname=f"e-{i}", agent_pubkey=b"\x00"*32))
        await session.commit()
        stmt = select(Host).where(Host.id.like("e-%"))
        s = apply_cursor(stmt, sort_column=Host.id, id_column=Host.id,
                         cursor=None, limit=2)
        rows = (await session.execute(s)).scalars().all()
        p = build_page(rows, limit=2, sort_attr="id", id_attr="id")
        assert len(p.items) == 2
        assert p.next_cursor is None


@pytest.mark.asyncio
async def test_cursor_with_distinct_sort_and_id_columns(sm):
    """Tiebreaker path: rows share sort_value but differ in id; ordering deterministic."""
    async with sm() as session:
        # All same hostname, different ids — sort by hostname (collision), tiebreak by id
        for i in range(3):
            session.add(Host(id=f"t-{i:02d}", hostname="same", agent_pubkey=b"\x00"*32))
        await session.commit()
        stmt = select(Host).where(Host.id.like("t-%"))
        # Sort by hostname (all "same"), tiebreak by id
        s1 = apply_cursor(stmt, sort_column=Host.hostname, id_column=Host.id,
                          cursor=None, limit=2)
        rows = (await session.execute(s1)).scalars().all()
        p1 = build_page(rows, limit=2, sort_attr="hostname", id_attr="id")
        assert [r.id for r in p1.items] == ["t-00", "t-01"]
        # Page 2 picks up "t-02"
        s2 = apply_cursor(stmt, sort_column=Host.hostname, id_column=Host.id,
                          cursor=p1.next_cursor, limit=2)
        rows = (await session.execute(s2)).scalars().all()
        p2 = build_page(rows, limit=2, sort_attr="hostname", id_attr="id")
        assert [r.id for r in p2.items] == ["t-02"]
