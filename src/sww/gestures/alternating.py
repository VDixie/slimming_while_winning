"""Rule-based dynamic gesture: two body points moving up and down in turn.

One detector covers two gestures, depending on which landmark pair it watches:

- **running in place**: left/right knee (:data:`RUNNING_IN_PLACE`)
- **pumping arms** (seated alternative): left/right wrist (:data:`PUMPING_ARMS`)

The signal
----------
For every frame we take ``s = left.y - right.y`` in the body frame (y up, unit
= shoulder width; see :mod:`sww.features`). ``s`` is positive while the left
point is higher than the right one. Because it is a *difference* of two points
on the same body, it doesn't change when the whole body bobs up and down
(which it does when running), only when the two points move relative to each
other. When running in place ``s`` swings back and forth around its standing
value at roughly 1.5-3 Hz (strides per second per leg).

``s`` is first passed through a 3-sample median filter, which removes
single-frame landmark glitches without delaying real motion much (one frame).

The score
---------
The score is the minimum (fuzzy AND) of two terms:

1. **swing** (look-back ``swing_ms``, ~1 s): *both* sides must have risen
   above the standing *baseline* within the window. ``swing`` =
   ``min(max(s - b), max(b - s))``, where ``b`` is the median of ``s`` over the
   last ``baseline_ms`` (~3 s). The median of a symmetric oscillation is its
   centre, and when standing still it is just the standing value, so the
   baseline adapts to stance and camera angle (e.g. one foot slightly
   forward). Requiring both sides rejects a single knee lift or shifting your
   weight onto one leg.
2. **recent motion** (look-back ``recent_ms``, ~350 ms): peak-to-peak range of
   ``s`` must still be large. This is what makes the gesture end quickly when
   you stop: the swing term remembers the last second, this one doesn't.

Each term is a linear ramp (see :func:`sww.gestures.base.rising`), so the score
is smooth and the state machine's hysteresis works on it.

Latency (measure with ``sww replay``)
-------------------------------------
A rhythm can't be recognised from a single frame. The swing term needs one
lift of each leg, so the gesture starts about half to three quarters of a
stride after you start running (~300-500 ms at 2 Hz). It ends when the recent
range has decayed (up to ``recent_ms``) plus the state machine's off-debounce.
Both are slower than the ~100 ms target for static gestures; shortening the
windows makes it faster but more likely to drop out between strides.

Frames where either point isn't visible are skipped. If too little of the
swing window has usable data (``min_coverage``), the score is 0.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sww.features import DEFAULT_MIN_VISIBILITY
from sww.gestures.base import Evaluation, rising
from sww.landmarks import Pose
from sww.window import FeatureWindow


@dataclass(frozen=True, slots=True)
class AlternatingParams:
    """Which landmarks to watch, plus thresholds.

    Distances are in shoulder widths, times in milliseconds.

    Attributes:
        left, right: The landmark pair, e.g. the two knees.
        swing_lo, swing_hi: Ramp for how far *each* side must rise above the
            baseline within ``swing_ms``.
        range_lo, range_hi: Ramp for the peak-to-peak range of ``s`` within
            ``recent_ms``.
        swing_ms: Look-back for the swing term. Must cover at least one full
            stride at the slowest pace you want detected.
        recent_ms: Look-back for the recent-motion term. Must cover at least
            half a stride, or the score dips between steps.
        baseline_ms: Look-back for the standing baseline (median).
        min_coverage: Fraction of frames in ``swing_ms`` where both points
            must be visible.
    """

    left: Pose
    right: Pose
    swing_lo: float
    swing_hi: float
    range_lo: float
    range_hi: float
    swing_ms: int = 1000
    recent_ms: int = 350
    baseline_ms: int = 3000
    min_coverage: float = 0.6
    min_visibility: float = DEFAULT_MIN_VISIBILITY

    def __post_init__(self) -> None:
        if not self.recent_ms <= self.swing_ms <= self.baseline_ms:
            raise ValueError("need recent_ms <= swing_ms <= baseline_ms")


# Knees: thigh ~1.1 shoulder widths long, so lifting it ~20-45 degrees raises the
# knee ~0.2-0.5 SW. Educated guesses: tune with `sww record` + `sww replay`.
RUNNING_IN_PLACE = AlternatingParams(
    left=Pose.LEFT_KNEE,
    right=Pose.RIGHT_KNEE,
    swing_lo=0.10,
    swing_hi=0.25,
    range_lo=0.15,
    range_hi=0.35,
)

# Wrists swing further than knees and jitter more, so the thresholds are higher.
PUMPING_ARMS = AlternatingParams(
    left=Pose.LEFT_WRIST,
    right=Pose.RIGHT_WRIST,
    swing_lo=0.20,
    swing_hi=0.40,
    range_lo=0.30,
    range_hi=0.60,
)


def median3(x: np.ndarray) -> np.ndarray:
    """3-sample running median; the first and last samples are kept as they are."""
    if len(x) < 3:
        return x.copy()
    out = x.copy()
    out[1:-1] = np.median(np.stack([x[:-2], x[1:-1], x[2:]]), axis=0)
    return out


class AlternatingMotion:
    """Detect two landmarks rising and falling in turn (see module docstring)."""

    def __init__(self, name: str, params: AlternatingParams):
        self.name = name
        self.params = params

    def _usable(self, f) -> bool:
        p = self.params
        return f.visible(p.left, p.min_visibility) and f.visible(p.right, p.min_visibility)

    def evaluate(self, window: FeatureWindow) -> Evaluation:
        """Score 0..1 for the newest frame; None when no person is tracked."""
        p = self.params
        latest = window.latest
        if latest is None:
            return Evaluation(score=None)
        if not self._usable(latest):
            return Evaluation(score=0.0, details={"visible": 0.0})

        now = window.latest_ms
        assert now is not None  # latest isn't None, so the window isn't empty
        times: list[int] = []
        values: list[float] = []
        swing_total = swing_valid = 0
        for ts, f in window.since(p.baseline_ms):
            in_swing = ts >= now - p.swing_ms
            swing_total += in_swing
            if f is None or not self._usable(f):
                continue
            swing_valid += in_swing
            times.append(ts)
            values.append(float(f.point(p.left)[1] - f.point(p.right)[1]))

        coverage = swing_valid / swing_total if swing_total else 0.0
        details = {"coverage": coverage}
        if coverage < p.min_coverage or swing_valid < 3:
            details["score"] = 0.0
            return Evaluation(score=0.0, details=details)

        t = np.asarray(times)
        s = median3(np.asarray(values, dtype=np.float64))
        baseline = float(np.median(s))
        swing_seg = s[t >= now - p.swing_ms] - baseline
        recent_seg = s[t >= now - p.recent_ms]

        # How far each side rose above the baseline; the smaller one counts.
        swing = min(float(swing_seg.max()), float(-swing_seg.min()))
        recent_range = float(np.ptp(recent_seg)) if len(recent_seg) else 0.0

        score = min(
            rising(swing, p.swing_lo, p.swing_hi),
            rising(recent_range, p.range_lo, p.range_hi),
        )
        details.update(
            signal=float(s[-1] - baseline),
            swing=swing,
            range=recent_range,
            score=score,
        )
        return Evaluation(score=score, details=details)
