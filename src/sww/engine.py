"""The per-frame pipeline after tracking: features → detectors → state → actions.

This part has no camera or model dependency, so it can be driven from recorded
or synthetic landmark streams in tests (replay testing).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sww.actions import ActionMapper, ActionRecord
from sww.features import BodyFeatures, to_body_frame
from sww.gestures.base import Evaluation, GestureDetector
from sww.landmarks import PoseFrame
from sww.state import DebounceConfig, GestureEvent, GestureState


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
    """Run detectors and state machines for every frame and dispatch actions."""

    def __init__(
        self,
        detectors: Sequence[GestureDetector],
        mapper: ActionMapper,
        debounce: dict[str, DebounceConfig] | None = None,
    ):
        names = [d.name for d in detectors]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate detector names: {names}")
        debounce = debounce or {}
        self.detectors = list(detectors)
        self.states = {d.name: GestureState(d.name, debounce.get(d.name)) for d in detectors}
        self.mapper = mapper

    def step(self, frame: PoseFrame | None, timestamp_ms: int) -> StepResult:
        """Process one frame. Pass ``frame=None`` when no person was detected."""
        features = to_body_frame(frame) if frame is not None else None
        result = StepResult(timestamp_ms=timestamp_ms, features=features)
        for det in self.detectors:
            ev = det.evaluate(features)
            result.evaluations[det.name] = ev
            event = self.states[det.name].update(ev.score, timestamp_ms)
            result.active[det.name] = self.states[det.name].active
            if event is None:
                continue
            result.events.append(event)
            record = self.mapper.handle(event)
            if record is not None:
                result.actions.append(record)
        return result

    def run(self, frames: Iterable[tuple[PoseFrame | None, int]]) -> list[StepResult]:
        """Convenience for replay tests: step through ``(frame, timestamp_ms)`` pairs."""
        return [self.step(frame, t) for frame, t in frames]
