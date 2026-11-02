"""Action mapper: gesture events → keyboard actions.

Step 1 supports **tap** only (one press + release when a gesture starts).
Hold (one key-down on start, one key-up on end) arrives in roadmap step 2
together with the safety releases it needs.

Fair play: each START event produces at most one tap. Nothing is repeated or
scheduled for later.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from sww.output.base import KeyboardBackend
from sww.output.keys import key_to_vk
from sww.state import EventKind, GestureEvent


class Mode(StrEnum):
    TAP = "tap"


@dataclass(frozen=True, slots=True)
class Mapping:
    """Bind one gesture to one key."""

    gesture: str
    key: str
    mode: Mode = Mode.TAP

    def __post_init__(self) -> None:
        key_to_vk(self.key)  # fail fast on typos


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """What the mapper did (or chose not to do) for one event. For logs and tests."""

    event: GestureEvent
    key: str
    action: str  # "tap" or "blocked"
    reason: str = ""


class ActionMapper:
    """Route gesture events to a keyboard backend.

    Args:
        mappings: One mapping per gesture name.
        backend: Where key events go.
        gate: Optional check run before sending; when it returns False the
            action is skipped (e.g. the target window isn't focused).
    """

    def __init__(
        self,
        mappings: Iterable[Mapping],
        backend: KeyboardBackend,
        gate: Callable[[], bool] | None = None,
    ):
        self._by_gesture: dict[str, Mapping] = {}
        for m in mappings:
            if m.gesture in self._by_gesture:
                raise ValueError(f"gesture {m.gesture!r} mapped twice (one gesture = one action)")
            self._by_gesture[m.gesture] = m
        self.backend = backend
        self.gate = gate

    def handle(self, event: GestureEvent) -> ActionRecord | None:
        """Perform the mapped action for ``event``, if any."""
        mapping = self._by_gesture.get(event.gesture)
        if mapping is None or event.kind is not EventKind.START:
            return None  # taps only act on START
        if self.gate is not None and not self.gate():
            return ActionRecord(event, mapping.key, "blocked", "target window not focused")
        self.backend.tap(mapping.key)
        return ActionRecord(event, mapping.key, "tap")
