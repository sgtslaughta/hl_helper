"""Advisory catalog models.

These tables live in the catalog metadata (``CatalogBase``) so the engine
factory can route them to a dedicated database file on SQLite while still
sharing a single connection on Postgres.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models._catalog_base import CatalogBase


class Advisory(CatalogBase):
    """A single security advisory (CVE, GHSA, etc.)."""

    __tablename__ = "advisories"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(String(512))
    description_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(16), default="unknown", server_default="unknown"
    )
    cvss_v3: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cvss_v4: Mapped[str | None] = mapped_column(String(64), nullable=True)
    epss: Mapped[float | None] = mapped_column(Float, nullable=True)
    kev: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false())
    published: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    modified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_advisories_severity", "severity"),
        Index("ix_advisories_epss", "epss"),
        Index("ix_advisories_kev", "kev"),
        Index("ix_advisories_modified", "modified"),
    )


class AffectedPackage(CatalogBase):
    """A package range affected by a single advisory."""

    __tablename__ = "affected_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    advisory_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("advisories.id", ondelete="CASCADE"), index=True
    )
    ecosystem: Mapped[str] = mapped_column(String(64), index=True)
    package: Mapped[str] = mapped_column(String(256), index=True)
    introduced: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fixed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    range_kind: Mapped[str] = mapped_column(
        String(16), default="SEMVER", server_default="SEMVER"
    )

    __table_args__ = (
        Index("ix_affected_packages_ecosystem_package", "ecosystem", "package"),
    )


class FeedStatus(CatalogBase):
    """Per-feed sync status. Survives restarts; consumed by /v1/advisories/feeds/status."""

    __tablename__ = "feed_status"

    feed_name: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    next_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
