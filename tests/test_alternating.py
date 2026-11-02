"""Running in place / pumping arms detector on synthetic landmark streams."""

import numpy as np
import pytest
from synthetic import FRAME_MS, motion_stream

from sww.actions import ActionMapper, Mapping, Mode
from sww.engine import Engine
from sww.features import to_body_frame
from sww.gestures import PUMPING_ARMS, RUNNING_IN_PLACE, AlternatingMotion, AlternatingParams
from sww.gestures.alternating import median3
from sww.landmarks import Pose
from sww.output import RecordingBackend
from sww.state import DebounceConfig, EventKind
from sww.window import FeatureWindow

RUN = "running_in_place"


def scores(segments, params=RUNNING_IN_PLACE, **kwargs) -> list[tuple[int, float | None]]:
    """(t, score) for every frame of a motion stream."""
    det = AlternatingMotion(RUN, params)
    win = FeatureWindow()
    out = []
    for frame, t in motion_stream(segments, **kwargs):
        win.push(t, to_body_frame(frame) if frame is not None else None)
        out.append((t, det.evaluate(win).score))
    return out


def make_engine():
    backend = RecordingBackend()
    det = AlternatingMotion(RUN, RUNNING_IN_PLACE)
    mapper = ActionMapper([Mapping(RUN, "w", Mode.HOLD)], backend)
    engine = Engine([det], mapper, {RUN: DebounceConfig(min_on_ms=50, min_off_ms=200)})
    return engine, backend


def event_times(results, kind):
    return [e.timestamp_ms for r in results for e in r.events if e.kind is kind]


# ---------------------------------------------------------------- building blocks


def test_median3_removes_single_spikes_only():
    x = np.array([0.0, 0.0, 5.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    np.testing.assert_array_equal(median3(x), [0, 0, 0, 0, 0, 1, 1, 1])
    np.testing.assert_array_equal(median3(np.array([1.0, 2.0])), [1.0, 2.0])


def test_params_validate_window_order():
    with pytest.raises(ValueError):
        AlternatingParams(Pose.LEFT_KNEE, Pose.RIGHT_KNEE, 0.1, 0.2, 0.1, 0.2, swing_ms=200)


# ---------------------------------------------------------------- scores


def test_standing_still_scores_zero():
    s = [v for _, v in scores([("stand", 3000)])]
    assert max(s) == 0.0


@pytest.mark.parametrize("freq_hz", [1.5, 2.0, 3.0])
def test_running_scores_high_once_both_legs_lifted(freq_hz):
    s = scores([("stand", 2000), ("run", 3000)], freq_hz=freq_hz)
    running = [v for t, v in s if t >= 3000]  # after the first second of running
    assert min(running) > 0.8


def test_scale_invariant():
    near = scores([("stand", 1000), ("run", 2000)], scale=0.5)
    far = scores([("stand", 1000), ("run", 2000)], scale=0.35)
    np.testing.assert_allclose([v for _, v in near], [v for _, v in far], atol=1e-3)


def test_knees_below_the_image_are_ignored_even_if_marked_visible():
    # Real bug from the first recordings: MediaPipe guessed off-screen knees with
    # visibility ~0.7. At scale 1 the synthetic knees lie below the 720p image.
    s = scores([("stand", 1000), ("run", 3000)], scale=1.0)
    assert {v for _, v in s} == {0.0}


def test_jitter_while_standing_stays_below_enter_threshold():
    s = scores([("stand", 6000)], jitter_px=4.0, seed=3)
    assert max(v for _, v in s) < 0.4


def test_single_knee_lift_is_not_running():
    s = scores([("stand", 2000), ("lift_left", 1500), ("stand", 1500)], lift=0.5)
    assert max(v for _, v in s) == 0.0


def test_hidden_knees_score_zero():
    s = scores([("run", 3000)], hidden=(Pose.LEFT_KNEE,))
    assert {v for _, v in s} == {0.0}


def test_legs_out_of_frame_score_zero():
    det = AlternatingMotion(RUN, RUNNING_IN_PLACE)
    win = FeatureWindow()
    for frame, t in motion_stream([("run", 2000)], legs_visible=False):
        win.push(t, to_body_frame(frame))
    ev = det.evaluate(win)
    assert ev.score == 0.0 and ev.details == {"visible": 0.0}


def test_no_person_gives_none():
    assert AlternatingMotion(RUN, RUNNING_IN_PLACE).evaluate(FeatureWindow.of(None)).score is None


def test_pumping_arms_preset_uses_wrists():
    s = scores([("stand", 2000), ("run", 3000)], params=PUMPING_ARMS, part="wrist", lift=0.7)
    assert min(v for t, v in s if t >= 3000) > 0.8
    still = scores([("stand", 3000)], params=PUMPING_ARMS, part="wrist", jitter_px=4.0)
    assert max(v for _, v in still) < 0.4


# ---------------------------------------------------------------- through the engine


def test_run_then_stop_gives_one_down_and_one_up_with_bounded_latency():
    engine, backend = make_engine()
    results = engine.run(motion_stream([("stand", 2000), ("run", 4000), ("stand", 2000)]))
    assert backend.calls == [("down", "w"), ("up", "w")]
    (start,) = event_times(results, EventKind.START)
    (end,) = event_times(results, EventKind.END)
    start_latency = start - 2000
    stop_latency = end - 6000
    # See the module docstring of sww.gestures.alternating for why these are > 100 ms.
    assert 150 <= start_latency <= 700, start_latency
    assert 0 <= stop_latency <= 800, stop_latency


def test_noisy_running_does_not_flicker():
    engine, backend = make_engine()
    stream = motion_stream(
        [("stand", 2000), ("run", 8000), ("stand", 2000)], jitter_px=4.0, seed=11, freq_hz=1.8
    )
    engine.run(stream)
    assert backend.calls == [("down", "w"), ("up", "w")]


@pytest.mark.parametrize("frame_ms", [50, 64])  # 20 fps; 15 fps as in the real recordings
@pytest.mark.parametrize("freq_hz", [1.33, 2.0])
def test_slow_frame_rate_still_works(frame_ms, freq_hz):
    engine, backend = make_engine()
    segments = [("stand", 2000), ("run", 6000), ("stand", 2000)]
    engine.run(motion_stream(segments, frame_ms=frame_ms, freq_hz=freq_hz, jitter_px=2.0))
    assert backend.calls == [("down", "w"), ("up", "w")]


def test_running_out_of_view_releases_quickly():
    engine, backend = make_engine()
    results = engine.run(motion_stream([("stand", 1000), ("run", 3000), (None, 1000)]))
    assert backend.calls == [("down", "w"), ("up", "w")]
    (end,) = event_times(results, EventKind.END)
    first_missing = next(r.timestamp_ms for r in results if r.features is None)
    # Released by the tracking-loss rule (150 ms), not the slower running window.
    assert end - first_missing <= 150 + FRAME_MS
