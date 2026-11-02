"""Find the frame-rate bottleneck: time the camera and the pose model separately.

The ``run`` loop can only go as fast as its slowest stage:

    fps  <=  min(camera fps, 1000 / tracking ms)

So we measure:
1. **Camera**: frames per second actually delivered for several capture
   settings (backend, MJPG on/off, resolution). Nothing else runs.
2. **Model**: milliseconds per frame for each downloaded pose model, run on a
   real frame from your camera (a blank image would skip the expensive
   landmark stage, because no person is found).
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from sww.capture import LatestFrameCamera


@dataclass(frozen=True, slots=True)
class CameraResult:
    api: str
    mjpg: bool
    requested: tuple[int, int]
    actual: tuple[int, int]
    fourcc: str
    fps: float
    error: str = ""

    def __str__(self) -> str:
        req = f"{self.requested[0]}x{self.requested[1]}"
        if self.error:
            return (
                f"  {self.api:5} mjpg={'on ' if self.mjpg else 'off'} {req:>9}  ERROR {self.error}"
            )
        act = f"{self.actual[0]}x{self.actual[1]}"
        return (
            f"  {self.api:5} mjpg={'on ' if self.mjpg else 'off'} {req:>9} -> {act:>9} "
            f"{self.fourcc:4}  {self.fps:5.1f} fps"
        )


def bench_camera(
    index: int, api: str, mjpg: bool, size: tuple[int, int], seconds: float
) -> tuple[CameraResult, np.ndarray | None]:
    """Measure delivered fps for one capture configuration. Also returns the last frame."""
    cam = LatestFrameCamera(index, size[0], size[1], 30, api=api, mjpg=mjpg)
    try:
        cam.start()
    except RuntimeError as exc:
        return CameraResult(api, mjpg, size, (0, 0), "", 0.0, str(exc)), None
    try:
        # Warm-up: the first frames after opening are often slow (auto exposure settling).
        first = cam.read_latest(0, timeout_s=3.0)
        if first is None:
            return CameraResult(
                api, mjpg, size, cam.actual_size, cam.actual_fourcc, 0.0, "no frames"
            ), None
        time.sleep(0.5)
        start = cam.read_latest(0, timeout_s=2.0)
        assert start is not None
        last = start
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            frame = cam.read_latest(last.seq, timeout_s=2.0)
            if frame is None:
                break
            last = frame
        elapsed = (last.timestamp_ms - start.timestamp_ms) / 1000.0
        fps = (last.seq - start.seq) / elapsed if elapsed > 0 else 0.0
        h, w = last.image.shape[:2]
        return CameraResult(api, mjpg, size, (w, h), cam.actual_fourcc, fps), last.image
    finally:
        cam.stop()


def bench_cameras(
    index: int, apis: Iterable[str], sizes: Iterable[tuple[int, int]], seconds: float
) -> tuple[list[CameraResult], np.ndarray | None]:
    """Try every combination of backend x MJPG x size, printing as it goes."""
    results: list[CameraResult] = []
    sample: np.ndarray | None = None
    for api, mjpg, size in itertools.product(apis, (True, False), sizes):
        result, image = bench_camera(index, api, mjpg, size, seconds)
        print(result, flush=True)
        results.append(result)
        if image is not None and (sample is None or image.shape[1] == 1280):
            sample = image
    return results, sample


@dataclass(frozen=True, slots=True)
class ModelResult:
    variant: str
    convert_ms: float
    track_mean_ms: float
    track_p95_ms: float
    person_found: bool

    def __str__(self) -> str:
        max_fps = 1000.0 / (self.convert_ms + self.track_mean_ms)
        note = "" if self.person_found else "  (no person in sample frame: number too optimistic)"
        return (
            f"  {self.variant:5}  BGR->RGB {self.convert_ms:4.1f} ms  "
            f"track {self.track_mean_ms:5.1f} ms "
            f"(p95 {self.track_p95_ms:5.1f})  -> max ~{max_fps:4.0f} fps{note}"
        )


def bench_model(model_path: Path, variant: str, image_bgr: np.ndarray, n: int = 100) -> ModelResult:
    """Time colour conversion and pose tracking on one frame, ``n`` times."""
    import cv2

    from sww.tracking import PoseTracker

    convert = []
    for _ in range(20):
        t0 = time.perf_counter()
        cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        convert.append((time.perf_counter() - t0) * 1000)

    times = []
    found = False
    with PoseTracker(model_path) as tracker:
        for i in range(n + 5):
            t0 = time.perf_counter()
            pose = tracker.process(image_bgr, i * 33)
            dt = (time.perf_counter() - t0) * 1000
            found = found or pose is not None
            if i >= 5:  # skip warm-up (first calls initialise the model)
                times.append(dt)
    arr = np.asarray(times)
    return ModelResult(
        variant,
        float(np.median(convert)),
        float(arr.mean()) - float(np.median(convert)),
        float(np.percentile(arr, 95)) - float(np.median(convert)),
        found,
    )
