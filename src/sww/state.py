"""Gesture state machine: turns a noisy per-frame score into clean start/end events.

Two mechanisms stop keys flickering:

- **Hysteresis**: a gesture starts when the score rises to ``enter`` (e.g. 0.6)
  but only ends when it falls below a lower ``exit`` (e.g. 0.4). A score
  hovering around 0.5 therefore can't toggle it on and off.
- **Debounce**: the score must stay past the threshold for ``min_on_ms`` before
  the gesture starts, and stay below ``exit`` for ``min_off_ms`` before it
  ends. Single-frame glitches are ignored.

Debounce times are in milliseconds, not frames, so behaviour doesn't change if
the frame rate drops. Trade-off: ``min_on_ms`` adds directly to
gesture-to-keypress latency. At 30 fps, 50 ms means three consecutive frames
(t=0, 33, 67 ms) above ``enter``.

A score of None (tracking lost) counts as "below exit", so a lost person ends
the gesture after ``min_off_ms``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventKind(StrEnum):
    START = "start"
    END = "end"


@dataclass(frozen=True, slots=True)
class GestureEvent:
    """A gesture began or finished at ``timestamp_ms``."""

    gesture: str
    kind: EventKind
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class DebounceConfig:
    """Thresholds (score units 0..1) and minimum durations (milliseconds)."""

    enter: float = 0.6
    exit: float = 0.4
    min_on_ms: int = 50
    min_off_ms: int = 150

    def __post_init__(self) -> None:
        if not 0.0 <= self.exit < self.enter <= 1.0:
            raise ValueError("need 0 <= exit < enter <= 1")
        if self.min_on_ms < 0 or self.min_off_ms < 0:
            raise ValueError("durations must be >= 0")


class GestureState:
    """Tracks one gesture. Call :meth:`update` once per frame."""

    def __init__(self, gesture: str, config: DebounceConfig | None = None):
        self.gesture = gesture
        self.config = config or DebounceConfig()
        self.active = False
        # When the score first crossed the relevant threshold; None = not crossing.
        self._crossing_since_ms: int | None = None

    def update(self, score: float | None, timestamp_ms: int) -> GestureEvent | None:
        """Feed one frame's score; return an event if the gesture started or ended."""
        cfg = self.config
        if not self.active:
            crossing = score is not None and score >= cfg.enter
            needed = cfg.min_on_ms
        else:
            crossing = score is None or score < cfg.exit
            needed = cfg.min_off_ms

        if not crossing:
            self._crossing_since_ms = None
            return None

        if self._crossing_since_ms is None:
            self._crossing_since_ms = timestamp_ms
        if timestamp_ms - self._crossing_since_ms < needed:
            return None

        self._crossing_since_ms = None
        self.active = not self.active
        kind = EventKind.START if self.active else EventKind.END
        return GestureEvent(self.gesture, kind, timestamp_ms)

    def reset(self, timestamp_ms: int) -> GestureEvent | None:
        """Force the gesture inactive (e.g. on pause). Returns END if it was active."""
        self._crossing_since_ms = None
        if self.active:
            self.active = False
            return GestureEvent(self.gesture, EventKind.END, timestamp_ms)
        return None
