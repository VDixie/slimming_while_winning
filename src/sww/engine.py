"""The per-frame pipeline after tracking: features → window → detectors → state → actions.

This part has no camera or model dependency, so it can be driven from recorded
or synthetic landmark streams in tests (replay testing).

Safety handled here (the rest lives in :mod:`sww.actions`):

- **Tracking lost**: if no usable person is seen for ``lost_release_ms``, every
  active gesture is ended, which releases its held key. This is independent of
  each gesture's own off-debounce, which may be longer (running needs ~200 ms
  to bridge the gap between strides).
- **Focus lost**: the mapper's gate is checked every frame while a key is held.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sww.actions import ActionMapper, ActionRecord
from sww.features import BodyFeatures, to_body_frame
from sww.gestures.base import Evaluation, GestureDetector
from sww.landmarks import PoseFrame
from sww.state import DebounceConfig, GestureEvent, GestureState
from sww.window import FeatureWindow

DEFAULT_LOST_RELEASE_MS = 150


@dataclass(slots=True)
class StepResult:
    """Everything that happened for one frame (for overlay, logging and tests)."""

    timestamp_ms: int
    features: BodyFeatures | None
    evaluations: dict[str, Evaluation] = field(default_factory=dict)
    active: dict[str, bool] = field(default_factory=dict)
    events: list[GestureEvent] = field(default_factory=list)
    actions: list[ActionRecord] = field(default_factory=list)


class Engine:
    """Run detectors and state machines for every frame and dispatch actions.

    Args:
        detectors: One per gesture; names must be unique.
        mapper: Turns gesture events into key actions.
        debounce: Per-gesture thresholds/timings (defaults otherwise).
        window_ms: History kept for dynamic detectors.
        lost_release_ms: End all gestures after this long without a person.
    """

    def __init__(
        self,
        detectors: Sequence[GestureDetector],
        mapper: ActionMapper,
        debounce: dict[str, DebounceConfig] | None = None,
        window_ms: int = 3000,
        lost_release_ms: int = DEFAULT_LOST_RELEASE_MS,
    ):
        names = [d.name for d in detectors]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate detector names: {names}")
        debounce = debounce or {}
        self.detectors = list(detectors)
        self.states = {d.name: GestureState(d.name, debounce.get(d.name)) for d in detectors}
        self.mapper = mapper
        self.window = FeatureWindow(window_ms)
        self.lost_release_ms = lost_release_ms
        self._lost_since_ms: int | None = None

    def _dispatch(self, event: GestureEvent, result: StepResult) -> None:
        result.events.append(event)
        record = self.mapper.handle(event)
        if record is not None:
            result.actions.append(record)

    def step(self, frame: PoseFrame | None, timestamp_ms: int) -> StepResult:
        """Process one frame. Pass ``frame=None`` when no person was detected."""
        features = to_body_frame(frame) if frame is not None else None
        self.window.push(timestamp_ms, features)
        result = StepResult(timestamp_ms=timestamp_ms, features=features)

        if features is None:
            if self._lost_since_ms is None:
                self._lost_since_ms = timestamp_ms
            if timestamp_ms - self._lost_since_ms >= self.lost_release_ms:
                for state in self.states.values():
                    event = state.reset(timestamp_ms)
                    if event is not None:
                        self._dispatch(event, result)
        else:
            self._lost_since_ms = None

        for det in self.detectors:
            ev = det.evaluate(self.window)
            result.evaluations[det.name] = ev
            event = self.states[det.name].update(ev.score, timestamp_ms)
            result.active[det.name] = self.states[det.name].active
            if event is not None:
                self._dispatch(event, result)

        result.actions.extend(self.mapper.check_gate(timestamp_ms))
        return result

    def run(self, frames: Iterable[tuple[PoseFrame | None, int]]) -> list[StepResult]:
        """Convenience for replay tests: step through ``(frame, timestamp_ms)`` pairs."""
        return [self.step(frame, t) for frame, t in frames]

    def shutdown(self, reason: str = "exit", timestamp_ms: int = 0) -> list[ActionRecord]:
        """Release every held key (call from ``finally``)."""
        return self.mapper.release_all(reason, timestamp_ms)
