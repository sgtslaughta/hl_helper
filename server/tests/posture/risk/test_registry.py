from __future__ import annotations

import pytest

from server.app.posture.risk.registry import ScorerRegistry
from server.app.posture.risk.scorers.vulnerabilities import VulnerabilitiesScorer


def test_registry_default_weights():
    reg = ScorerRegistry()
    reg.register(VulnerabilitiesScorer())
    cfg = reg.config()
    assert cfg.weights["vulnerabilities"] == 0.30
    assert cfg.scorers[0]["enabled"] is True


def test_registry_apply_override():
    reg = ScorerRegistry()
    reg.register(VulnerabilitiesScorer())
    reg.apply_overrides(
        weights={"vulnerabilities": 0.50},
        enabled={"vulnerabilities": True},
    )
    cfg = reg.config()
    assert cfg.weights["vulnerabilities"] == 0.50


def test_registry_disable_excludes_from_active():
    reg = ScorerRegistry()
    reg.register(VulnerabilitiesScorer())
    reg.apply_overrides(weights={}, enabled={"vulnerabilities": False})
    assert list(reg.active_scorers()) == []


def test_registry_rejects_unknown_scorer_in_override():
    reg = ScorerRegistry()
    reg.register(VulnerabilitiesScorer())
    with pytest.raises(ValueError):
        reg.apply_overrides(weights={"nope": 0.1}, enabled={})


def test_registry_rejects_out_of_range_weight():
    reg = ScorerRegistry()
    reg.register(VulnerabilitiesScorer())
    with pytest.raises(ValueError):
        reg.apply_overrides(weights={"vulnerabilities": 1.5}, enabled={})
