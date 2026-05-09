"""Advisory storage helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.advisory.feeds import FeedAdvisory
from server.app.models import Advisory, AffectedPackage

# Cooperative pause between commit batches so concurrent writers (login,
# heartbeat, sweeper) reliably win the SQLite writer lock. Tuned for dev:
# 50ms gap × ~1k batches ≈ 50s extra wall time; trivial vs. the network pull.
_BATCH_PAUSE_S = 0.05


async def upsert_advisories(
    sm: async_sessionmaker[AsyncSession],
    items: list[FeedAdvisory],
    source: str,
    *,
    batch_size: int = 500,
) -> tuple[int, int]:
    """Upsert advisories and their affected packages.

    Idempotent. Commits every ``batch_size`` advisories so the writer lock is
    released between batches — large feed syncs (e.g. OSV with 100k+ entries)
    won't starve concurrent writers like login or heartbeat handlers.

    Returns (inserted, updated).
    """
    inserted = 0
    updated = 0

    for start in range(0, len(items), batch_size):
        chunk = items[start : start + batch_size]
        async with sm() as session:
            for item in chunk:
                adv = await session.get(Advisory, item.id)

                if adv is None:
                    adv = Advisory(
                        id=item.id,
                        aliases=item.aliases,
                        summary=item.summary,
                        description_md=item.description_md,
                        severity=item.severity,
                        cvss_v3=item.cvss_v3,
                        cvss_v4=item.cvss_v4,
                        published=item.published,
                        modified=item.modified,
                        refs=item.refs,
                        sources=[source],
                    )
                    session.add(adv)
                    inserted += 1
                else:
                    adv.summary = item.summary
                    adv.description_md = item.description_md
                    adv.severity = item.severity
                    adv.cvss_v3 = item.cvss_v3
                    adv.cvss_v4 = item.cvss_v4
                    adv.published = item.published
                    adv.modified = item.modified
                    adv.refs = item.refs
                    adv.aliases = item.aliases
                    if source not in adv.sources:
                        adv.sources.append(source)
                    adv.updated_at = datetime.now(timezone.utc)
                    updated += 1

                stmt = sa.delete(AffectedPackage).where(
                    AffectedPackage.advisory_id == item.id
                )
                await session.execute(stmt)

                for aff in item.affected:
                    pkg = AffectedPackage(
                        advisory_id=item.id,
                        ecosystem=aff.ecosystem,
                        package=aff.package,
                        introduced=aff.introduced,
                        fixed=aff.fixed,
                        range_kind=aff.range_kind,
                    )
                    session.add(pkg)

            await session.commit()
        await asyncio.sleep(_BATCH_PAUSE_S)

    return inserted, updated


async def apply_scores(
    sm: async_sessionmaker[AsyncSession],
    scores: dict[str, float | bool],
    *,
    kind: str,
    batch_size: int = 500,
) -> int:
    """Apply scores (EPSS or KEV) to advisories.

    Matches by advisory id AND aliases. Builds an in-memory alias index in
    one pass so a single CVE id can fan out to every distro/GHSA record
    that lists it as an alias (Ubuntu OSV ids, GHSA ids, etc). This lifts
    EPSS/KEV coverage well past the ~1% of records whose primary id is a
    bare ``CVE-*``.

    Commits every ``batch_size`` updates so the writer lock is released
    between batches. Returns count of updated rows.
    """
    if kind not in ("epss", "kev"):
        raise ValueError(f"kind must be 'epss' or 'kev', got {kind!r}")
    if not scores:
        return 0

    # Build alias→[advisory_id...] reverse index in one pass.
    alias_index: dict[str, list[str]] = {}
    async with sm() as session:
        rows = (
            await session.execute(sa.select(Advisory.id, Advisory.aliases))
        ).all()
    for adv_id, aliases in rows:
        alias_index.setdefault(adv_id, []).append(adv_id)
        if isinstance(aliases, list):
            for a in aliases:
                if isinstance(a, str) and a:
                    alias_index.setdefault(a, []).append(adv_id)

    # Resolve incoming score keys → set of advisory ids to update.
    resolved: dict[str, float | bool] = {}
    for key, score in scores.items():
        for adv_id in alias_index.get(key, []):
            resolved[adv_id] = score  # later wins on collision

    if not resolved:
        return 0

    count = 0
    items = list(resolved.items())
    col_name = "epss" if kind == "epss" else "kev"

    for start in range(0, len(items), batch_size):
        chunk = items[start : start + batch_size]
        # Group by score value to issue one bulk UPDATE per distinct value.
        by_val: dict[float | bool, list[str]] = {}
        for adv_id, val in chunk:
            by_val.setdefault(val, []).append(adv_id)
        async with sm() as session:
            for val, ids in by_val.items():
                stmt = (
                    sa.update(Advisory)
                    .where(Advisory.id.in_(ids))
                    .values({col_name: val})
                )
                result = await session.execute(stmt)
                rc = getattr(result, "rowcount", None)
                count += int(rc) if rc is not None else len(ids)
            await session.commit()
        await asyncio.sleep(_BATCH_PAUSE_S)

    return count
