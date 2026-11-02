"""Ground-truth labels: parsing, segments, comparison, and the replay CLI."""

import csv
import json

import pytest
from synthetic import IMAGE_SIZE, motion_stream

from sww.cli import main
from sww.labels import (
    Interval,
    Segment,
    active_segments,
    compare,
    frame_labels,
    labels_path,
    load_labels,
    parse_labels,
)
from sww.recording import Recording


def test_labels_path_sits_next_to_recording(tmp_path):
    assert labels_path(tmp_path / "running_1.npz") == tmp_path / "running_1.labels.json"


def test_parse_sorts_and_allows_open_end_and_empty():
    labels = parse_labels({"running": [[13.8, None], [2, 9.4]], "jump": []})
    assert labels["running"] == [Interval(2.0, 9.4), Interval(13.8, None)]
    assert labels["jump"] == []


@pytest.mark.parametrize(
    "bad",
    [
        [1, 2],
        {"running": [[1]]},
        {"running": [[5, 3]]},
        {"running": [[1, 5], [4, 6]]},
        {"running": [[1, None], [4, 6]]},
        {"running": "1-2"},
    ],
)
def test_parse_rejects_bad_labels(bad):
    with pytest.raises(ValueError):
        parse_labels(bad)


def test_load_labels_missing_file_is_none(tmp_path):
    assert load_labels(tmp_path / "x.npz") is None


def test_active_segments_and_frame_labels():
    times = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    assert active_segments(times, [0, 1, 1, 0, 1, 1]) == [Segment(0.5, 1.5), Segment(2.0, None)]
    assert frame_labels([Interval(0.5, 1.5)], times) == [False, True, True, False, False, False]


def test_compare_good_detection_reports_delays():
    c = compare(
        [Interval(2.0, 9.4), Interval(13.8, None)], [Segment(3.0, 9.6), Segment(14.6, None)]
    )
    assert c.ok, c.problems()
    assert c.intervals[0].start_delay_s == pytest.approx(1.0)
    assert c.intervals[0].stop_delay_s == pytest.approx(0.2)
    assert c.intervals[1].stop_delay_s is None


def test_compare_finds_flicker_misses_slow_starts_and_false_positives():
    c = compare(
        [Interval(4.0, 13.4), Interval(20.0, 25.0), Interval(30.0, 35.0)],
        [Segment(4.9, 5.5), Segment(6.1, 13.6), Segment(16.0, 16.5), Segment(32.0, 35.2)],
    )
    problems = " | ".join(c.problems())
    assert "flicker" in problems
    assert "[20, 25]: never activated" in problems
    assert "start delay +2.00" in problems
    assert "outside the labels at 16.00" in problems


def test_compare_open_ended_interval_must_stay_on():
    c = compare([Interval(1.0, None)], [Segment(1.5, 8.0)])
    assert any("before the end" in p for p in c.problems())


def test_replay_uses_labels_file(tmp_path, capsys):
    stream = motion_stream([("stand", 2000), ("run", 5000), ("stand", 2000)])
    path = Recording.from_frames(stream, IMAGE_SIZE, {"label": "running"}).save(tmp_path / "r.npz")
    labels_path(path).write_text(json.dumps({"running": [[2.0, 7.0]]}), encoding="utf-8")
    assert main(["replay", str(path), "--csv"]) == 0
    out = capsys.readouterr().out
    assert "Labels check: running_in_place" in out and "  OK" in out
    with (tmp_path / "r.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["label.running"] == "0"
    assert any(r["label.running"] == "1" for r in rows)
