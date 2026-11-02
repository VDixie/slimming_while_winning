"""Landmark recordings: save what the tracker saw, replay it through the engine later.

Recordings store **landmarks, not video**: about 0.5 KB per frame before
compression, private (no image of you or your room), and enough to re-run
every gesture detector exactly as it ran live. They are used for tuning
thresholds (``sww replay --csv``), for regression tests, and later (roadmap
step 4) as training data.

File format: a NumPy ``.npz`` archive (zip of arrays; ``np.load`` reads it,
and pandas users can turn the arrays into a DataFrame in one line):

=================  ==============  ===========================================
array              shape / dtype   meaning
=================  ==============  ===========================================
``timestamps_ms``  (N,) int64      capture time, monotonic ms (see PoseFrame)
``landmarks``      (N, 33, 4) f32  MediaPipe x, y, z, visibility (normalised
                                   image coords, see :mod:`sww.landmarks`);
                                   all NaN where no person was detected
``image_size``     (2,) int64      width, height in pixels
``meta``           () str          JSON: format version, label, model, camera,
                                   start time, ...
=================  ==============  ===========================================
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from sww.landmarks import NUM_POSE_LANDMARKS, PoseFrame

FORMAT_VERSION = 1


@dataclass(slots=True)
class Recording:
    """A sequence of pose frames (see module docstring for the layout)."""

    timestamps_ms: np.ndarray
    landmarks: np.ndarray
    image_size: tuple[int, int]
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = len(self.timestamps_ms)
        if self.landmarks.shape != (n, NUM_POSE_LANDMARKS, 4):
            raise ValueError(f"landmarks shape {self.landmarks.shape} doesn't match {n} frames")
        if n > 1 and np.any(np.diff(self.timestamps_ms) < 0):
            raise ValueError("timestamps must not decrease")

    @classmethod
    def from_frames(
        cls,
        frames: Iterable[tuple[PoseFrame | None, int]],
        image_size: tuple[int, int],
        meta: dict[str, Any] | None = None,
    ) -> Recording:
        """Build from ``(frame or None, timestamp_ms)`` pairs."""
        times: list[int] = []
        rows: list[np.ndarray] = []
        missing = np.full((NUM_POSE_LANDMARKS, 4), np.nan, dtype=np.float32)
        for frame, ts in frames:
            times.append(ts)
            rows.append(missing if frame is None else frame.landmarks.astype(np.float32))
        landmarks = (
            np.stack(rows) if rows else np.empty((0, NUM_POSE_LANDMARKS, 4), dtype=np.float32)
        )
        return cls(np.asarray(times, dtype=np.int64), landmarks, image_size, dict(meta or {}))

    # ------------------------------------------------------------------ access

    def __len__(self) -> int:
        return len(self.timestamps_ms)

    @property
    def person_present(self) -> np.ndarray:
        """(N,) bool: True where a person was tracked."""
        return ~np.isnan(self.landmarks[:, 0, 0])

    @property
    def duration_ms(self) -> int:
        return int(self.timestamps_ms[-1] - self.timestamps_ms[0]) if len(self) > 1 else 0

    def frames(self) -> Iterator[tuple[PoseFrame | None, int]]:
        """Yield ``(PoseFrame or None, timestamp_ms)``, ready for :meth:`Engine.run`."""
        present = self.person_present
        for i, ts in enumerate(self.timestamps_ms.tolist()):
            frame = (
                PoseFrame(timestamp_ms=ts, landmarks=self.landmarks[i], image_size=self.image_size)
                if present[i]
                else None
            )
            yield frame, ts

    # ------------------------------------------------------------------ files

    def save(self, path: Path) -> Path:
        """Write a compressed ``.npz`` (parent folders are created)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {"format_version": FORMAT_VERSION, **self.meta}
        np.savez_compressed(
            path,
            timestamps_ms=self.timestamps_ms,
            landmarks=self.landmarks,
            image_size=np.asarray(self.image_size, dtype=np.int64),
            meta=np.asarray(json.dumps(meta)),
        )
        return path

    @classmethod
    def load(cls, path: Path) -> Recording:
        with np.load(Path(path), allow_pickle=False) as data:
            meta = json.loads(str(data["meta"]))
            version = meta.get("format_version")
            if version != FORMAT_VERSION:
                raise ValueError(f"{path}: unsupported recording format version {version}")
            width, height = (int(v) for v in data["image_size"])
            return cls(
                timestamps_ms=data["timestamps_ms"].astype(np.int64),
                landmarks=data["landmarks"].astype(np.float32),
                image_size=(width, height),
                meta=meta,
            )
