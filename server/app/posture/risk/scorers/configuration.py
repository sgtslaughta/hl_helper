"""Configuration pillar scorer.

Inputs: posture findings whose rule belongs to the config rule set
(sshd, kernel, fs perms, release signing, update engine, transport).
Each finding contributes a fixed weight by severity. Per-rule cap
prevents one noisy rule from dominating.
"""

from __future__ import annotations

from typing import Any

from server.app.posture.risk.types import Driver, ScoreContext, SubScore

_SEV_WEIGHT = {"critical": 25.0, "high": 12.0, "medium": 5.0, "low": 1.5}

_CONFIG_RULES = {
    "sshd_passwordauth",
    "sshd_permitrootlogin",
    "kernel_aslr",
    "fs_shadow_perms",
    "release_signing_not_configured",
    "update_engine_not_configured",
}

_PER_RULE_CAP = 35.0


class ConfigurationScorer:
    name = "configuration"
    label = "Configuration"
    description = (
        "Misconfiguration findings (sshd hardening, kernel ASLR, FS "
        "permissions, secrets handling, release signing, update engine "
        "presence). Does NOT see runtime exploit-mitigation telemetry."
    )
    weight_default = 0.25
    enabled_by_default = True

    async def score(self, ctx: ScoreContext) -> SubScore:
        per_rule: dict[str, float] = {}
        per_rule_findings: dict[str, list[Any]] = {}

        for f in ctx.findings:
            rule = getattr(f, "rule", "")
            if rule not in _CONFIG_RULES:
                continue
            sev = (getattr(f, "severity", "") or "low").lower()
            w = _SEV_WEIGHT.get(sev, 0.0)
            per_rule[rule] = min(_PER_RULE_CAP, per_rule.get(rule, 0.0) + w)
            per_rule_findings.setdefault(rule, []).append(f)

        score = min(100.0, sum(per_rule.values()))
        drivers = [
            Driver(label=f"{r} ({len(per_rule_findings[r])})", contrib=round(v, 2))
            for r, v in sorted(per_rule.items(), key=lambda x: -x[1])[:3]
        ]

        coverage = 0.4
        if isinstance(ctx.survey, dict):
            # Survey keys come from the agent's host_survey envelope —
            # `sshd`, `sysctl`, `fs_perms` (see server/app/posture/
            # findings_misconfig.py for the canonical shape).
            seen = sum(
                1
                for key in ("sshd", "sysctl", "fs_perms")
                if key in ctx.survey
            )
            coverage = max(0.4, min(1.0, 0.4 + 0.2 * seen))
        notes = []
        if ctx.survey is None:
            notes.append("no survey data — config posture cannot be assessed")
            coverage = 0.3

        return SubScore(
            score=round(score, 1),
            confidence=round(coverage, 3),
            drivers=drivers,
            coverage_notes=notes,
        )
