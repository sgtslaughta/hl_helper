"""Aggregator math tests."""

from __future__ import annotations

from server.app.posture.risk.aggregator import blend, label_for, apply_hysteresis
from server.app.posture.risk.types import SubScore


def _sub(score: float, conf: float = 1.0) -> SubScore:
    return SubScore(score=score, confidence=conf)


def test_label_thresholds():
    assert label_for(0) == "minimal"
    assert label_for(15) == "stable"
    assert label_for(16) == "moderate"
    assert label_for(35) == "moderate"
    assert label_for(36) == "elevated"
    assert label_for(55) == "elevated"
    assert label_for(56) == "high"
    assert label_for(75) == "high"
    assert label_for(76) == "severe"
    assert label_for(100) == "severe"
    assert label_for(None) == "unknown"


def test_blend_single_pillar_weights_propagate():
    risk = blend(
        subs={"vulnerabilities": _sub(40, 1.0)},
        weights={"vulnerabilities": 0.30, "configuration": 0.25},
    )
    # Only one pillar reporting; den = 0.30, score = 40
    assert risk.score == 40
    assert risk.level == "elevated"
    assert abs(risk.confidence - 0.30 / 0.55) < 1e-6


def test_blend_quiet_majority_dampens_one_hot_pillar():
    # 80 in vulns, 5 in others → score weighed down to ~30, NOT 80.
    risk = blend(
        subs={
            "vulnerabilities": _sub(80, 1.0),
            "configuration": _sub(5, 1.0),
            "identity": _sub(5, 1.0),
            "hygiene": _sub(5, 1.0),
        },
        weights={
            "vulnerabilities": 0.30,
            "configuration": 0.25,
            "identity": 0.20,
            "hygiene": 0.15,
        },
    )
    assert risk.score == 30
    assert risk.level == "moderate"
    assert risk.floor_triggered is False


def test_blend_hot_pillar_floor_triggers():
    risk = blend(
        subs={
            "vulnerabilities": _sub(75, 0.9),
            "configuration": _sub(0, 1.0),
            "identity": _sub(0, 1.0),
            "hygiene": _sub(0, 1.0),
        },
        weights={
            "vulnerabilities": 0.30,
            "configuration": 0.25,
            "identity": 0.20,
            "hygiene": 0.15,
        },
    )
    assert risk.score == 50
    assert risk.floor_triggered is True


def test_blend_unknown_when_no_signal():
    risk = blend(
        subs={"vulnerabilities": _sub(0, 0.0)},
        weights={"vulnerabilities": 0.30},
    )
    assert risk.score is None
    assert risk.level == "unknown"


def test_apply_hysteresis_holds_band():
    new_level = apply_hysteresis(
        new_score=36,
        new_level="elevated",
        prev_score=34,
        prev_level="moderate",
    )
    assert new_level == "moderate"


def test_apply_hysteresis_breaks_band():
    new_level = apply_hysteresis(
        new_score=39,
        new_level="elevated",
        prev_score=34,
        prev_level="moderate",
    )
    assert new_level == "elevated"
