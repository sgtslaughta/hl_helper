"""Separate declarative base for the advisory catalog tables.

Advisory data lives in its own SQLAlchemy ``MetaData`` so that on SQLite we
can route it to a dedicated database file (``advisory.db``), keeping bulk
feed writes off the fleet writer queue. On Postgres both metadatas attach to
the same engine and both bases live in the same database.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class CatalogBase(DeclarativeBase):
    """Declarative base for advisory catalog tables (Advisory, AffectedPackage, FeedStatus)."""
    pass
