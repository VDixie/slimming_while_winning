"""Global hotkey (works while the game has focus), used to pause/resume output.

How it works on Windows: ``RegisterHotKey`` asks the OS to watch for a key
combination system-wide. When it's pressed, Windows posts a ``WM_HOTKEY``
message to the *thread that registered it*, and the combination is not passed
on to the focused app (WoW won't see it). Receiving that message needs a
message loop (``GetMessageW``), so the hotkey lives on its own small thread.

The callback runs on that thread, so it must be thread-safe
(:meth:`sww.actions.ActionMapper.toggle_pause` is). Releasing held keys right
there, rather than waiting for the camera loop, means a pause takes effect even
if the camera has stalled.

Limitation: if a program running as administrator has focus, Windows may not
deliver the hotkey to us (the same UIPI rule that blocks injected input).
"""

from __future__ import annotations

import ctypes
import sys
import threading
import traceback
from collections.abc import Callable
from ctypes import wintypes

from sww.output.keys import key_to_vk

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000  # holding the combo doesn't fire repeatedly
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
_HOTKEY_ID = 0x5357  # any id unique within this thread

_MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT,
              "win": MOD_WIN}  # fmt: skip

DEFAULT_PAUSE_HOTKEY = "ctrl+alt+p"


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse e.g. ``"ctrl+alt+p"`` or ``"pause"`` into ``(modifier flags, virtual-key code)``.

    Modifiers come first; the rest is one key name from :mod:`sww.output.keys`
    (so ``"ctrl+num+"`` means Ctrl + numpad plus).

    Raises:
        ValueError: unknown key name.
    """
    tokens = [t.strip() for t in spec.lower().split("+")]
    mods = 0
    i = 0
    while i < len(tokens) - 1 and tokens[i] in _MODIFIERS:
        mods |= _MODIFIERS[tokens[i]]
        i += 1
    return mods, key_to_vk("+".join(tokens[i:]))


class GlobalHotkey:
    """Call ``callback`` whenever ``spec`` is pressed anywhere in Windows.

    Use as a context manager, or call :meth:`start` / :meth:`stop`.
    """

    def __init__(self, spec: str, callback: Callable[[], None]):
        self.spec = spec
        self.modifiers, self.vk = parse_hotkey(spec)
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._error: OSError | None = None

    def start(self) -> None:
        """Register the hotkey. Raises ``OSError`` if Windows refuses (already taken)."""
        if sys.platform != "win32":
            raise OSError("global hotkeys only work on Windows")
        self._thread = threading.Thread(target=self._loop, name="sww-hotkey", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=2.0):
            raise OSError("hotkey thread did not start")
        if self._error is not None:
            raise self._error

    def _loop(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.GetMessageW.argtypes = (
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        )
        user32.GetMessageW.restype = ctypes.c_int  # BOOL, but -1 means error

        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, _HOTKEY_ID, self.modifiers | MOD_NOREPEAT, self.vk):
            self._error = OSError(
                ctypes.get_last_error(),
                f"could not register hotkey {self.spec!r}; another program may already use it",
            )
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    try:
                        self.callback()
                    except Exception:
                        traceback.print_exc()
        finally:
            user32.UnregisterHotKey(None, _HOTKEY_ID)

    def stop(self) -> None:
        """Unregister the hotkey and end the thread."""
        if self._thread is None or not self._thread.is_alive():
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.PostThreadMessageW.argtypes = (
            wintypes.DWORD,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=1.0)

    def __enter__(self) -> GlobalHotkey:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
