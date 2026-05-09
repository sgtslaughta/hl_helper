"""RiskRecomputer — coordinates scorer execution + persistence.

Per-host asyncio.Lock + 30s debounce + inputs_hash short-circuit. On
level transition: emits ticker event + audit entry.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.posture.risk.aggregator import apply_hysteresis, blend
from server.app.posture.risk.registry import ScorerRegistry
from server.app.posture.risk.types import ScoreContext, SubScore

log = logging.getLogger(__name__)


class RiskRecomputer:
    DEBOUNCE_S = 30.0
    SCORER_TIMEOUT_S = 0.25

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        registry: ScorerRegistry,
        *,
        bus: Any,
        audit: Any,
        catalog_sessionmaker: async_sessionmaker | None = None,
    ):
        self._sm = sessionmaker
        self._catalog_sm = catalog_sessionmaker
        self._reg = registry
        self._bus = bus
        self._audit = audit
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_run: dict[str, float] = {}
        self._writes = 0

    def _lock(self, host_id: str) -> asyncio.Lock:
        return self._locks.setdefault(host_id, asyncio.Lock())

    async def request(self, host_id: str, *, trigger_reason: str) -> None:
        """Debounced recompute — checks last-run time inside the per-host lock
        so concurrent callers can't both slip past the window."""
        await self.recompute(
            host_id, trigger_reason=trigger_reason, debounced=True
        )

    async def recompute(
        self,
        host_id: str,
        *,
        trigger_reason: str,
        debounced: bool = False,
    ) -> None:
        async with self._lock(host_id):
            loop = asyncio.get_event_loop()
            if (
                debounced
                and loop.time() - self._last_run.get(host_id, 0) < self.DEBOUNCE_S
            ):
                return
            try:
                await self._recompute_locked(host_id, trigger_reason=trigger_reason)
            finally:
                self._last_run[host_id] = loop.time()

    async def _recompute_locked(self, host_id: str, *, trigger_reason: str) -> None:
        from server.app.models.host import Host
        from server.app.models.host_advisory import HostAdvisory
        from server.app.models.host_risk import HostRisk

        async with self._sm() as session:
            host = await session.get(Host, host_id)
            if host is None:
                return
            ha_rows = list(
                (
                    await session.execute(
                        select(HostAdvisory).where(HostAdvisory.host_id == host_id)
                    )
                ).scalars().all()
            )
            findings = await self._fetch_findings(session, host_id)

        # Enrich host_advisories with catalog-side fields (severity/kev/epss).
        # HostAdvisory only carries the advisory_id pointer; severity etc.
        # live on the Advisory table in the catalog DB. Without this join the
        # vulnerabilities scorer sees `severity=""` → bucketed as unknown →
        # zero contribution → 0/100 score regardless of actual fleet state.
        advs = await self._enrich_advisories(ha_rows)

        # Hygiene scorer reads `metrics["latest_agent_release"]` to compute
        # version drift. host.metrics holds heartbeat telemetry (cpu/mem/etc),
        # not release info — merge in the looked-up version here.
        host_metrics = dict(getattr(host, "metrics", None) or {})
        latest_release = await self._latest_agent_release(host)
        if latest_release is not None:
            host_metrics["latest_agent_release"] = latest_release

        # Vulnerabilities scorer's confidence reads `survey["packages"]` as
        # an inventory-presence flag. The agent's host_survey doesn't carry
        # packages — they live in host_packages. Stamp a count into a copy
        # of the survey dict so the scorer sees inventory coverage.
        host_survey = dict(getattr(host, "survey", None) or {})
        pkg_count = await self._host_package_count(host_id)
        if pkg_count > 0:
            host_survey["packages"] = pkg_count

        ctx = ScoreContext(
            host=host,
            advisories=advs,
            findings=findings,
            survey=host_survey or None,
            metrics=host_metrics or None,
            now=datetime.now(timezone.utc),
        )

        subs: dict[str, SubScore] = {}
        for s in self._reg.active_scorers():
            try:
                sub = await asyncio.wait_for(s.score(ctx), timeout=self.SCORER_TIMEOUT_S)
            except (asyncio.TimeoutError, Exception) as exc:
                log.warning("risk.scorer_failed", extra={"scorer": s.name, "err": str(exc)})
                sub = SubScore(score=0, confidence=0, coverage_notes=[f"scorer error: {exc}"])
            subs[s.name] = sub

        cfg = self._reg.config()
        weights = cfg.weights
        risk = blend(subs, weights)

        h = self._hash_inputs(host, advs, findings, weights)
        async with self._sm() as session:
            prev = await session.get(HostRisk, host_id)
            if prev is not None and prev.inputs_hash == h:
                return

            level = risk.level
            if (
                prev is not None
                and risk.score is not None
                and prev.score is not None
            ):
                level = apply_hysteresis(
                    new_score=risk.score,
                    new_level=risk.level,
                    prev_score=prev.score,
                    prev_level=prev.level,
                )

            new_row = HostRisk(
                host_id=host_id,
                score=risk.score,
                level=level,
                confidence=risk.confidence,
                pillars={
                    name: {
                        "score": sub.score,
                        "confidence": sub.confidence,
                        "weight": weights.get(name, 0.0),
                        "drivers": [d.__dict__ for d in sub.drivers],
                        "coverage_notes": sub.coverage_notes,
                    }
                    for name, sub in subs.items()
                },
                computed_at=ctx.now,
                inputs_hash=h,
                floor_triggered=risk.floor_triggered,
                score_prev=(prev.score if prev else None),
                level_prev=(prev.level if prev else None),
            )
            await session.merge(new_row)
            await session.commit()
            self._writes += 1

            if prev is not None and prev.level != level:
                # `prev.level` is non-nullable per the model declaration.
                assert isinstance(prev.level, str)
                await self._emit_transition(host, prev.level, level, risk.score)
            await self._emit_audit(host_id, risk, prev, trigger_reason, h)

    async def _enrich_advisories(self, ha_rows: list[Any]) -> list[Any]:
        """Attach severity/kev/epss/package fields from the catalog Advisory
        table onto each HostAdvisory row. The Vulnerabilities scorer reads
        these via getattr; missing means base=0 → silent score collapse.

        Falls back gracefully when the catalog sessionmaker is unavailable
        (e.g. tests without split-DB) — host_advisory rows pass through
        unchanged and the scorer's existing getattr defaults handle them.
        """
        if not ha_rows or self._catalog_sm is None:
            return list(ha_rows)
        from server.app.models.advisory import Advisory

        ids = list({getattr(r, "advisory_id", "") for r in ha_rows if getattr(r, "advisory_id", "")})
        by_id: dict[str, Any] = {}
        try:
            async with self._catalog_sm() as cat:
                rows = (
                    await cat.execute(select(Advisory).where(Advisory.id.in_(ids)))
                ).scalars().all()
                for a in rows:
                    by_id[a.id] = a
        except Exception:
            log.exception("risk.advisory_enrich_failed")
            return list(ha_rows)

        enriched: list[Any] = []
        for ha in ha_rows:
            adv = by_id.get(getattr(ha, "advisory_id", ""))
            if adv is None:
                enriched.append(ha)
                continue
            # Decorate the HostAdvisory row in-place with the catalog fields
            # the scorer expects. Safe because the row is detached at this point.
            try:
                setattr(ha, "severity", getattr(adv, "severity", "unknown") or "unknown")
                setattr(ha, "kev", bool(getattr(adv, "kev", False)))
                epss_val = getattr(adv, "epss", 0.0)
                setattr(ha, "epss", float(epss_val) if epss_val is not None else 0.0)
            except Exception:
                pass
            enriched.append(ha)
        return enriched

    async def _fetch_findings(self, session, host_id: str) -> list[Any]:
        """Pull both host-scoped findings (sshd, kernel, fs perms, …) AND
        global/fleet-scoped findings (RBAC posture: no_owner_account,
        excessive_admin_count, stale_pending_approvals, …).

        Identity scorer specifically expects globals — without them every
        host scores 0 on Identity even when the org has critical RBAC gaps.
        """
        try:
            from server.app.posture.model import PostureFindingRow
            from sqlalchemy import or_

            rows = (
                await session.execute(
                    select(PostureFindingRow).where(
                        or_(
                            PostureFindingRow.subject_id == host_id,
                            PostureFindingRow.subject_kind == "global",
                            PostureFindingRow.subject_kind == "fleet",
                        )
                    )
                )
            ).scalars().all()
            return list(rows)
        except Exception as exc:
            log.warning(
                "risk.fetch_findings_failed",
                extra={"host_id": host_id, "err": str(exc)},
            )
            return []

    async def _host_package_count(self, host_id: str) -> int:
        """Count host_packages rows for the host. Used as the inventory-
        presence proxy for the Vulnerabilities scorer's confidence."""
        try:
            from sqlalchemy import func

            from server.app.models.host_package import HostPackage

            async with self._sm() as session:
                row = (
                    await session.execute(
                        select(func.count(HostPackage.id)).where(
                            HostPackage.host_id == host_id
                        )
                    )
                ).scalar_one()
                return int(row or 0)
        except Exception:
            log.exception("risk.host_package_count_failed")
            return 0

    async def _latest_agent_release(self, host: Any) -> str | None:
        """Look up the newest non-yanked AgentRelease matching host.os + arch.
        Used by the Hygiene scorer to surface drift between the agent
        running on the host and the latest one published."""
        try:
            from server.app.models.agent_release import AgentRelease, ReleaseStatus

            os = getattr(host, "os", None) or (
                (getattr(host, "labels", None) or {}).get("os")
            )
            arch = getattr(host, "arch", None) or (
                (getattr(host, "labels", None) or {}).get("arch")
            )
            if not os or not arch:
                return None
            async with self._sm() as session:
                stmt = (
                    select(AgentRelease.version)
                    .where(
                        AgentRelease.os == os,
                        AgentRelease.arch == arch,
                        AgentRelease.status != ReleaseStatus.YANKED,
                    )
                    .order_by(AgentRelease.uploaded_at.desc())
                    .limit(1)
                )
                row = (await session.execute(stmt)).scalar_one_or_none()
                return row
        except Exception:
            log.exception("risk.latest_release_lookup_failed")
            return None

    def _hash_inputs(self, host, advs, findings, weights) -> str:
        payload = {
            "host_id": getattr(host, "id", None),
            "agent_version": getattr(host, "agent_version", None),
            "agent_update_status": str(getattr(host, "agent_update_status", "")),
            "cert_expires_at": getattr(host, "cert_expires_at", None)
            and host.cert_expires_at.isoformat(),
            "last_seen_at": getattr(host, "last_seen_at", None)
            and host.last_seen_at.isoformat(),
            "advisories": sorted(
                (
                    getattr(a, "advisory_id", ""),
                    getattr(a, "severity", ""),
                    getattr(a, "kev", False),
                    getattr(a, "epss", 0.0),
                    getattr(a, "status", ""),
                )
                for a in advs
            ),
            "findings": sorted(
                (getattr(f, "rule", ""), getattr(f, "severity", ""))
                for f in findings
            ),
            "weights": sorted(weights.items()),
        }
        s = json.dumps(payload, default=str, sort_keys=True)
        return hashlib.sha256(s.encode()).hexdigest()

    async def _emit_transition(
        self, host, prev_level: str, new_level: str, score: int | None
    ) -> None:
        try:
            from server.app.events.ticker import publish_ticker

            order = ["minimal", "stable", "moderate", "elevated", "high", "severe", "unknown"]
            improving = order.index(new_level) < order.index(prev_level)
            severity = "ok" if improving else ("error" if new_level == "severe" else "warn")
            await publish_ticker(
                self._bus,
                type="posture",
                severity=severity,
                text=f"{getattr(host, 'hostname', host.id)} risk: {prev_level} → {new_level} ({score})",
                link=f"/hosts/{host.id}/risk",
                meta={
                    "host_id": host.id,
                    "prev_level": prev_level,
                    "level": new_level,
                    "score": score,
                },
            )
        except Exception:
            log.exception("risk.ticker_emit_failed")

    async def _emit_audit(self, host_id, risk, prev, trigger_reason, inputs_hash) -> None:
        try:
            async with self._sm() as session:
                await self._audit.append(
                    session,
                    actor="system",
                    action="risk.recomputed",
                    subject=host_id,
                    payload={
                        "score": risk.score,
                        "level": risk.level,
                        "score_prev": (prev.score if prev else None),
                        "level_prev": (prev.level if prev else None),
                        "inputs_hash": inputs_hash,
                        "floor_triggered": risk.floor_triggered,
                        "trigger_reason": trigger_reason,
                    },
                )
                await session.commit()
        except Exception:
            log.exception("risk.audit_emit_failed")
