"""Confidence-weighted aggregator + hysteresis helpers.

See docs/superpowers/specs/2026-05-09-posture-risk-aggregator-design.md
section 'Aggregation' for math derivation.
"""

from __future__ import annotations

from server.app.posture.risk.types import Risk, SubScore

# Score → level thresholds (upper bound inclusive). Keep in sync with the spec table.
_THRESHOLDS = [
    (0, "minimal"),
    (15, "stable"),
    (35, "moderate"),
    (55, "elevated"),
    (75, "high"),
    (100, "severe"),
]

# Hysteresis: how many points past a level boundary the new score must
# travel before the new label sticks.
HYSTERESIS_BAND = 3

# Hot-pillar floor: any pillar with score >= this AND confidence >= conf
# threshold pulls overall score up to FLOOR_LIFT.
HOT_PILLAR_SCORE = 70
HOT_PILLAR_CONF = 0.7
FLOOR_LIFT = 50

# Below this aggregate confidence we cannot produce a meaningful score.
UNKNOWN_CONF_THRESHOLD = 0.10


def label_for(score: int | float | None) -> str:
    if score is None:
        return "unknown"
    s = max(0, min(100, score))
    for upper, label in _THRESHOLDS:
        if s <= upper:
            return label
    return "severe"


def blend(
    subs: dict[str, SubScore],
    weights: dict[str, float],
) -> Risk:
    """Confidence-weighted average across enabled pillars.

    Disabled pillars are absent from `subs` (their weight is excluded
    from the denominator). Hot-pillar floor lifts a quiet majority's
    blend when one pillar has confirmed high risk and others are silent.
    """
    den = 0.0
    num = 0.0
    floor = False
    hot_pillar_name = None
    other_contribution = 0.0

    for name, sub in subs.items():
        w = weights.get(name, 0.0)
        if w <= 0:
            continue
        den += w * sub.confidence
        num += sub.score * w * sub.confidence

        if sub.score >= HOT_PILLAR_SCORE and sub.confidence >= HOT_PILLAR_CONF:
            hot_pillar_name = name

    # Check if floor should trigger: hot pillar exists AND other pillars' contribution is very low
    if hot_pillar_name:
        for name, sub in subs.items():
            if name != hot_pillar_name:
                w = weights.get(name, 0.0)
                if w > 0:
                    other_contribution += sub.score * w

        if other_contribution < 2.5:
            floor = True

    if den < UNKNOWN_CONF_THRESHOLD:
        return Risk(score=None, level="unknown", confidence=den, floor_triggered=False)

    blended = num / den
    if floor:
        blended = max(blended, FLOOR_LIFT)
    score = int(round(min(100.0, max(0.0, blended))))

    total_w = sum(w for w in weights.values() if w > 0) or 1.0
    overall_conf = min(1.0, den / total_w)

    return Risk(
        score=score,
        level=label_for(score),
        confidence=overall_conf,
        floor_triggered=floor,
    )


def _level_index(level: str) -> int:
    order = ["minimal", "stable", "moderate", "elevated", "high", "severe"]
    try:
        return order.index(level)
    except ValueError:
        return -1


def apply_hysteresis(
    *,
    new_score: int,
    new_level: str,
    prev_score: int | None,
    prev_level: str | None,
) -> str:
    """Return the level we should display, applying a 3-point band.

    If `new_level` differs from `prev_level`, only honor the change when
    `new_score` has crossed the relevant boundary by at least
    HYSTERESIS_BAND points. Otherwise stick with `prev_level`.
    """
    if prev_level is None or prev_score is None:
        return new_level
    if new_level == prev_level:
        return new_level
    if _level_index(new_level) > _level_index(prev_level):
        # promotion — boundary is the upper edge of prev's band
        for upper, label in _THRESHOLDS:
            if label == prev_level:
                if new_score >= upper + HYSTERESIS_BAND:
                    return new_level
                return prev_level
        return new_level
    else:
        # demotion — boundary is the lower edge of prev's band
        for i, (upper, label) in enumerate(_THRESHOLDS):
            if label == prev_level:
                lower = _THRESHOLDS[i - 1][0] if i > 0 else 0
                if new_score <= lower - HYSTERESIS_BAND:
                    return new_level
                return prev_level
        return new_level
