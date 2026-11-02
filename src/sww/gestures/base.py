"""The one interface every gesture detector implements.

A detector turns body features into a *score* between 0 and 1: how strongly the
gesture is present in this frame. Rule-based detectors compute it from geometry;
trained classifiers (roadmap step 4) will return a class probability. Either
way, the state machine (:mod:`sww.state`) decides when a gesture starts and
ends, using separate enter/exit thresholds (hysteresis) and minimum durations
(debounce). Keeping that logic out of detectors means every detector gets the
same anti-flicker behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sww.features import BodyFeatures


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Result of evaluating one detector on one frame.

    Attributes:
        score: 0..1 strength of the gesture, or None if it can't be judged
            (no person tracked).
        details: Named intermediate values for the live debug overlay and for
            tuning thresholds, e.g. ``{"right.height": 0.31}``.
    """

    score: float | None
    details: dict[str, float] = field(default_factory=dict)


class GestureDetector(Protocol):
    """Anything with a ``name`` and an ``evaluate`` method."""

    name: str

    def evaluate(self, features: BodyFeatures | None) -> Evaluation:
        """Score the gesture for one frame. ``features`` is None when tracking is lost."""
        ...


def rising(x: float, lo: float, hi: float) -> float:
    """Linear ramp: 0 at or below ``lo``, 1 at or above ``hi``.

    Using ramps instead of hard ``x > threshold`` checks gives a smooth score,
    so hysteresis on the score works and small jitter near a threshold doesn't
    flip the result.
    """
    if hi <= lo:
        raise ValueError("hi must be greater than lo")
    return min(1.0, max(0.0, (x - lo) / (hi - lo)))


def falling(x: float, lo: float, hi: float) -> float:
    """Linear ramp: 1 at or below ``lo``, 0 at or above ``hi``."""
    return 1.0 - rising(x, lo, hi)
