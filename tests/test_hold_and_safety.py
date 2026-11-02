"""Hold mode, pause and safety releases (mapper + engine), plus hotkey parsing."""

import sys

import pytest
from synthetic import motion_stream

from sww.actions import ActionKind, ActionMapper, Mapping, Mode
from sww.engine import Engine
from sww.gestures import HandOnHead, RunningInPlace
from sww.output import RecordingBackend
from sww.output.hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, GlobalHotkey, parse_hotkey
from sww.output.keys import key_to_vk
from sww.output.safety import install_console_close_handler
from sww.state import DebounceConfig, EventKind, GestureEvent


def start(g="run", t=0):
    return GestureEvent(g, EventKind.START, t)


def end(g="run", t=0):
    return GestureEvent(g, EventKind.END, t)


def hold_mapper(gate=None):
    backend = RecordingBackend()
    mapper = ActionMapper([Mapping("run", "w", Mode.HOLD), Mapping("head", "b")], backend, gate)
    return mapper, backend


# ---------------------------------------------------------------- hold


def test_hold_sends_one_down_and_one_up():
    mapper, backend = hold_mapper()
    assert mapper.handle(start()).action is ActionKind.DOWN
    assert mapper.held_keys == ["w"]
    assert mapper.handle(end()).action is ActionKind.UP
    assert backend.calls == [("down", "w"), ("up", "w")]
    assert mapper.held_keys == []


def test_hold_never_sends_a_second_key_down():
    mapper, backend = hold_mapper()
    mapper.handle(start())
    assert mapper.handle(start()) is None
    assert backend.calls == [("down", "w")]


def test_end_without_hold_sends_nothing():
    mapper, backend = hold_mapper()
    assert mapper.handle(end()) is None
    assert backend.calls == []


def test_two_holds_on_one_key_rejected():
    with pytest.raises(ValueError, match="held by both"):
        ActionMapper(
            [Mapping("a", "w", Mode.HOLD), Mapping("b", "W", Mode.HOLD)], RecordingBackend()
        )


# ---------------------------------------------------------------- focus gate


def test_focus_loss_releases_and_does_not_repress_on_return():
    focused = True
    mapper, backend = hold_mapper(gate=lambda: focused)
    mapper.handle(start())
    assert mapper.check_gate() == []
    focused = False
    (rec,) = mapper.check_gate(123)
    assert rec.action is ActionKind.RELEASE and rec.reason == "target window lost focus"
    focused = True
    assert mapper.check_gate() == []  # focus back, gesture still going: no automatic re-press
    assert mapper.handle(end()) is None  # the gesture's END finds nothing held
    mapper.handle(start())  # a new gesture presses again
    assert backend.calls == [("down", "w"), ("up", "w"), ("down", "w")]


def test_hold_blocked_when_unfocused_at_start():
    mapper, backend = hold_mapper(gate=lambda: False)
    assert mapper.handle(start()).action is ActionKind.BLOCKED
    assert backend.calls == [] and mapper.held_keys == []


# ---------------------------------------------------------------- pause


def test_pause_releases_blocks_and_resume_does_not_repress():
    mapper, backend = hold_mapper()
    mapper.handle(start())
    (rec,) = mapper.toggle_pause(5)
    assert mapper.paused and rec.action is ActionKind.RELEASE and rec.reason == "paused"
    blocked = mapper.handle(start("head"))
    assert blocked.action is ActionKind.BLOCKED and blocked.reason == "paused"
    assert mapper.toggle_pause() == []
    assert not mapper.paused
    assert backend.calls == [("down", "w"), ("up", "w")]
    mapper.handle(start("head"))
    assert backend.calls[-1] == ("tap", "b")


def test_release_all_is_idempotent():
    mapper, backend = hold_mapper()
    mapper.handle(start())
    assert len(mapper.release_all("exit")) == 1
    assert mapper.release_all("exit") == []
    assert backend.calls == [("down", "w"), ("up", "w")]


def test_release_all_continues_after_a_backend_error():
    class Flaky(RecordingBackend):
        def key_up(self, key):
            super().key_up(key)
            if key == "w":
                raise OSError("boom")

    backend = Flaky()
    mapper = ActionMapper([Mapping("a", "w", Mode.HOLD), Mapping("b", "s", Mode.HOLD)], backend)
    mapper.handle(start("a"))
    mapper.handle(start("b"))
    assert len(mapper.release_all("exit")) == 2
    assert ("up", "s") in backend.calls and mapper.held_keys == []


# ---------------------------------------------------------------- engine


def make_engine(gate=None):
    backend = RecordingBackend()
    run = RunningInPlace("run")
    head = HandOnHead("head")
    mapper = ActionMapper([Mapping("run", "w", Mode.HOLD), Mapping("head", "b")], backend, gate)
    engine = Engine([head, run], mapper, {"run": DebounceConfig(min_off_ms=200)})
    return engine, backend


def test_engine_checks_focus_every_frame():
    focused = [True]
    engine, backend = make_engine(gate=lambda: focused[0])
    frames = list(motion_stream([("stand", 1000), ("run", 5000)]))
    for frame, t in frames[:120]:
        engine.step(frame, t)
    assert backend.calls == [("down", "w")]
    focused[0] = False
    result = engine.step(*frames[120])
    assert [r.action for r in result.actions] == [ActionKind.RELEASE]
    focused[0] = True
    for frame, t in frames[121:]:
        engine.step(frame, t)
    assert backend.calls == [("down", "w"), ("up", "w")]  # not pressed again


def test_brief_dropout_keeps_holding():
    engine, backend = make_engine()
    stream = motion_stream([("stand", 1000), ("run", 3000), (None, 100), ("run", 3000)])
    engine.run(stream)
    assert backend.calls == [("down", "w")]


def test_shutdown_releases_everything():
    engine, backend = make_engine()
    engine.run(motion_stream([("stand", 1000), ("run", 3000)]))
    (rec,) = engine.shutdown("exit", 9)
    assert rec.reason == "exit" and backend.calls[-1] == ("up", "w")


# ---------------------------------------------------------------- hotkey / console


@pytest.mark.parametrize(
    ("spec", "mods", "key"),
    [
        ("ctrl+alt+p", MOD_CONTROL | MOD_ALT, "p"),
        ("Ctrl + Shift + F9", MOD_CONTROL | MOD_SHIFT, "f9"),
        ("pause", 0, "pause"),
        ("ctrl+num+", MOD_CONTROL, "num+"),
    ],
)
def test_parse_hotkey(spec, mods, key):
    assert parse_hotkey(spec) == (mods, key_to_vk(key))


def test_parse_hotkey_rejects_unknown_key():
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+hyper")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows API")
def test_global_hotkey_registers_and_stops():
    # An obscure combination nobody uses; registered and released within the test.
    with GlobalHotkey("ctrl+alt+shift+f24", lambda: None) as hk:
        assert hk._thread is not None and hk._thread.is_alive()
    assert not hk._thread.is_alive()


def test_console_close_handler_installs_and_uninstalls():
    uninstall = install_console_close_handler(lambda: None)
    uninstall()
