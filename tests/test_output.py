import ctypes
import sys

import pytest

from sww.cli import main
from sww.output.keys import EXTENDED_VKS, key_to_vk, known_keys
from sww.output.sendinput import INPUT, KEYBDINPUT, SendInputBackend


@pytest.mark.parametrize(
    ("name", "vk"),
    [("b", 0x42), ("B", 0x42), ("w", 0x57), ("space", 0x20), ("tab", 0x09), ("1", 0x31),
     ("f1", 0x70), ("f12", 0x7B), ("numlock", 0x90), ("num0", 0x60), ("up", 0x26)],
)  # fmt: skip
def test_key_to_vk(name, vk):
    assert key_to_vk(name) == vk


def test_unknown_key():
    with pytest.raises(ValueError):
        key_to_vk("hyper")


def test_extended_keys():
    assert key_to_vk("up") in EXTENDED_VKS
    assert key_to_vk("numlock") in EXTENDED_VKS
    assert key_to_vk("b") not in EXTENDED_VKS
    assert key_to_vk("space") not in EXTENDED_VKS


def test_known_keys_cover_wow_defaults():
    assert {"w", "a", "s", "d", "q", "e", "b", "m", "space", "tab", "numlock"} <= set(known_keys())


@pytest.mark.skipif(ctypes.sizeof(ctypes.c_void_p) != 8, reason="64-bit layout")
def test_input_struct_matches_win64_abi():
    # SendInput validates cbSize; on 64-bit Windows sizeof(INPUT) == 40.
    assert ctypes.sizeof(KEYBDINPUT) == 24
    assert ctypes.sizeof(INPUT) == 40


@pytest.mark.skipif(sys.platform == "win32", reason="checks the non-Windows guard")
def test_sendinput_backend_refuses_off_windows():
    with pytest.raises(OSError):
        SendInputBackend()


def test_keytest_dry_run(capsys):
    assert main(["keytest", "--key", "b", "--delay", "0"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "Would have tapped 'b'" in out


def test_cli_rejects_unknown_key(capsys):
    with pytest.raises(SystemExit):
        main(["run", "--key", "hyper"])
