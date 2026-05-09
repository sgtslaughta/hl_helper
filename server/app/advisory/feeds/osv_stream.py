"""Stream-parse OSV all.zip with an ecosystem allowlist applied at parse time.

OSV's ``all.zip`` is one-JSON-per-advisory. We iterate ZIP entries lazily,
parse each small record with stdlib ``json``, drop any record whose affected
ecosystems are all outside the allowlist, accumulate up to ``batch_size``
into a buffer, and hand the buffer to ``upsert_advisories`` (which itself
commits in chunks with a small inter-batch breath — see store.py).

Memory bound: O(batch_size advisories + 1 in-flight JSON record). No 566k
list, no 1 GB peak.

The dedicated ``ijson`` dependency is intentionally not used here: each OSV
record is small enough that incremental JSON parsing inside a single file
buys nothing. ijson stays installed for future feeds whose payloads ARE
large arrays in a single file.
"""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.advisory.feeds import FeedAdvisory
from server.app.advisory.feeds.osv import download_zip, parse_osv_record
from server.app.advisory.store import upsert_advisories

log = logging.getLogger(__name__)

OSV_ALL_ZIP_URL = "https://osv-vulnerabilities.storage.googleapis.com/all.zip"


def _record_matches_allowlist(record: dict, allowlist: set[str] | None) -> bool:
    """Return True if any 'affected' entry's ecosystem is in the allowlist.

    A None allowlist disables filtering (sync everything).
    """
    if allowlist is None:
        return True
    for aff in record.get("affected", []):
        eco = aff.get("package", {}).get("ecosystem", "")
        if eco in allowlist:
            return True
    return False


async def osv_sync_stream(
    catalog_sm: async_sessionmaker[AsyncSession],
    *,
    ecosystem_allowlist: list[str] | None = None,
    batch_size: int = 500,
    url: str = OSV_ALL_ZIP_URL,
) -> tuple[int, int, list[str]]:
    """Stream OSV ``all.zip`` into the catalog DB.

    @param catalog_sm           Catalog (advisory) sessionmaker.
    @param ecosystem_allowlist  If given, skip any record whose affected
                                ecosystems are all outside this list. None
                                pulls everything.
    @param batch_size           Advisories per ``upsert_advisories`` call.
    @param url                  Override URL (tests).

    @return ``(inserted, updated, errors)``. ``errors`` is a list of failed
            entry filenames + reasons, capped at 100 to bound memory.
    """
    allow_set = set(ecosystem_allowlist) if ecosystem_allowlist is not None else None
    inserted_total = 0
    updated_total = 0
    errors: list[str] = []
    batch: list[FeedAdvisory] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "all.zip"
        await download_zip(url, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if not info.filename.endswith(".json"):
                    continue
                try:
                    with zf.open(info) as fp:
                        record = json.load(fp)
                except Exception as e:
                    if len(errors) < 100:
                        errors.append(f"{info.filename}: parse error: {e}")
                    continue

                if not _record_matches_allowlist(record, allow_set):
                    continue

                try:
                    adv = parse_osv_record(record)
                except Exception as e:
                    if len(errors) < 100:
                        errors.append(f"{info.filename}: parse error: {e}")
                    continue

                if adv is None:
                    continue

                # Trim affected list to only the allowed ecosystems so we
                # don't store affected_packages we never want to match.
                if allow_set is not None:
                    adv.affected = [a for a in adv.affected if a.ecosystem in allow_set]
                    if not adv.affected:
                        continue

                batch.append(adv)
                if len(batch) >= batch_size:
                    ins, upd = await upsert_advisories(catalog_sm, batch, "osv")
                    inserted_total += ins
                    updated_total += upd
                    batch = []

            if batch:
                ins, upd = await upsert_advisories(catalog_sm, batch, "osv")
                inserted_total += ins
                updated_total += upd

    log.info(
        "osv_stream.done inserted=%s updated=%s errors=%s ecosystems=%s",
        inserted_total,
        updated_total,
        len(errors),
        len(allow_set) if allow_set is not None else "all",
    )
    return inserted_total, updated_total, errors
