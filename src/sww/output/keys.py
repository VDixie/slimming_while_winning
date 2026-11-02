"""Key names → Windows virtual-key codes, plus which keys are "extended".

Background (Windows keyboard input):

- A **virtual-key code** (VK) is a layout-independent ID like ``VK_SPACE``
  (0x20). Many games, WoW included, read the hardware **scan code** instead,
  which identifies the physical key position. We look up the VK here and let
  Windows translate it into the scan code for the active keyboard layout
  (``MapVirtualKeyW``) at send time; see :mod:`sww.output.sendinput`.
- Some keys (arrows, Insert/Delete/Home/End/PageUp/PageDown, right Ctrl/Alt,
  NumLock, numpad divide) share scan codes with other keys and are told apart
  by an "extended" prefix (0xE0). They must be sent with the
  ``KEYEVENTF_EXTENDEDKEY`` flag, or e.g. Up arrow arrives as numpad 8.

Kept free of ctypes so it can be unit-tested on any OS.
"""

from __future__ import annotations

_NAMED_VK: dict[str, int] = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0xA0,  # left shift
    "ctrl": 0xA2,  # left control
    "alt": 0xA4,  # left alt
    "pause": 0x13,
    "capslock": 0x14,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "rshift": 0xA1,
    "rctrl": 0xA3,
    "ralt": 0xA5,
    "num*": 0x6A,
    "num+": 0x6B,
    "num-": 0x6D,
    "num.": 0x6E,
    "num/": 0x6F,
    # US-layout punctuation (OEM keys). Other layouts: use the key on the
    # same physical position.
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
}

# Letters, digits, function keys, numpad digits.
_NAMED_VK.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})
_NAMED_VK.update({str(d): 0x30 + d for d in range(10)})
_NAMED_VK.update({f"f{n}": 0x70 + n - 1 for n in range(1, 25)})
_NAMED_VK.update({f"num{d}": 0x60 + d for d in range(10)})

EXTENDED_VKS: frozenset[int] = frozenset(
    {
        0x21, 0x22, 0x23, 0x24,  # PageUp, PageDown, End, Home
        0x25, 0x26, 0x27, 0x28,  # arrows
        0x2D, 0x2E,  # Insert, Delete
        0x6F,  # numpad divide
        0x90,  # NumLock
        0xA3, 0xA5,  # right Ctrl, right Alt
    }
)  # fmt: skip


def key_to_vk(key: str) -> int:
    """Return the virtual-key code for a key name (case-insensitive).

    Raises:
        ValueError: if the name isn't known.
    """
    name = key.strip().lower()
    try:
        return _NAMED_VK[name]
    except KeyError:
        raise ValueError(f"unknown key name {key!r}") from None


def known_keys() -> list[str]:
    """All accepted key names, sorted."""
    return sorted(_NAMED_VK)
