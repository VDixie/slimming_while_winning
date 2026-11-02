"""Focus gate: only allow output while a chosen window is in the foreground.

Reads just the *title* of the foreground window via ``GetForegroundWindow`` /
``GetWindowTextW``. It doesn't look at the window's contents, memory or
pixels, so it stays within the fair-play rules.
"""

from __future__ import annotations

import ctypes
import functools
import sys
from collections.abc import Callable
from ctypes import wintypes


@functools.cache
def _user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    return user32


def foreground_window_title() -> str:
    """Return the title of the current foreground window (Windows only).

    Cheap (two system calls), so it's fine to call every frame while a key is held.
    """
    if sys.platform != "win32":
        raise OSError("foreground_window_title only works on Windows")
    user32 = _user32()
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_title_gate(
    substring: str, title_source: Callable[[], str] = foreground_window_title
) -> Callable[[], bool]:
    """Return a function that is True while the foreground title contains ``substring``.

    Matching is case-insensitive. ``title_source`` is injectable for tests.
    """
    needle = substring.lower()

    def gate() -> bool:
        return needle in title_source().lower()

    return gate
