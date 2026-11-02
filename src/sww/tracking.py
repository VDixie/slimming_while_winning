"""Pose tracking with MediaPipe's PoseLandmarker (Tasks API).

Running mode: we use ``VIDEO`` (synchronous ``detect_for_video``). In this
mode MediaPipe tracks the person from frame to frame instead of re-detecting
from scratch each time, which is faster and steadier. Synchronous calls keep
the pipeline simple; frame dropping is handled by
:class:`sww.capture.LatestFrameCamera`.

Models (download with ``sww download-models``):
- ``lite``: fastest, the default. Good enough for large arm/body gestures.
- ``full`` / ``heavy``: more accurate, more CPU.
Internally every variant resizes the image to 256x256, so feeding a 720p frame
doesn't make inference slower, only the BGR→RGB conversion.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from sww.landmarks import NUM_POSE_LANDMARKS, PoseFrame


class PoseTracker:
    """Wrap a MediaPipe PoseLandmarker for single-person video tracking."""

    def __init__(
        self,
        model_path: Path,
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        if not model_path.is_file():
            raise FileNotFoundError(
                f"pose model not found: {model_path}. Run `uv run sww download-models` first."
            )
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=min_detection_confidence,
            min_pose_presence_confidence=min_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)
        self._last_ts = -1

    def process(self, image_bgr: np.ndarray, timestamp_ms: int) -> PoseFrame | None:
        """Track one frame. Returns None if no person is found.

        ``timestamp_ms`` must increase between calls (MediaPipe requirement);
        equal or older timestamps are bumped forward by 1 ms.
        """
        ts = max(timestamp_ms, self._last_ts + 1)
        self._last_ts = ts
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, ts)
        if not result.pose_landmarks:
            return None
        lms = result.pose_landmarks[0]
        arr = np.empty((NUM_POSE_LANDMARKS, 4), dtype=np.float32)
        for i, lm in enumerate(lms):
            arr[i] = (lm.x, lm.y, lm.z, lm.visibility if lm.visibility is not None else 0.0)
        height, width = image_bgr.shape[:2]
        return PoseFrame(timestamp_ms=timestamp_ms, landmarks=arr, image_size=(width, height))

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> PoseTracker:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
