"""Catalog engine factory.

The advisory catalog ships in its own SQLAlchemy ``MetaData`` so that on
SQLite we can route it to a separate database file (``advisory.db``) — that
keeps multi-MB feed-sync transactions off the fleet writer queue. On
Postgres, both the fleet ``Base`` and the catalog ``CatalogBase`` attach to
the same engine and live in the same database; no SQLite split needed there.

This module is the only place that knows how to derive a catalog URL from a
fleet URL. Business logic talks only to ``catalog_sm`` (the catalog
sessionmaker) and never sees the engine.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse, urlunparse

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from server.app.settings.config import FleetSettings

log = structlog.get_logger(__name__)


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


def derive_catalog_url(fleet_url: str, override: str | None) -> str:
    """Return the URL to use for the catalog engine.

    Resolution rules:
      1. If ``override`` is non-empty, return it unchanged.
      2. If fleet URL is SQLite, replace the database filename with
         ``advisory.db`` in the same directory (``fleet.db`` -> ``advisory.db``).
      3. If fleet URL is Postgres (or anything non-SQLite), return the fleet URL
         unchanged so the catalog tables share the same connection.
    """
    if override:
        return override

    if _is_sqlite_url(fleet_url):
        # SQLite async URLs look like sqlite+aiosqlite:////absolute/path/fleet.db
        # urlparse mangles the leading slashes, so split on the scheme manually.
        scheme, sep, rest = fleet_url.partition("://")
        if not sep or not rest or rest.startswith(":memory:") or "memory" in rest:
            return fleet_url  # in-memory or unusual URL — leave alone
        # rest may begin with '/' (relative) or '//absolute' (one extra slash for absolute).
        leading = ""
        path_str = rest
        while path_str.startswith("/"):
            leading += "/"
            path_str = path_str[1:]
        p = Path(path_str)
        new_name = "advisory.db" if p.suffix == ".db" else f"{p.name}.advisory.db"
        new_path = str(p.with_name(new_name))
        return f"{scheme}://{leading}{new_path}"

    return fleet_url


def make_catalog_engine(
    settings: FleetSettings,
    *,
    main_engine: AsyncEngine | None = None,
) -> AsyncEngine:
    """Build the catalog engine.

    On Postgres the fleet engine is reused (caller may pass ``main_engine``);
    on SQLite a separate AsyncEngine is created with WAL + busy_timeout
    matching ``make_engine``.
    """
    catalog_url = derive_catalog_url(settings.db_url, settings.advisory_catalog_database_url)

    if (
        main_engine is not None
        and not _is_sqlite_url(settings.db_url)
        and catalog_url == settings.db_url
    ):
        log.info("catalog_engine.shared_with_main", url=_redact(catalog_url))
        return main_engine

    engine = create_async_engine(catalog_url, echo=False)

    if _is_sqlite_url(catalog_url):
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _conn_record):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            try:
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=30000")
                cur.execute("PRAGMA synchronous=NORMAL")
            finally:
                cur.close()

        log.info("catalog_engine.sqlite", url=_redact(catalog_url))
    else:
        log.info("catalog_engine.dedicated_remote", url=_redact(catalog_url))

    return engine


def _redact(url: str) -> str:
    """Strip credentials from a URL for safe logging."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}", ":***")
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        pass
    return url
