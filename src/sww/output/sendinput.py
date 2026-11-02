"""Windows keyboard output via the ``SendInput`` API with scan codes.

``SendInput`` inserts events into the OS input stream exactly as if they came
from a physical keyboard. We send **scan codes** (``KEYEVENTF_SCANCODE``)
rather than virtual-key codes because games that read raw/hardware input often
ignore VK-only events.

Limitations:
- Windows' UIPI blocks injected input into a process running at a higher
  privilege level. Don't run WoW/Battle.net as administrator, or run this app
  at the same level.
- The events go to whichever window has keyboard focus. Use the focus gate
  (``--window``) so keys only go to the intended window.

Windows-only: importing works anywhere, but constructing the backend on another
OS raises ``OSError``.
"""

from __future__ import annotations

import ctypes
import sys
import time

from sww.output.keys import EXTENDED_VKS, key_to_vk

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0

# Win32 integer types with explicit widths. (ctypes.wintypes.DWORD is
# c_ulong, which is 8 bytes on Linux; fixed widths keep the struct layout
# identical everywhere, so the layout test below runs on any OS.)
WORD = ctypes.c_uint16
DWORD = ctypes.c_uint32
LONG = ctypes.c_int32
# ULONG_PTR: an unsigned integer the size of a pointer (8 bytes on 64-bit).
ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", WORD),
        ("wScan", WORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class MOUSEINPUT(ctypes.Structure):
    # Only declared so the union below has the correct (largest) size;
    # SendInput rejects INPUT structs whose size it doesn't expect.
    _fields_ = (
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", DWORD),
        ("wParamL", WORD),
        ("wParamH", WORD),
    )


class _InputUnion(ctypes.Union):
    _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (("type", DWORD), ("u", _InputUnion))


class SendInputBackend:
    """Send key events with ``SendInput`` + scan codes.

    Args:
        tap_ms: How long a tap holds the key down. 0 sends down+up in a single
            ``SendInput`` call. Some games miss a press whose key-up arrives in
            the same instant; ~15-30 ms behaves like a quick human tap. This
            blocks the caller for ``tap_ms``.
    """

    def __init__(self, tap_ms: int = 15) -> None:
        if sys.platform != "win32":
            raise OSError("SendInputBackend only works on Windows")
        self.tap_ms = tap_ms
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
        self._user32.SendInput.restype = ctypes.c_uint
        self._user32.MapVirtualKeyW.argtypes = (ctypes.c_uint, ctypes.c_uint)
        self._user32.MapVirtualKeyW.restype = ctypes.c_uint

    def _make_input(self, key: str, key_up: bool) -> INPUT:
        vk = key_to_vk(key)
        scan = self._user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        if scan == 0:
            raise ValueError(f"no scan code for key {key!r} on this keyboard layout")
        flags = KEYEVENTF_SCANCODE
        if vk in EXTENDED_VKS:
            flags |= KEYEVENTF_EXTENDEDKEY
        if key_up:
            flags |= KEYEVENTF_KEYUP
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
        return inp

    def _send(self, *inputs: INPUT) -> None:
        array = (INPUT * len(inputs))(*inputs)
        sent = self._user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
        if sent != len(inputs):
            err = ctypes.get_last_error()
            raise OSError(err, f"SendInput sent {sent}/{len(inputs)} events (blocked by UIPI?)")

    def tap(self, key: str) -> None:
        down = self._make_input(key, key_up=False)
        up = self._make_input(key, key_up=True)
        if self.tap_ms <= 0:
            self._send(down, up)
            return
        self._send(down)
        try:
            time.sleep(self.tap_ms / 1000.0)
        finally:
            self._send(up)  # always release, even on Ctrl+C mid-tap

    def key_down(self, key: str) -> None:
        self._send(self._make_input(key, key_up=False))

    def key_up(self, key: str) -> None:
        self._send(self._make_input(key, key_up=True))
