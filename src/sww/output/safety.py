"""Release held keys when the console window is closed (Windows).

``try/finally`` in the run loop covers normal exit, Ctrl+C and Python
exceptions. It does *not* run when you click the console's X button, log off or
shut down: Windows then sends a "control event" to the process and kills it a
few seconds later. ``SetConsoleCtrlHandler`` lets us run code on that event,
so we release held keys there.

What nothing can cover: a hard kill (Task Manager "End task" on the process,
``taskkill /f``) or a power cut. Windows then still thinks the injected key is
down until it sees a key-up; pressing the key once on the real keyboard clears
it.
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
from collections.abc import Callable
from ctypes import wintypes

CTRL_C_EVENT = 0
CTRL_BREAK_EVENT = 1
CTRL_CLOSE_EVENT = 2
CTRL_LOGOFF_EVENT = 5
CTRL_SHUTDOWN_EVENT = 6

# Ctrl+C is left alone: Python turns it into KeyboardInterrupt, and the run
# loop's `finally` releases keys. Ctrl+Break kills Python without an exception.
_RELEASE_ON = {CTRL_BREAK_EVENT, CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT}


def install_console_close_handler(on_close: Callable[[], None]) -> Callable[[], None]:
    """Run ``on_close`` when the console is closed. Returns a function that uninstalls it.

    A no-op on other platforms. ``on_close`` runs on a thread Windows creates,
    so it must be thread-safe and quick (Windows allows ~5 s).
    """
    if sys.platform != "win32":
        return lambda: None

    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def handler(ctrl_type: int) -> bool:
        if ctrl_type in _RELEASE_ON:
            with contextlib.suppress(Exception):
                on_close()
        return False  # let the default handling (exit / KeyboardInterrupt) continue

    c_handler = handler_type(handler)  # must stay referenced while installed
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetConsoleCtrlHandler.argtypes = (handler_type, wintypes.BOOL)
    kernel32.SetConsoleCtrlHandler(c_handler, True)

    def uninstall() -> None:
        kernel32.SetConsoleCtrlHandler(c_handler, False)

    uninstall.handler = c_handler  # type: ignore[attr-defined]  # keep it alive
    return uninstall
