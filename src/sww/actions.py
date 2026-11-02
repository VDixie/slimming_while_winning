"""Action mapper: gesture events → keyboard actions, plus the safety releases.

Modes:

- **tap**: one press + release when the gesture starts.
- **hold**: one key-down when the gesture starts, one key-up when it ends.
  Never repeated presses: Windows auto-repeats a *physical* key you hold, but
  an injected key-down stays a single event, and games like WoW read whether
  the key is down, not the repeats.

Safety releases (every held key gets a key-up when any of these happens):

- the target window loses focus (:meth:`ActionMapper.check_gate`, every frame)
- output is paused (:meth:`ActionMapper.set_paused`, e.g. by the global hotkey)
- tracking is lost (the engine ends active gestures, see :mod:`sww.engine`)
- the app exits, crashes or its console is closed (:meth:`ActionMapper.release_all`)

**Re-arm rule (fair play):** after a safety release the key is *not* pressed
again by itself when focus returns or the app resumes, even if you're still
performing the gesture. Only a new gesture START presses it again, so every
key-down follows from one deliberate gesture.

Thread safety: the pause hotkey and console-close handlers run on other
threads, so every public method takes one lock. A tap holds the lock for its
``tap_ms`` (default 15 ms).
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from sww.output.base import KeyboardBackend
from sww.output.keys import key_to_vk
from sww.state import EventKind, GestureEvent


class Mode(StrEnum):
    TAP = "tap"
    HOLD = "hold"


@dataclass(frozen=True, slots=True)
class Mapping:
    """Bind one gesture to one key."""

    gesture: str
    key: str
    mode: Mode = Mode.TAP

    def __post_init__(self) -> None:
        key_to_vk(self.key)  # fail fast on typos


class ActionKind(StrEnum):
    TAP = "tap"
    DOWN = "down"  # hold started
    UP = "up"  # hold ended with the gesture
    RELEASE = "release"  # held key released for safety (reason says why)
    BLOCKED = "blocked"  # gesture started but nothing was sent (reason says why)


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """What the mapper did (or chose not to do). For logs, the preview and tests."""

    gesture: str
    key: str
    action: ActionKind
    timestamp_ms: int
    reason: str = ""

    def describe(self) -> str:
        text = f"{self.action.value.upper()} '{self.key}'"
        return f"{text} ({self.reason})" if self.reason else text


class ActionMapper:
    """Route gesture events to a keyboard backend.

    Args:
        mappings: One mapping per gesture name.
        backend: Where key events go.
        gate: Optional check run before sending; when it returns False the
            action is skipped (e.g. the target window isn't focused). For held
            keys it is also checked every frame (:meth:`check_gate`).
    """

    def __init__(
        self,
        mappings: Iterable[Mapping],
        backend: KeyboardBackend,
        gate: Callable[[], bool] | None = None,
    ):
        self._by_gesture: dict[str, Mapping] = {}
        hold_keys: dict[str, str] = {}
        for m in mappings:
            if m.gesture in self._by_gesture:
                raise ValueError(f"gesture {m.gesture!r} mapped twice (one gesture = one action)")
            if m.mode is Mode.HOLD:
                key = m.key.lower()
                if key in hold_keys:
                    raise ValueError(
                        f"key {m.key!r} held by both {hold_keys[key]!r} and {m.gesture!r}; "
                        "one gesture ending would release the other's key"
                    )
                hold_keys[key] = m.gesture
            self._by_gesture[m.gesture] = m
        self.backend = backend
        self.gate = gate
        self._held: dict[str, str] = {}  # gesture -> key currently held down
        self._paused = False
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ state

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def held_keys(self) -> list[str]:
        """Keys currently held down by this mapper."""
        with self._lock:
            return list(self._held.values())

    # ------------------------------------------------------------------ events

    def handle(self, event: GestureEvent) -> ActionRecord | None:
        """Perform the mapped action for ``event``, if any."""
        with self._lock:
            mapping = self._by_gesture.get(event.gesture)
            if mapping is None:
                return None
            ts = event.timestamp_ms
            if event.kind is EventKind.END:
                if mapping.mode is Mode.HOLD and event.gesture in self._held:
                    key = self._held.pop(event.gesture)
                    self.backend.key_up(key)
                    return ActionRecord(event.gesture, key, ActionKind.UP, ts)
                return None  # taps don't act on END; a safety-released hold is already up

            # START
            if self._paused:
                return ActionRecord(event.gesture, mapping.key, ActionKind.BLOCKED, ts, "paused")
            if self.gate is not None and not self.gate():
                return ActionRecord(
                    event.gesture, mapping.key, ActionKind.BLOCKED, ts, "target window not focused"
                )
            if mapping.mode is Mode.TAP:
                self.backend.tap(mapping.key)
                return ActionRecord(event.gesture, mapping.key, ActionKind.TAP, ts)
            if event.gesture in self._held:
                return None  # already down: never send a second key-down
            self.backend.key_down(mapping.key)
            self._held[event.gesture] = mapping.key
            return ActionRecord(event.gesture, mapping.key, ActionKind.DOWN, ts)

    # ------------------------------------------------------------------ safety

    def release_all(self, reason: str, timestamp_ms: int = 0) -> list[ActionRecord]:
        """Send a key-up for every held key. Safe to call repeatedly and from any thread."""
        with self._lock:
            records = []
            for gesture, key in list(self._held.items()):
                del self._held[gesture]
                # Keep releasing the others even if one fails; nothing better to do here.
                with contextlib.suppress(Exception):
                    self.backend.key_up(key)
                records.append(ActionRecord(gesture, key, ActionKind.RELEASE, timestamp_ms, reason))
            return records

    def check_gate(self, timestamp_ms: int = 0) -> list[ActionRecord]:
        """Release held keys if the focus gate now says no. Call once per frame."""
        with self._lock:
            if not self._held or self.gate is None or self.gate():
                return []
            return self.release_all("target window lost focus", timestamp_ms)

    def set_paused(self, paused: bool, timestamp_ms: int = 0) -> list[ActionRecord]:
        """Pause (release everything, block new actions) or resume output."""
        with self._lock:
            self._paused = paused
            return self.release_all("paused", timestamp_ms) if paused else []

    def toggle_pause(self, timestamp_ms: int = 0) -> list[ActionRecord]:
        with self._lock:
            return self.set_paused(not self._paused, timestamp_ms)
