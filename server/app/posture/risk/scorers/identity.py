"""Identity & Access pillar scorer.

Inputs: RBAC posture findings (no owner, excessive admins, stale
approvals, lockout). Identity issues compound silently — apply a
baseline floor of 5 if any finding is present.
"""

from __future__ import annotations

from server.app.posture.risk.types import Driver, ScoreContext, SubScore

_SEV_WEIGHT = {"critical": 25.0, "high": 12.0, "medium": 5.0, "low": 1.5, "info": 0.5}

_IDENTITY_RULES = {
    "no_owner_account",
    "excessive_admin_count",
    "stale_pending_approvals",
    "hosts_with_expired_certs",
}

_BASELINE_FLOOR = 5.0


class IdentityScorer:
    name = "identity"
    label = "Identity & Access"
    description = (
        "RBAC posture across the deployment (owner accounts, admin "
        "count, stale approvals, expired host certs). Org-wide signal — "
        "applies equally to every host."
    )
    weight_default = 0.20
    enabled_by_default = True

    async def score(self, ctx: ScoreContext) -> SubScore:
        total = 0.0
        per_rule: dict[str, float] = {}
        for f in ctx.findings:
            rule = getattr(f, "rule", "")
            if rule not in _IDENTITY_RULES:
                continue
            sev = (getattr(f, "severity", "") or "low").lower()
            w = _SEV_WEIGHT.get(sev, 0.0)
            total += w
            per_rule[rule] = per_rule.get(rule, 0.0) + w

        if total > 0:
            total = max(_BASELINE_FLOOR, total)
        score = min(100.0, total)

        drivers = [
            Driver(label=r, contrib=round(v, 2))
            for r, v in sorted(per_rule.items(), key=lambda x: -x[1])[:3]
        ]

        return SubScore(
            score=round(score, 1),
            confidence=1.0,
            drivers=drivers,
            coverage_notes=[],
        )
