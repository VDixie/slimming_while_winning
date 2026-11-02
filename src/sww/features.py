"""Feature extraction: convert raw landmarks into a body-centred frame.

Body frame (used by every gesture rule)
---------------------------------------
- Origin: midpoint between the two shoulders.
- x axis: image-right (pixels right / shoulder width). Not mirrored.
- y axis: **up** (we negate image y so "higher" means larger y; more intuitive
  for rules like "hand above head").
- Unit: one *shoulder width* in pixels. Expressing positions in shoulder widths
  makes thresholds roughly independent of how far you stand from the camera
  and of the camera resolution.

Why pixels first: MediaPipe normalises x by image width and y by image height.
On a 16:9 image one unit of x is 1.78x longer than one unit of y, so distances
and angles computed directly on normalised coordinates would be distorted.

Known limitation: if you turn sideways, apparent shoulder width shrinks and all
body-frame distances inflate. Per-user calibration (roadmap step 3) will
replace this with a reference measured in a neutral pose.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sww.landmarks import Pose, PoseFrame

# Minimum MediaPipe visibility for a landmark to be trusted.
DEFAULT_MIN_VISIBILITY = 0.5

# Below this apparent shoulder width (pixels) the person is too far away or the
# shoulders are mis-detected; scale-normalising would amplify noise.
MIN_SHOULDER_WIDTH_PX = 20.0


@dataclass(frozen=True, slots=True)
class BodyFeatures:
    """Landmarks expressed in the body frame (see module docstring).

    Attributes:
        timestamp_ms: Copied from the source :class:`PoseFrame`.
        points: ``(33, 2)`` float32 array, body-frame x/y in shoulder widths.
        visibility: ``(33,)`` float32 array, MediaPipe visibility 0..1.
        shoulder_width_px: The scale used, in pixels (useful for debugging).
    """

    timestamp_ms: int
    points: np.ndarray
    visibility: np.ndarray
    shoulder_width_px: float

    def visible(self, idx: Pose, min_visibility: float = DEFAULT_MIN_VISIBILITY) -> bool:
        """Return True if landmark ``idx`` is visible enough to use."""
        return bool(self.visibility[idx] >= min_visibility)

    def point(self, idx: Pose) -> np.ndarray:
        """Return the body-frame ``(x, y)`` of one landmark."""
        return self.points[idx]


def to_body_frame(
    frame: PoseFrame, min_visibility: float = DEFAULT_MIN_VISIBILITY
) -> BodyFeatures | None:
    """Convert a :class:`PoseFrame` to :class:`BodyFeatures`.

    Returns None if both shoulders aren't visible or are implausibly close
    together, because the body frame can't be defined without them.
    """
    vis = frame.visibility
    if vis[Pose.LEFT_SHOULDER] < min_visibility or vis[Pose.RIGHT_SHOULDER] < min_visibility:
        return None

    px = frame.pixels()  # (33, 2), origin top-left, y down
    left_sh = px[Pose.LEFT_SHOULDER]
    right_sh = px[Pose.RIGHT_SHOULDER]
    shoulder_width = float(np.linalg.norm(left_sh - right_sh))
    if shoulder_width < MIN_SHOULDER_WIDTH_PX:
        return None

    origin = (left_sh + right_sh) / 2.0
    body = (px - origin) / shoulder_width
    body[:, 1] *= -1.0  # flip so +y is up

    return BodyFeatures(
        timestamp_ms=frame.timestamp_ms,
        points=body.astype(np.float32),
        visibility=vis.astype(np.float32),
        shoulder_width_px=shoulder_width,
    )


def joint_angle_deg(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Return the angle ABC in degrees (0..180), i.e. the bend at joint ``b``.

    180 means the three points are in a straight line (e.g. a straight arm);
    small values mean a sharp bend. Computed in 2D, so a limb pointing towards
    the camera is foreshortened and the angle is only approximate.
    """
    ba = a - b
    bc = c - b
    denom = float(np.linalg.norm(ba) * np.linalg.norm(bc))
    if denom < 1e-9:
        return 180.0
    cos_angle = float(np.dot(ba, bc)) / denom
    return float(np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0))))
