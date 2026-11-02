"""End-to-end replay tests: synthetic landmark streams through the whole engine."""

import numpy as np
import pytest
from synthetic import make_frame

from sww.actions import ActionMapper, Mapping
from sww.engine import Engine
from sww.gestures import HandOnHead
from sww.output import RecordingBackend
from sww.output.focus import window_title_gate
from sww.state import EventKind, GestureEvent

FRAME_MS = 33


def stream(segments, rng=None, jitter_px=0.0):
    """Yield (frame, t) from [(pose_kwargs | None, n_frames), ...]. None = no person."""
    t = 0
    for kwargs, n in segments:
        for _ in range(n):
            frame = (
                None if kwargs is None else make_frame(t, jitter_px=jitter_px, rng=rng, **kwargs)
            )
            yield frame, t
            t += FRAME_MS


def make_engine(gate=None):
    backend = RecordingBackend()
    det = HandOnHead()
    engine = Engine([det], ActionMapper([Mapping(det.name, "B")], backend, gate))
    return engine, backend


# ---------------------------------------------------------------- mapper


def test_mapper_taps_on_start_only():
    backend = RecordingBackend()
    mapper = ActionMapper([Mapping("g", "b")], backend)
    assert mapper.handle(GestureEvent("g", EventKind.START, 0)).action == "tap"
    assert mapper.handle(GestureEvent("g", EventKind.END, 10)) is None
    assert mapper.handle(GestureEvent("other", EventKind.START, 20)) is None
    assert backend.calls == [("tap", "b")]


def test_mapper_gate_blocks():
    backend = RecordingBackend()
    mapper = ActionMapper([Mapping("g", "b")], backend, gate=lambda: False)
    rec = mapper.handle(GestureEvent("g", EventKind.START, 0))
    assert rec.action == "blocked"
    assert backend.calls == []


def test_one_gesture_cannot_map_to_two_actions():
    with pytest.raises(ValueError, match="one gesture = one action"):
        ActionMapper([Mapping("g", "b"), Mapping("g", "c")], RecordingBackend())


def test_unknown_key_rejected():
    with pytest.raises(ValueError):
        Mapping("g", "not-a-key")


def test_window_title_gate():
    title = "Untitled - Notepad"
    gate = window_title_gate("notepad", title_source=lambda: title)
    assert gate()
    title = "World of Warcraft"
    assert not gate()


# ---------------------------------------------------------------- engine replay


def test_hand_on_head_twice_gives_exactly_two_taps():
    engine, backend = make_engine()
    segments = [({}, 15), ({"right": "on_head"}, 30), ({}, 20), ({"left": "on_head"}, 30), ({}, 10)]
    results = engine.run(stream(segments))
    assert backend.calls == [("tap", "b"), ("tap", "b")]
    kinds = [e.kind for r in results for e in r.events]
    assert kinds == [EventKind.START, EventKind.END, EventKind.START, EventKind.END]


def test_holding_pose_does_not_repeat():
    engine, backend = make_engine()
    engine.run(stream([({"right": "on_head"}, 300)]))  # ~10 s held
    assert backend.calls == [("tap", "b")]


def test_noisy_stream_gives_single_tap():
    engine, backend = make_engine()
    rng = np.random.default_rng(7)
    engine.run(stream([({}, 20), ({"right": "on_head"}, 40), ({}, 20)], rng=rng, jitter_px=5.0))
    assert backend.calls == [("tap", "b")]


def test_brief_tracking_dropout_does_not_retrigger():
    engine, backend = make_engine()
    segments = [({"right": "on_head"}, 10), (None, 2), ({"right": "on_head"}, 10)]
    engine.run(stream(segments))
    assert backend.calls == [("tap", "b")]


def test_passing_through_head_height_quickly_does_not_fire():
    engine, backend = make_engine()
    # One frame on the head is shorter than min_on_ms (50 ms).
    engine.run(stream([({}, 5), ({"right": "on_head"}, 1), ({}, 5)]))
    assert backend.calls == []


def test_arms_overhead_and_chin_do_not_fire():
    engine, backend = make_engine()
    engine.run(stream([({"right": "overhead", "left": "overhead"}, 30), ({"right": "chin"}, 30)]))
    assert backend.calls == []


def test_no_person_never_fires():
    engine, backend = make_engine()
    results = engine.run(stream([(None, 30)]))
    assert backend.calls == []
    assert all(r.features is None for r in results)
