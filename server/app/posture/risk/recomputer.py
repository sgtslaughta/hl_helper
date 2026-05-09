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
    ):
        self._sm = sessionmaker
        self._reg = registry
        self._bus = bus
        self._audit = audit
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_run: dict[str, float] = {}
        self._writes = 0

    def _lock(self, host_id: str) -> asyncio.Lock:
        return self._locks.setdefault(host_id, asyncio.Lock())

    async def request(self, host_id: str, *, trigger_reason: str) -> None:
        loop = asyncio.get_event_loop()
        last = self._last_run.get(host_id, 0)
        if loop.time() - last < self.DEBOUNCE_S:
            return
        await self.recompute(host_id, trigger_reason=trigger_reason)

    async def recompute(self, host_id: str, *, trigger_reason: str) -> None:
        async with self._lock(host_id):
            try:
                await self._recompute_locked(host_id, trigger_reason=trigger_reason)
            finally:
                self._last_run[host_id] = asyncio.get_event_loop().time()

    async def _recompute_locked(self, host_id: str, *, trigger_reason: str) -> None:
        from server.app.models.host import Host
        from server.app.models.host_advisory import HostAdvisory
        from server.app.models.host_risk import HostRisk

        async with self._sm() as session:
            host = await session.get(Host, host_id)
            if host is None:
                return
            advs = list(
                (
                    await session.execute(
                        select(HostAdvisory).where(HostAdvisory.host_id == host_id)
                    )
                ).scalars().all()
            )
            findings = await self._fetch_findings(session, host_id)

        ctx = ScoreContext(
            host=host,
            advisories=advs,
            findings=findings,
            survey=getattr(host, "survey", None),
            metrics=getattr(host, "metrics", None),
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
                and prev.level is not None
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
                await self._emit_transition(host, prev.level, level, risk.score)
            await self._emit_audit(host_id, risk, prev, trigger_reason, h)

    async def _fetch_findings(self, session, host_id: str) -> list[Any]:
        try:
            from server.app.posture.model import PostureFindingRow

            rows = (
                await session.execute(
                    select(PostureFindingRow).where(
                        PostureFindingRow.subject_id == host_id
                    )
                )
            ).scalars().all()
            return list(rows)
        except Exception:
            return []

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
