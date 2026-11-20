"""Pure score smoothing and visual classification (B-05).

Scores are relative model support, not calibrated probabilities. Nothing here
touches the network, word grouping or frontend geometry.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..audio_ai_ports import RenderCandidate, ScoreVector
from ..config import Settings

LABELS = ("angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "unknown")
VISIBLE = ("angry", "disgusted", "fearful", "happy", "sad", "surprised")
FAINT_OPACITY = (0.14, 0.30)
STANDARD_OPACITY = (0.35, 0.75)
STANDARD_SUPPORT_CEIL = 1.0


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def smooth(current: ScoreVector, previous: ScoreVector | None, config: Settings) -> ScoreVector:
    """EMA per label: alpha*current + (1-alpha)*previous. Convex, so a
    probability-like pair stays normalized. The first window passes through."""
    if previous is None:
        return {k: float(current[k]) for k in LABELS}
    a = config.emotion_smoothing_alpha
    return {k: a * float(current[k]) + (1 - a) * float(previous[k]) for k in LABELS}


def opacity_for_support(support: float, config: Settings) -> float:
    """Monotonic in support: faint 0.14-0.30 over [faint, visible], standard
    0.35-0.75 over [visible, 1.0]; clamped. Uses support breakpoints even while
    hysteresis keeps a tier alive."""
    lo, vis = config.emotion_faint_support, config.emotion_visible_support
    if support < vis:
        t = _clip((support - lo) / (vis - lo))
        return FAINT_OPACITY[0] + t * (FAINT_OPACITY[1] - FAINT_OPACITY[0])
    t = _clip((support - vis) / (STANDARD_SUPPORT_CEIL - vis))
    return STANDARD_OPACITY[0] + t * (STANDARD_OPACITY[1] - STANDARD_OPACITY[0])


def classify(
    scores: Mapping[str, float], previous_state: RenderCandidate | None, config: Settings
) -> RenderCandidate | None:
    """Return None (suppressed) or a RenderCandidate. See docs/PIPELINE.md."""
    top = max(scores[k] for k in LABELS)
    # neutral/other/unknown leading or tied for the lead suppresses immediately
    if any(scores[k] >= top for k in ("neutral", "other", "unknown")):
        return None
    if scores["neutral"] >= config.emotion_neutral_suppress:
        return None
    ranked = sorted(VISIBLE, key=lambda k: (-scores[k], VISIBLE.index(k)))
    primary = ranked[0]
    p = scores[primary]

    faint_in, std_in = config.emotion_faint_support, config.emotion_visible_support
    h = config.emotion_hysteresis
    std_floor, faint_floor = std_in, faint_in
    if previous_state is not None and previous_state.primary == primary:
        # exit hysteresis: the previous tier survives until support falls h below its entry
        if previous_state.support >= std_in:
            std_floor = std_in - h
        faint_floor = faint_in - h
    if p >= std_floor:
        tier = "standard"
    elif p >= faint_floor:
        tier = "faint"
    else:
        return None

    others = max(v for k, v in scores.items() if k != primary)
    intensity = _clip((p - others + 0.25) / 0.75)

    secondary = None
    weight = None
    top2 = sorted(LABELS, key=lambda k: (-scores[k], LABELS.index(k)))[:2]
    if top2[0] == primary and top2[1] in VISIBLE and p >= std_in:
        s = scores[top2[1]]
        if s >= config.emotion_blend_secondary_min and p - s <= config.emotion_blend_gap_max:
            secondary = top2[1]
            weight = s / (p + s)
    return RenderCandidate(
        primary=primary,  # type: ignore[arg-type]
        secondary=secondary,  # type: ignore[arg-type]
        support=p,
        visual_intensity=intensity,
        opacity=opacity_for_support(p, config),
        blend_weight=weight,
    )


class DefaultScorePolicy:
    """Object form of the ScorePolicy protocol."""

    smooth = staticmethod(smooth)
    classify = staticmethod(classify)
