"""Regression tests on your own landmark recordings, if there are any.

Recordings stay private (``recordings/`` is git-ignored), so these tests are
skipped on a fresh checkout. Make them with ``sww record --label running`` /
``--label idle``. Files are matched by the label stored in the recording.

- ``running``: running in place with natural arm swing the whole time
  (both ``--forward run`` and ``--forward arms`` must hold W through it, with
  exactly one key-down)
- ``idle``: standing or normal play movements without running (no W at all)
"""

from pathlib import Path

import pytest

from sww.actions import ActionMapper, Mapping, Mode
from sww.engine import Engine
from sww.gestures import RunningInPlace, pumping_arms
from sww.output import RecordingBackend
from sww.recording import Recording
from sww.state import DebounceConfig

RECORDINGS = Path(__file__).resolve().parent.parent / "recordings"


def _by_label(label: str) -> list[Path]:
    paths = []
    for path in sorted(RECORDINGS.glob("*.npz")):
        try:
            if Recording.load(path).meta.get("label") == label:
                paths.append(path)
        except (ValueError, OSError, KeyError):
            continue
    return paths


DETECTORS = {"run": RunningInPlace, "arms": pumping_arms}


def _replay(path: Path, mode: str) -> list[tuple[str, str]]:
    backend = RecordingBackend()
    det = DETECTORS[mode]()
    mapper = ActionMapper([Mapping(det.name, "w", Mode.HOLD)], backend)
    engine = Engine([det], mapper, {det.name: DebounceConfig(min_on_ms=50, min_off_ms=200)})
    engine.run(Recording.load(path).frames())
    return backend.calls


def _params(label):
    paths = _by_label(label)
    return paths or [pytest.param(None, marks=pytest.mark.skip(f"no '{label}' recordings"))]


@pytest.mark.parametrize("mode", list(DETECTORS))
@pytest.mark.parametrize("path", _params("running"), ids=lambda p: getattr(p, "stem", "none"))
def test_running_recording_holds_w_once(path, mode):
    calls = _replay(path, mode)
    assert calls[:1] == [("down", "w")]
    assert calls.count(("down", "w")) == 1


@pytest.mark.parametrize("mode", list(DETECTORS))
@pytest.mark.parametrize("path", _params("idle"), ids=lambda p: getattr(p, "stem", "none"))
def test_idle_recording_never_presses_w(path, mode):
    assert _replay(path, mode) == []
