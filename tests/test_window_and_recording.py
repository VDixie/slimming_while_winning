"""FeatureWindow, landmark recordings and the record/replay CLI path."""

import csv

import numpy as np
import pytest
from synthetic import IMAGE_SIZE, motion_stream

from sww.cli import main
from sww.features import to_body_frame
from sww.recording import Recording
from sww.window import FeatureWindow

# ---------------------------------------------------------------- window


def test_window_keeps_only_span_ms():
    win = FeatureWindow(span_ms=100)
    for t in range(0, 300, 10):
        win.push(t, None)
    times = [t for t, _ in win]
    assert times[0] == 190 and times[-1] == 290
    assert [t for t, _ in win.since(30)] == [260, 270, 280, 290]


def test_window_latest_and_none_entries():
    win = FeatureWindow()
    assert win.latest is None and win.latest_ms is None and win.since(100) == []
    (frame, t), *_ = motion_stream([("stand", 33)])
    f = to_body_frame(frame)
    win.push(t, f)
    win.push(t + 33, None)
    assert win.latest is None and win.latest_ms == t + 33 and len(win) == 2


def test_window_rejects_time_going_backwards():
    win = FeatureWindow()
    win.push(10, None)
    with pytest.raises(ValueError):
        win.push(5, None)


# ---------------------------------------------------------------- recordings


def sample_recording() -> Recording:
    stream = motion_stream([("stand", 1500), ("run", 3000), (None, 300), ("stand", 1500)])
    return Recording.from_frames(stream, IMAGE_SIZE, {"label": "test"})


def test_recording_roundtrip(tmp_path):
    rec = sample_recording()
    path = rec.save(tmp_path / "sub" / "r.npz")
    loaded = Recording.load(path)
    assert loaded.meta["label"] == "test" and loaded.meta["format_version"] == 1
    assert loaded.image_size == IMAGE_SIZE
    np.testing.assert_array_equal(loaded.timestamps_ms, rec.timestamps_ms)
    np.testing.assert_array_equal(loaded.person_present, rec.person_present)
    assert not loaded.person_present.all() and loaded.person_present.any()
    for (a, ta), (b, tb) in zip(rec.frames(), loaded.frames(), strict=True):
        assert ta == tb and (a is None) == (b is None)
        if a is not None:
            np.testing.assert_array_equal(a.landmarks, b.landmarks)


def test_recording_validates_shapes():
    with pytest.raises(ValueError):
        Recording(np.arange(3), np.zeros((2, 33, 4), np.float32), IMAGE_SIZE)


def test_replay_cli_reports_hold_and_writes_csv(tmp_path, capsys):
    path = sample_recording().save(tmp_path / "run.npz")
    out_csv = tmp_path / "scores.csv"
    assert main(["replay", str(path), "--csv", str(out_csv)]) == 0
    out = capsys.readouterr().out
    assert out.count("DOWN 'w'") == 1
    assert out.count("UP 'w'") == 1  # released by tracking loss in the gap
    assert "running_in_place" in out and "starts" in out
    with out_csv.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(sample_recording())
    assert {"t_ms", "person", "running_in_place.score", "running_in_place.active"} <= set(rows[0])
    assert any(r["running_in_place.active"] == "1" for r in rows)


def test_replay_with_forward_off(tmp_path, capsys):
    path = sample_recording().save(tmp_path / "run.npz")
    assert main(["replay", str(path), "--forward", "off"]) == 0
    assert "DOWN" not in capsys.readouterr().out
