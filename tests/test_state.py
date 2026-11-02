import pytest

from sww.state import DebounceConfig, EventKind, GestureState

FRAME_MS = 33  # ~30 fps


def feed(state: GestureState, scores, start_ms: int = 0):
    """Feed scores one frame apart; return [(frame_index, kind)] for emitted events."""
    out = []
    for i, s in enumerate(scores):
        ev = state.update(s, start_ms + i * FRAME_MS)
        if ev is not None:
            out.append((i, ev.kind))
    return out


def test_starts_after_min_on_ms():
    st = GestureState("g", DebounceConfig(enter=0.6, exit=0.4, min_on_ms=50, min_off_ms=150))
    # frames at 0, 33, 66 ms: 66 - 0 >= 50 -> START on the 3rd high frame
    assert feed(st, [0.0, 0.9, 0.9, 0.9, 0.9]) == [(3, EventKind.START)]
    assert st.active


def test_single_frame_glitch_is_ignored():
    st = GestureState("g", DebounceConfig(min_on_ms=50))
    assert feed(st, [0.0, 0.9, 0.0, 0.9, 0.0, 0.9, 0.0]) == []
    assert not st.active


def test_hysteresis_keeps_gesture_active_between_thresholds():
    st = GestureState("g", DebounceConfig(enter=0.6, exit=0.4, min_on_ms=0, min_off_ms=0))
    events = feed(st, [0.7, 0.5, 0.45, 0.55, 0.41, 0.5])
    assert events == [(0, EventKind.START)]
    assert st.active


def test_ends_after_min_off_ms():
    st = GestureState("g", DebounceConfig(min_on_ms=0, min_off_ms=150))
    events = feed(st, [0.9] + [0.0] * 8)
    # low from frame 1 (33 ms); 33 + 150 = 183 -> first frame at >= 183 ms is frame 6 (198 ms)
    assert events == [(0, EventKind.START), (6, EventKind.END)]


def test_short_dropout_while_active_does_not_end():
    st = GestureState("g", DebounceConfig(min_on_ms=0, min_off_ms=150))
    events = feed(st, [0.9, 0.0, 0.0, 0.9, 0.9, 0.0, 0.9])
    assert events == [(0, EventKind.START)]


def test_tracking_lost_ends_gesture():
    st = GestureState("g", DebounceConfig(min_on_ms=0, min_off_ms=100))
    events = feed(st, [0.9, None, None, None, None, None])
    # lost from 33 ms; 33 + 100 = 133 -> frame 5 (165 ms)
    assert events == [(0, EventKind.START), (5, EventKind.END)]


def test_none_never_starts_gesture():
    st = GestureState("g", DebounceConfig(min_on_ms=0))
    assert feed(st, [None] * 5) == []


def test_reset_ends_active_gesture():
    st = GestureState("g", DebounceConfig(min_on_ms=0))
    st.update(1.0, 0)
    ev = st.reset(100)
    assert ev is not None and ev.kind is EventKind.END and ev.timestamp_ms == 100
    assert st.reset(200) is None


@pytest.mark.parametrize(
    "kwargs",
    [{"enter": 0.4, "exit": 0.6}, {"enter": 0.5, "exit": 0.5}, {"min_on_ms": -1}, {"enter": 1.5}],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        DebounceConfig(**kwargs)
