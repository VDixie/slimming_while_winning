"""Generic rule for rhythmic motion: one number per frame swinging up and down.

A *signal* is any function that turns one frame's :class:`BodyFeatures` into a
number, e.g. "left wrist height minus right wrist height" (arm swing) or "how
high the shoulders are in the picture" (body bounce). While running in place
both signals oscillate around their resting value; when standing they don't.
See :mod:`sww.gestures.running` for the signals actually used.

The score
---------
The score is the minimum (fuzzy AND) of two terms:

1. **swing** (look-back ``swing_ms``, ~1 s): the signal must have gone *both*
   above and below its *baseline* within the window. ``swing`` =
   ``min(max(s - b), max(b - s))``, where ``b`` is the median of the signal
   over the last ``baseline_ms`` (~3 s). The median of a symmetric oscillation
   is its centre, and when standing still it is just the resting value, so the
   baseline adapts to stance, posture and camera position. Requiring both sides
   rejects one-off movements: raising one hand, or crouching down and staying.
2. **recent motion** (look-back ``recent_ms``, ~450 ms): peak-to-peak range of
   the signal must still be large. This is what makes the gesture end quickly
   when you stop: the swing term remembers the last second, this one doesn't.
   It must cover at least half of the slowest cycle you want detected, or the
   score dips at every turning point.

Each term is a linear ramp (see :func:`sww.gestures.base.rising`), so the score
is smooth and the state machine's hysteresis works on it.

Optional smoothing: a 3-sample median filter removes single-frame landmark
glitches. Good for slow signals (arm swing, ~1.3 Hz); bad for fast ones
(bounce, ~2.6 Hz is only ~6 samples per cycle at 15 fps), where it clips the
peaks.

Latency: a rhythm can't be recognised from one frame. Expect ~0.4-0.6 s to
start (both sides must be seen) and ~0.5-0.7 s to stop (``recent_ms`` plus the
state machine's off-debounce). Measure with ``sww replay``.

Frames where the signal is undefined (a landmark not visible) are skipped. If
too little of the swing window has a usable signal (``min_coverage``), the
score is 0.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from sww.features import BodyFeatures
from sww.gestures.base import Evaluation, rising
from sww.window import FeatureWindow

Signal = Callable[[BodyFeatures], float | None]
"""One number per frame, or None if it can't be measured in that frame."""


@dataclass(frozen=True, slots=True)
class OscillationParams:
    """Thresholds (in the signal's units) and look-back windows (milliseconds).

    Attributes:
        swing_lo, swing_hi: Ramp for how far the signal must go *each way*
            from its baseline within ``swing_ms``.
        range_lo, range_hi: Ramp for the peak-to-peak range within ``recent_ms``.
        swing_ms: Look-back for the swing term (at least one full cycle).
        recent_ms: Look-back for the recent-motion term (at least half a cycle).
        baseline_ms: Look-back for the resting value (median).
        min_coverage: Fraction of frames in ``swing_ms`` with a usable signal.
        smooth: Apply a 3-sample median filter first.
        pixel_signal: The signal is in pixels; divide the whole window by the
            *median* shoulder width over the window to get shoulder widths.
            Dividing frame by frame instead would turn shoulder-width jitter
            into fake motion, amplified by the signal's size (e.g. how far
            the shoulders are from the top of the image).
    """

    swing_lo: float
    swing_hi: float
    range_lo: float
    range_hi: float
    swing_ms: int = 1000
    recent_ms: int = 450
    baseline_ms: int = 3000
    min_coverage: float = 0.6
    smooth: bool = True
    pixel_signal: bool = False

    def __post_init__(self) -> None:
        if not self.recent_ms <= self.swing_ms <= self.baseline_ms:
            raise ValueError("need recent_ms <= swing_ms <= baseline_ms")


def median3(x: np.ndarray) -> np.ndarray:
    """3-sample running median; the first and last samples are kept as they are."""
    if len(x) < 3:
        return x.copy()
    out = x.copy()
    out[1:-1] = np.median(np.stack([x[:-2], x[1:-1], x[2:]]), axis=0)
    return out


def oscillation(window: FeatureWindow, signal: Signal, params: OscillationParams) -> Evaluation:
    """Score how strongly ``signal`` is oscillating at the newest frame of ``window``.

    Returns ``score=None`` when no person is tracked in the newest frame.
    Details: ``signal`` (current value minus baseline), ``swing``, ``range``,
    ``coverage``, ``score``.
    """
    p = params
    latest = window.latest
    if latest is None:
        return Evaluation(score=None)
    if signal(latest) is None:
        return Evaluation(score=0.0, details={"visible": 0.0})

    now = window.latest_ms
    assert now is not None  # latest isn't None, so the window isn't empty
    times: list[int] = []
    values: list[float] = []
    widths: list[float] = []
    swing_total = swing_valid = 0
    for ts, f in window.since(p.baseline_ms):
        in_swing = ts >= now - p.swing_ms
        swing_total += in_swing
        value = signal(f) if f is not None else None
        if value is None:
            continue
        swing_valid += in_swing
        times.append(ts)
        values.append(value)
        widths.append(f.shoulder_width_px)

    coverage = swing_valid / swing_total if swing_total else 0.0
    details = {"coverage": coverage}
    if coverage < p.min_coverage or swing_valid < 3:
        details["score"] = 0.0
        return Evaluation(score=0.0, details=details)

    t = np.asarray(times)
    s = np.asarray(values, dtype=np.float64)
    if p.pixel_signal:
        s = s / float(np.median(widths))
    if p.smooth:
        s = median3(s)
    baseline = float(np.median(s))
    swing_seg = s[t >= now - p.swing_ms] - baseline
    recent_seg = s[t >= now - p.recent_ms]

    # How far the signal went each way from the baseline; the smaller one counts.
    swing = min(float(swing_seg.max()), float(-swing_seg.min()))
    recent_range = float(np.ptp(recent_seg)) if len(recent_seg) else 0.0

    score = min(
        rising(swing, p.swing_lo, p.swing_hi),
        rising(recent_range, p.range_lo, p.range_hi),
    )
    details.update(signal=float(s[-1] - baseline), swing=swing, range=recent_range, score=score)
    return Evaluation(score=score, details=details)


class OscillationDetector:
    """A gesture detector that is just one oscillating signal."""

    def __init__(self, name: str, signal: Signal, params: OscillationParams):
        self.name = name
        self.signal = signal
        self.params = params

    def evaluate(self, window: FeatureWindow) -> Evaluation:
        return oscillation(window, self.signal, self.params)
