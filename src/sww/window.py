"""Rolling window of recent body features, for gestures that unfold over time.

Static gestures (hand on head) only need the newest frame, but dynamic ones
(running in place) need to see how landmarks moved over the last second or so.
The engine keeps one :class:`FeatureWindow` and hands it to every detector, so
each detector can look as far back as it needs. Trained classifiers (roadmap
step 4) will read their input sequences from the same window.

The window is bounded by **time in milliseconds**, not by a number of frames,
so a detector's behaviour doesn't change if the frame rate drops from 30 to 20
fps; it just sees fewer samples.

Frames where no person was tracked are kept as ``None`` entries, so detectors
can tell "no data" apart from "no movement".
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator

from sww.features import BodyFeatures


class FeatureWindow:
    """The last ``span_ms`` milliseconds of ``(timestamp_ms, features | None)``.

    Args:
        span_ms: How much history to keep. Must cover the longest look-back of
            any detector (default 3 s).
    """

    def __init__(self, span_ms: int = 3000):
        if span_ms <= 0:
            raise ValueError("span_ms must be > 0")
        self.span_ms = span_ms
        self._items: deque[tuple[int, BodyFeatures | None]] = deque()

    @classmethod
    def of(cls, features: BodyFeatures | None, timestamp_ms: int | None = None) -> FeatureWindow:
        """Window holding a single frame (handy for static detectors and tests)."""
        win = cls()
        ts = timestamp_ms if timestamp_ms is not None else getattr(features, "timestamp_ms", 0)
        win.push(ts, features)
        return win

    def push(self, timestamp_ms: int, features: BodyFeatures | None) -> None:
        """Add the newest frame and drop entries older than ``span_ms``.

        Timestamps must not go backwards (they come from a monotonic clock).
        """
        if self._items and timestamp_ms < self._items[-1][0]:
            raise ValueError("timestamps must not decrease")
        self._items.append((timestamp_ms, features))
        cutoff = timestamp_ms - self.span_ms
        while self._items and self._items[0][0] < cutoff:
            self._items.popleft()

    def clear(self) -> None:
        self._items.clear()

    @property
    def latest(self) -> BodyFeatures | None:
        """Features of the newest frame (None if no person, or the window is empty)."""
        return self._items[-1][1] if self._items else None

    @property
    def latest_ms(self) -> int | None:
        return self._items[-1][0] if self._items else None

    def since(self, ms: int) -> list[tuple[int, BodyFeatures | None]]:
        """Entries from the last ``ms`` milliseconds (inclusive), oldest first."""
        if not self._items:
            return []
        cutoff = self._items[-1][0] - ms
        return [item for item in self._items if item[0] >= cutoff]

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[tuple[int, BodyFeatures | None]]:
        return iter(self._items)
