"""Regression tests on your own landmark recordings, if there are any.

Recordings stay private (``recordings/`` is git-ignored), so these tests are
skipped on a fresh checkout. Make them with ``sww record --label running`` /
``--label idle``.

What each recording must do is decided by, in order:

1. its labels file ``<name>.labels.json`` (see :mod:`sww.labels`), e.g.
   ``{"running": [[4.0, 13.4]]}``: W held once per labelled run (started
   within ~1 s, released within ~1 s of stopping), never outside;
2. otherwise the label stored in the recording: ``running`` = running in place
   the whole time (one key-down, held to the end); ``idle`` = never running.

Both ``--forward run`` and ``--forward arms`` are checked.
"""

from pathlib import Path

import pytest

from sww.actions import ActionMapper, Mapping, Mode
from sww.engine import Engine
from sww.gestures import RunningInPlace, pumping_arms
from sww.labels import ACTIVITY_FOR_GESTURE, Interval, active_segments, compare, load_labels
from sww.output import RecordingBackend
from sww.recording import Recording
from sww.state import DebounceConfig

RECORDINGS = Path(__file__).resolve().parent.parent / "recordings"
DETECTORS = {"run": RunningInPlace, "arms": pumping_arms}


def _expected(path: Path, rec: Recording, activity: str) -> list[Interval] | None:
    labels = load_labels(path)
    if labels is not None:
        return labels.get(activity, [])
    label = rec.meta.get("label")
    if label == activity:
        return [Interval(0.0, None)]
    if label == "idle":
        return []
    return None  # unknown label, no labels file: nothing to check


def _cases() -> list:
    cases = []
    for path in sorted(RECORDINGS.glob("*.npz")):
        try:
            rec = Recording.load(path)
        except (ValueError, OSError, KeyError):
            continue
        if _expected(path, rec, "running") is not None:
            cases += [pytest.param(path, mode, id=f"{path.stem}-{mode}") for mode in DETECTORS]
    return cases or [pytest.param(None, None, marks=pytest.mark.skip("no recordings"))]


@pytest.mark.parametrize(("path", "mode"), _cases())
def test_recording_matches_labels(path, mode):
    rec = Recording.load(path)
    det = DETECTORS[mode]()
    expected = _expected(path, rec, ACTIVITY_FOR_GESTURE[det.name])
    backend = RecordingBackend()
    mapper = ActionMapper([Mapping(det.name, "w", Mode.HOLD)], backend)
    engine = Engine([det], mapper, {det.name: DebounceConfig(min_on_ms=50, min_off_ms=200)})
    results = engine.run(rec.frames())

    t0 = int(rec.timestamps_ms[0])
    times = [(r.timestamp_ms - t0) / 1000 for r in results]
    segments = active_segments(times, [r.active.get(det.name, False) for r in results])
    comparison = compare(expected, segments)
    assert comparison.ok, comparison.problems()
    # One key-down per activation: no presses beyond what the labels allow.
    assert backend.calls.count(("down", "w")) == len(expected)
