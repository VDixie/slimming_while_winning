"""Rule-based static gesture: one hand resting on top of the head.

Geometry (all in the body frame: origin between the shoulders, y up, unit =
shoulder width; see :mod:`sww.features`). Rough adult proportions: the nose sits
~0.6-0.7 shoulder widths above the shoulder line and the top of the head
another ~0.3-0.4 above the nose.

For each hand we take a "hand point" = mean of the pose model's wrist, index
knuckle and pinky knuckle landmarks, then require all of:

1. **height**: hand point is above the nose (``dy`` = hand y - nose y).
   Ramp up between ``height_lo`` and ``height_hi``.
2. **not overhead**: hand is not far above the head (that's "arms raised").
   Ramp down between ``overhead_lo`` and ``overhead_hi``.
3. **centred**: hand is horizontally near the head (``|dx|``).
   Ramp down between ``centre_lo`` and ``centre_hi``.
4. **bent elbow**: angle shoulder-elbow-wrist is small. A hand on the head
   needs a sharply bent arm; a raised straight arm is ~150-180 degrees.

The hand's score is the *minimum* of these four (all must hold, like a fuzzy
AND). The gesture score is the max over both hands ("either hand").

The default numbers are educated guesses. Run ``sww run --debug`` to see the
live values next to the preview and adjust them for your body and camera.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sww.features import DEFAULT_MIN_VISIBILITY, BodyFeatures, joint_angle_deg
from sww.gestures.base import Evaluation, falling, rising
from sww.landmarks import Pose


@dataclass(frozen=True, slots=True)
class HandOnHeadParams:
    """Thresholds, in shoulder widths (distances) or degrees (angles)."""

    height_lo: float = 0.05
    height_hi: float = 0.25
    overhead_lo: float = 0.9
    overhead_hi: float = 1.3
    centre_lo: float = 0.45
    centre_hi: float = 0.75
    elbow_lo_deg: float = 100.0
    elbow_hi_deg: float = 135.0
    min_visibility: float = DEFAULT_MIN_VISIBILITY


_SIDES: dict[str, tuple[Pose, Pose, Pose, Pose, Pose]] = {
    # side: (shoulder, elbow, wrist, index, pinky)
    "left": (
        Pose.LEFT_SHOULDER,
        Pose.LEFT_ELBOW,
        Pose.LEFT_WRIST,
        Pose.LEFT_INDEX,
        Pose.LEFT_PINKY,
    ),
    "right": (
        Pose.RIGHT_SHOULDER,
        Pose.RIGHT_ELBOW,
        Pose.RIGHT_WRIST,
        Pose.RIGHT_INDEX,
        Pose.RIGHT_PINKY,
    ),
}


class HandOnHead:
    """Detect a hand placed on top of the head (either hand)."""

    def __init__(self, name: str = "hand_on_head", params: HandOnHeadParams | None = None):
        self.name = name
        self.params = params or HandOnHeadParams()

    def _head_point(self, f: BodyFeatures) -> np.ndarray | None:
        """Nose if visible, else the midpoint of whichever ears are visible."""
        p = self.params
        if f.visible(Pose.NOSE, p.min_visibility):
            return f.point(Pose.NOSE)
        ears = [
            f.point(e) for e in (Pose.LEFT_EAR, Pose.RIGHT_EAR) if f.visible(e, p.min_visibility)
        ]
        if ears:
            return np.mean(ears, axis=0)
        return None

    def _hand_score(
        self, f: BodyFeatures, head: np.ndarray, side: str, details: dict[str, float]
    ) -> float:
        p = self.params
        shoulder, elbow, wrist, index, pinky = _SIDES[side]
        hand_ids = [i for i in (wrist, index, pinky) if f.visible(i, p.min_visibility)]
        if not hand_ids or not f.visible(elbow, p.min_visibility):
            details[f"{side}.score"] = 0.0
            return 0.0

        hand = np.mean([f.point(i) for i in hand_ids], axis=0)
        dy = float(hand[1] - head[1])  # + means hand is above the nose
        dx = abs(float(hand[0] - head[0]))
        elbow_deg = joint_angle_deg(f.point(shoulder), f.point(elbow), hand)

        terms = (
            rising(dy, p.height_lo, p.height_hi),
            falling(dy, p.overhead_lo, p.overhead_hi),
            falling(dx, p.centre_lo, p.centre_hi),
            falling(elbow_deg, p.elbow_lo_deg, p.elbow_hi_deg),
        )
        score = min(terms)
        details[f"{side}.dy"] = dy
        details[f"{side}.dx"] = dx
        details[f"{side}.elbow_deg"] = elbow_deg
        details[f"{side}.score"] = score
        return score

    def evaluate(self, features: BodyFeatures | None) -> Evaluation:
        """Score 0..1; None when no person is tracked."""
        if features is None:
            return Evaluation(score=None)
        head = self._head_point(features)
        if head is None:
            return Evaluation(score=0.0, details={"head_visible": 0.0})
        details: dict[str, float] = {}
        score = max(self._hand_score(features, head, side, details) for side in _SIDES)
        return Evaluation(score=score, details=details)
