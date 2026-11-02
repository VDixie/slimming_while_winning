"""Running in place (arm swing AND body bounce) and the generic oscillation rule."""

import numpy as np
import pytest
from synthetic import FRAME_MS, make_frame, motion_stream

from sww.actions import ActionMapper, Mapping, Mode
from sww.engine import Engine
from sww.features import to_body_frame
from sww.gestures import (
    ARM_SWING,
    BOUNCE,
    OscillationParams,
    RunningInPlace,
    oscillation,
    pumping_arms,
    shoulder_height_px,
)
from sww.gestures.oscillation import median3
from sww.landmarks import Pose
from sww.output import RecordingBackend
from sww.state import DebounceConfig, EventKind
from sww.window import FeatureWindow

RUN = "running_in_place"


def scores(segments, detector=None, **kwargs) -> list[tuple[int, float | None, dict]]:
    """(t, score, details) for every frame of a motion stream."""
    det = detector or RunningInPlace()
    win = FeatureWindow()
    out = []
    for frame, t in motion_stream(segments, **kwargs):
        win.push(t, to_body_frame(frame) if frame is not None else None)
        ev = det.evaluate(win)
        out.append((t, ev.score, ev.details))
    return out


def max_score(segments, **kwargs) -> float:
    return max(s or 0.0 for _, s, _ in scores(segments, **kwargs))


def make_engine(detector=None):
    backend = RecordingBackend()
    det = detector or RunningInPlace()
    mapper = ActionMapper([Mapping(det.name, "w", Mode.HOLD)], backend)
    engine = Engine([det], mapper, {det.name: DebounceConfig(min_on_ms=50, min_off_ms=200)})
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
        OscillationParams(0.1, 0.2, 0.1, 0.2, swing_ms=200)


def test_shoulder_height_goes_up_when_body_rises():
    low = to_body_frame(make_frame(rise=0.0))
    high = to_body_frame(make_frame(rise=0.1))
    rise_px = shoulder_height_px(high) - shoulder_height_px(low)
    assert rise_px == pytest.approx(0.1 * low.shoulder_width_px, abs=1e-3)


def test_bounce_ignores_shoulder_width_jitter():
    # Regression: dividing each frame by its own shoulder width turned width
    # jitter into fake bounce (worse the further the shoulders are from the
    # image top). Here only the width jitters; the shoulder line doesn't move.
    win = FeatureWindow()
    rng = np.random.default_rng(1)
    for i in range(90):
        frame = make_frame(i * FRAME_MS)
        dx = rng.normal(0, 1.5) / 1280  # shoulders move sideways only
        frame.landmarks[Pose.LEFT_SHOULDER, 0] += dx
        frame.landmarks[Pose.RIGHT_SHOULDER, 0] -= dx
        win.push(i * FRAME_MS, to_body_frame(frame))
    ev = oscillation(win, shoulder_height_px, BOUNCE)
    assert ev.details["range"] < 0.005 and ev.score == 0.0


def test_landmarks_outside_the_image_count_as_not_visible():
    # Real bug from the first recordings: MediaPipe guessed knees below the image
    # with visibility ~0.7. The synthetic knees also lie below the 720p image.
    frame = make_frame()
    frame.landmarks[Pose.LEFT_KNEE, 3] = 0.9
    f = to_body_frame(frame)
    assert not f.visible(Pose.LEFT_KNEE)
    assert f.visible(Pose.LEFT_WRIST)


def test_oscillation_none_without_person_and_zero_when_signal_missing():
    assert oscillation(FeatureWindow.of(None), shoulder_height_px, BOUNCE).score is None
    win = FeatureWindow.of(to_body_frame(make_frame()))
    ev = oscillation(win, lambda f: None, ARM_SWING)
    assert ev.score == 0.0 and ev.details == {"visible": 0.0}


# ---------------------------------------------------------------- running scores


def test_standing_still_scores_zero():
    assert max_score([("stand", 3000)]) == 0.0


@pytest.mark.parametrize("freq_hz", [1.1, 1.33, 2.0, 3.0])
def test_running_scores_high_after_one_cycle(freq_hz):
    s = scores([("stand", 2000), ("run", 4000)], freq_hz=freq_hz)
    running = [v for t, v, _ in s if t >= 2000 + 1000 / freq_hz + 200]
    assert min(running) > 0.8


def test_both_terms_reported():
    *_, (_, score, details) = scores([("stand", 1000), ("run", 3000)])
    assert details["arms.score"] > 0.8 and details["bounce.score"] > 0.8
    assert score == min(details["arms.score"], details["bounce.score"])


def test_scale_invariant():
    near = scores([("stand", 1000), ("run", 2000)], scale=1.0)
    far = scores([("stand", 1000), ("run", 2000)], scale=0.5)
    np.testing.assert_allclose([v for _, v, _ in near], [v for _, v, _ in far], atol=1e-3)


def test_jitter_while_standing_stays_low():
    assert max_score([("stand", 6000)], jitter_px=2.0, seed=3) < 0.4


@pytest.mark.parametrize(
    "activity",
    [
        "arms",  # gesturing / pumping arms without bouncing
        "bounce",  # bobbing / shifting weight without arm swing
        "raise_left",  # one hand up and held
        "crouch",  # body down and held
    ],
)
def test_one_part_of_running_alone_is_not_running(activity):
    assert max_score([("stand", 2000), (activity, 3000), ("stand", 2000)], jitter_px=1.0) < 0.4


def test_hidden_wrist_scores_zero():
    s = scores([("run", 3000)], hidden=(Pose.LEFT_WRIST,))
    assert {v for _, v, _ in s} == {0.0}


def test_no_person_gives_none():
    assert RunningInPlace().evaluate(FeatureWindow.of(None)).score is None


def test_pumping_arms_needs_no_bounce():
    det = pumping_arms()
    assert max_score([("stand", 2000), ("arms", 3000)], detector=det) > 0.8
    assert max_score([("stand", 3000)], detector=det, jitter_px=2.0) < 0.4


# ---------------------------------------------------------------- through the engine


def test_run_then_stop_gives_one_down_and_one_up_with_bounded_latency():
    engine, backend = make_engine()
    results = engine.run(motion_stream([("stand", 2000), ("run", 5000), ("stand", 2000)]))
    assert backend.calls == [("down", "w"), ("up", "w")]
    (start,) = event_times(results, EventKind.START)
    (end,) = event_times(results, EventKind.END)
    # See sww.gestures.oscillation for why these are > 100 ms.
    assert 150 <= start - 2000 <= 800, start - 2000
    assert 0 <= end - 7000 <= 800, end - 7000


def test_noisy_running_does_not_flicker():
    engine, backend = make_engine()
    stream = motion_stream(
        [("stand", 2000), ("run", 8000), ("stand", 2000)], jitter_px=2.0, seed=11
    )
    engine.run(stream)
    assert backend.calls == [("down", "w"), ("up", "w")]


@pytest.mark.parametrize("frame_ms", [50, 64])  # 20 fps; 15 fps as in the real recordings
@pytest.mark.parametrize("freq_hz", [1.33, 2.0])
def test_slow_frame_rate_still_works(frame_ms, freq_hz):
    engine, backend = make_engine()
    segments = [("stand", 2000), ("run", 6000), ("stand", 2000)]
    engine.run(motion_stream(segments, frame_ms=frame_ms, freq_hz=freq_hz, jitter_px=1.0))
    assert backend.calls == [("down", "w"), ("up", "w")]


def test_running_out_of_view_releases_quickly():
    engine, backend = make_engine()
    results = engine.run(motion_stream([("stand", 1000), ("run", 3000), (None, 1000)]))
    assert backend.calls == [("down", "w"), ("up", "w")]
    (end,) = event_times(results, EventKind.END)
    first_missing = next(r.timestamp_ms for r in results if r.features is None)
    # Released by the tracking-loss rule (150 ms), not the slower running window.
    assert end - first_missing <= 150 + FRAME_MS
