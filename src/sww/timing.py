"""Rolling performance stats: frame rate and per-stage latency.

What the numbers mean (all milliseconds):
- ``age``: frame captured → we start processing it. High values mean the main
  loop is falling behind the camera.
- ``track``: MediaPipe inference + colour conversion.
- ``e2e``: frame captured → key decision made (what you'd feel in game).
  It does *not* include the camera's own sensor/USB delay before ``read()``
  returns (typically another 30-60 ms) or the game's input handling.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class StatsSummary:
    fps: float
    age_mean: float
    track_mean: float
    track_p95: float
    e2e_mean: float
    e2e_p95: float

    def __str__(self) -> str:
        return (
            f"fps {self.fps:5.1f} | track {self.track_mean:5.1f} ms (p95 {self.track_p95:5.1f}) "
            f"| age {self.age_mean:5.1f} ms | e2e {self.e2e_mean:5.1f} ms "
            f"(p95 {self.e2e_p95:5.1f})"
        )


class PerfStats:
    """Keep the last ``window`` frames of timings."""

    def __init__(self, window: int = 300):
        self._t: deque[int] = deque(maxlen=window)
        self._age: deque[float] = deque(maxlen=window)
        self._track: deque[float] = deque(maxlen=window)
        self._e2e: deque[float] = deque(maxlen=window)

    def add(self, captured_ms: int, start_ms: int, tracked_ms: int, done_ms: int) -> None:
        self._t.append(done_ms)
        self._age.append(start_ms - captured_ms)
        self._track.append(tracked_ms - start_ms)
        self._e2e.append(done_ms - captured_ms)

    def __len__(self) -> int:
        return len(self._t)

    def summary(self) -> StatsSummary | None:
        if len(self._t) < 2:
            return None
        span_s = (self._t[-1] - self._t[0]) / 1000.0
        fps = (len(self._t) - 1) / span_s if span_s > 0 else 0.0
        track = np.asarray(self._track)
        e2e = np.asarray(self._e2e)
        return StatsSummary(
            fps=fps,
            age_mean=float(np.mean(self._age)),
            track_mean=float(track.mean()),
            track_p95=float(np.percentile(track, 95)),
            e2e_mean=float(e2e.mean()),
            e2e_p95=float(np.percentile(e2e, 95)),
        )
