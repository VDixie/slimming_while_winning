"""Keyboard output backend interface.

Fair-play contract (see PROJECT_INSTRUCTIONS.md): a backend only ever performs
the single key operation it is asked for. No repeats, no sequences, no timers
that fire later on their own.
"""

from __future__ import annotations

from typing import Protocol


class KeyboardBackend(Protocol):
    """Sends OS-level key events. Key names are case-insensitive, e.g. ``"b"``, ``"space"``."""

    def tap(self, key: str) -> None:
        """Press and release ``key`` once."""
        ...

    def key_down(self, key: str) -> None:
        """Send a single key-down for ``key``."""
        ...

    def key_up(self, key: str) -> None:
        """Send a single key-up for ``key``."""
        ...


class RecordingBackend:
    """Backend that only records calls. Used for ``--dry-run``, tests and non-Windows."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def tap(self, key: str) -> None:
        self.calls.append(("tap", key.lower()))

    def key_down(self, key: str) -> None:
        self.calls.append(("down", key.lower()))

    def key_up(self, key: str) -> None:
        self.calls.append(("up", key.lower()))
