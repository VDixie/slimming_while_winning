"""Running in place, detected from the upper body: arm swing AND body bounce.

The knees are below the camera image at the play position, so running is
recognised from two things the camera does see:

- **arm swing** (:func:`arm_swing`): ``left_wrist.y - right_wrist.y`` in the
  body frame (y up, shoulder widths). Swinging arms alternate, so this swings
  between positive and negative at the stride rate (~1.3 Hz measured). As a
  difference of two points on the body it ignores the whole body moving.
- **body bounce** (:func:`shoulder_height_px`): height of the shoulder midpoint
  in the image. The torso rises and falls once per step, so twice per arm
  cycle (~2.6 Hz measured), pushing *up* from standing height (scored with
  ``sides="up"``). Measured in pixels and converted to shoulder widths
  with the *median* width over the window (see ``OscillationParams.pixel_signal``).

Each signal is scored by :func:`sww.gestures.oscillation.oscillation` (it must
move both ways around its resting value, and still be moving in the last
~450 ms). :class:`RunningInPlace` takes the **minimum** of the two scores
(fuzzy AND), so neither alone is enough:

- arms without bounce: gesturing, talking with your hands, pumping arms seated
- bounce without arms: bobbing to music, shifting weight, a cough or laugh

Thresholds were tuned on real recordings (2026-11-02, 15 fps, running and
standing idle; see DECISIONS.md). Re-tune with ``sww record`` + ``sww replay --csv``.

Seated play: :func:`pumping_arms` is the arm-swing signal on its own
(``sww run --forward arms``).
"""

from __future__ import annotations

from sww.features import DEFAULT_MIN_VISIBILITY, BodyFeatures
from sww.gestures.base import Evaluation
from sww.gestures.oscillation import OscillationDetector, OscillationParams, oscillation
from sww.landmarks import Pose
from sww.window import FeatureWindow


def arm_swing(f: BodyFeatures) -> float | None:
    """Left wrist height minus right wrist height (shoulder widths); None if a wrist is hidden."""
    if not (
        f.visible(Pose.LEFT_WRIST, DEFAULT_MIN_VISIBILITY)
        and f.visible(Pose.RIGHT_WRIST, DEFAULT_MIN_VISIBILITY)
    ):
        return None
    return float(f.point(Pose.LEFT_WRIST)[1] - f.point(Pose.RIGHT_WRIST)[1])


def shoulder_height_px(f: BodyFeatures) -> float:
    """Shoulder midpoint height in the image (pixels from the top, up = +). Always defined."""
    return -float(f.origin_px[1])


# Running: arm swing p5 0.21 (median 0.32), 450 ms range p1 ~0.4.
# Idle: swing <= 0.03, range <= 0.07.
ARM_SWING = OscillationParams(swing_lo=0.08, swing_hi=0.18, range_lo=0.15, range_hi=0.35)

# Bounce is one-sided: the shoulders' lowest point while running is about their
# standing height, and each step pushes them *up* from there. Requiring both
# sides of the baseline (as for the arms) made W flicker off ~0.5 s into a run,
# while the baseline still remembered standing. So only the upward side counts
# (labelled recordings of 2026-11-02):
#   running: up-swing min 0.076, 450 ms range p1 0.090
#   not running: up-swing <= 0.022, range <= 0.049
# swing_hi is set well below the running minimum so a gentler bounce than
# measured (half the size) still scores ~1.
# No median filter: at ~2.6 Hz and 15 fps a cycle is only ~6 samples and the
# filter clips the peaks.
BOUNCE = OscillationParams(
    swing_lo=0.02,
    swing_hi=0.045,
    range_lo=0.035,
    range_hi=0.07,
    smooth=False,
    pixel_signal=True,
    sides="up",
)


class RunningInPlace:
    """Running in place: arm swing AND body bounce (see module docstring)."""

    def __init__(
        self,
        name: str = "running_in_place",
        arms: OscillationParams = ARM_SWING,
        bounce: OscillationParams = BOUNCE,
    ):
        self.name = name
        self.arms = arms
        self.bounce = bounce

    def evaluate(self, window: FeatureWindow) -> Evaluation:
        a = oscillation(window, arm_swing, self.arms)
        if a.score is None:
            return Evaluation(score=None)
        b = oscillation(window, shoulder_height_px, self.bounce)
        score = min(a.score, b.score if b.score is not None else 0.0)
        details = {f"arms.{k}": v for k, v in a.details.items()}
        details.update({f"bounce.{k}": v for k, v in b.details.items()})
        details["score"] = score
        return Evaluation(score=score, details=details)


def pumping_arms(name: str = "pumping_arms") -> OscillationDetector:
    """Arm swing on its own, for seated play (no bounce required)."""
    return OscillationDetector(name, arm_swing, ARM_SWING)
