"""Landmark data types shared by tracking, features and tests.

Coordinate system of :class:`PoseFrame.landmarks` (exactly what MediaPipe returns):

- ``x``: horizontal position, normalised to image width. 0 = left edge of the
  *unmirrored* camera image, 1 = right edge.
- ``y``: vertical position, normalised to image height. 0 = top, 1 = bottom
  (so y grows *downwards*).
- ``z``: depth relative to the hips' midpoint, roughly the same scale as ``x``;
  smaller = closer to the camera. Single-camera depth is a rough estimate.
- ``visibility``: 0..1, the model's estimate that the point is visible
  (not occluded and inside the frame).

Because x and y are normalised by *different* lengths (width vs height), any
distance or angle must first be converted to pixels; see :mod:`sww.features`.

"Left"/"right" in landmark names are the *person's* left/right. In an
unmirrored webcam image the person's left shoulder appears on the image's right.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np

NUM_POSE_LANDMARKS = 33


class Pose(IntEnum):
    """Indices into MediaPipe's 33-point pose model (BlazePose topology)."""

    NOSE = 0
    LEFT_EYE_INNER = 1
    LEFT_EYE = 2
    LEFT_EYE_OUTER = 3
    RIGHT_EYE_INNER = 4
    RIGHT_EYE = 5
    RIGHT_EYE_OUTER = 6
    LEFT_EAR = 7
    RIGHT_EAR = 8
    MOUTH_LEFT = 9
    MOUTH_RIGHT = 10
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_PINKY = 17
    RIGHT_PINKY = 18
    LEFT_INDEX = 19
    RIGHT_INDEX = 20
    LEFT_THUMB = 21
    RIGHT_THUMB = 22
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28
    LEFT_HEEL = 29
    RIGHT_HEEL = 30
    LEFT_FOOT_INDEX = 31
    RIGHT_FOOT_INDEX = 32


# Skeleton edges for drawing the preview overlay.
POSE_CONNECTIONS: tuple[tuple[Pose, Pose], ...] = (
    (Pose.LEFT_SHOULDER, Pose.RIGHT_SHOULDER),
    (Pose.LEFT_SHOULDER, Pose.LEFT_ELBOW),
    (Pose.LEFT_ELBOW, Pose.LEFT_WRIST),
    (Pose.RIGHT_SHOULDER, Pose.RIGHT_ELBOW),
    (Pose.RIGHT_ELBOW, Pose.RIGHT_WRIST),
    (Pose.LEFT_WRIST, Pose.LEFT_INDEX),
    (Pose.LEFT_WRIST, Pose.LEFT_PINKY),
    (Pose.RIGHT_WRIST, Pose.RIGHT_INDEX),
    (Pose.RIGHT_WRIST, Pose.RIGHT_PINKY),
    (Pose.LEFT_SHOULDER, Pose.LEFT_HIP),
    (Pose.RIGHT_SHOULDER, Pose.RIGHT_HIP),
    (Pose.LEFT_HIP, Pose.RIGHT_HIP),
    (Pose.LEFT_HIP, Pose.LEFT_KNEE),
    (Pose.LEFT_KNEE, Pose.LEFT_ANKLE),
    (Pose.RIGHT_HIP, Pose.RIGHT_KNEE),
    (Pose.RIGHT_KNEE, Pose.RIGHT_ANKLE),
    (Pose.LEFT_EAR, Pose.LEFT_EYE),
    (Pose.LEFT_EYE, Pose.NOSE),
    (Pose.NOSE, Pose.RIGHT_EYE),
    (Pose.RIGHT_EYE, Pose.RIGHT_EAR),
)


@dataclass(frozen=True, slots=True)
class PoseFrame:
    """One frame of pose landmarks for a single person.

    Attributes:
        timestamp_ms: Capture time in milliseconds on a monotonic clock.
        landmarks: Array of shape ``(33, 4)``, float32, columns
            ``(x, y, z, visibility)`` in MediaPipe's normalised image
            coordinates (see module docstring).
        image_size: ``(width, height)`` of the source image in pixels.
    """

    timestamp_ms: int
    landmarks: np.ndarray
    image_size: tuple[int, int]

    def __post_init__(self) -> None:
        if self.landmarks.shape != (NUM_POSE_LANDMARKS, 4):
            raise ValueError(
                f"landmarks must have shape ({NUM_POSE_LANDMARKS}, 4), got {self.landmarks.shape}"
            )

    def pixels(self) -> np.ndarray:
        """Return ``(33, 2)`` x/y positions in pixels (origin top-left, y down)."""
        width, height = self.image_size
        return self.landmarks[:, :2] * np.array([width, height], dtype=np.float32)

    @property
    def visibility(self) -> np.ndarray:
        """Return the ``(33,)`` visibility column."""
        return self.landmarks[:, 3]
