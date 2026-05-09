"""Plugin registry + admin override storage.

Holds the ordered list of registered PostureScorers, their default
weights/enabled-by-default flags, and any admin overrides loaded from
the settings store. Persistence layer is provided by the caller — the
registry itself is in-memory and idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass

from server.app.posture.risk.types import PostureScorer


@dataclass
class RiskConfig:
    weights: dict[str, float]
    scorers: list[dict]


class ScorerRegistry:
    def __init__(self) -> None:
        self._scorers: dict[str, PostureScorer] = {}
        self._weight_overrides: dict[str, float] = {}
        self._enabled_overrides: dict[str, bool] = {}

    def register(self, s: PostureScorer) -> None:
        self._scorers[s.name] = s

    def apply_overrides(
        self,
        *,
        weights: dict[str, float],
        enabled: dict[str, bool],
    ) -> None:
        for name in {*weights, *enabled}:
            if name not in self._scorers:
                raise ValueError(f"unknown scorer: {name}")
        for name, w in weights.items():
            if not (0.0 <= w <= 1.0):
                raise ValueError(f"weight out of range for {name}: {w}")
        self._weight_overrides = dict(weights)
        self._enabled_overrides = dict(enabled)

    def weight(self, name: str) -> float:
        if name in self._weight_overrides:
            return self._weight_overrides[name]
        return self._scorers[name].weight_default

    def is_enabled(self, name: str) -> bool:
        if name in self._enabled_overrides:
            return self._enabled_overrides[name]
        return self._scorers[name].enabled_by_default

    def active_scorers(self):
        for name, s in self._scorers.items():
            if self.is_enabled(name):
                yield s

    def config(self) -> RiskConfig:
        weights = {n: self.weight(n) for n in self._scorers if self.is_enabled(n)}
        scorers = [
            {
                "name": s.name,
                "label": s.label,
                "description": s.description,
                "weight_default": s.weight_default,
                "weight": self.weight(s.name),
                "enabled_by_default": s.enabled_by_default,
                "enabled": self.is_enabled(s.name),
                "plugin": "builtin",
            }
            for s in self._scorers.values()
        ]
        return RiskConfig(weights=weights, scorers=scorers)
