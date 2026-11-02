"""Smoke-test the `sww run` loop with a fake camera and fake tracker (no webcam, no model)."""

import numpy as np
from synthetic import make_frame

import sww.capture
import sww.tracking
from sww.capture import CapturedFrame
from sww.cli import main
from sww.engine import StepResult
from sww.preview import render


class FakeCamera:
    """Delivers N blank frames, then simulates Ctrl+C."""

    def __init__(self, *args, n_frames: int = 40, **kwargs):
        self.n = n_frames
        self.actual_size = (1280, 720)
        self.actual_fps = 30.0
        self.actual_fourcc = "MJPG"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def read_latest(self, after_seq=0, timeout_s=1.0):
        seq = after_seq + 1
        if seq > self.n:
            raise KeyboardInterrupt
        return CapturedFrame(np.zeros((720, 1280, 3), np.uint8), timestamp_ms=seq * 33, seq=seq)


class FakeTracker:
    """Hand on head for frames 10-29, arms down otherwise."""

    def __init__(self, model_path, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def process(self, image, timestamp_ms):
        seq = timestamp_ms // 33
        return make_frame(timestamp_ms, right="on_head" if 10 <= seq < 30 else None)


def test_run_loop_dry_run_taps_once(monkeypatch, capsys):
    monkeypatch.setattr(sww.capture, "LatestFrameCamera", FakeCamera)
    monkeypatch.setattr(sww.tracking, "PoseTracker", FakeTracker)
    assert main(["run", "--no-preview", "--no-pause-hotkey", "--stats-every", "0.5"]) == 0
    out = capsys.readouterr().out
    assert out.count("[dry run] TAP 'b'") == 1
    assert "[perf" in out


def test_render_draws_without_display():
    frame = make_frame(right="on_head")
    image = np.zeros((720, 1280, 3), np.uint8)
    step = StepResult(timestamp_ms=0, features=None)
    out = render(image, frame, step, ["status"], mirror=True, debug=True)
    assert out.shape == image.shape
    assert out.any()  # something was drawn
    assert not image.any()  # input untouched


def test_fourcc_decoding():
    from sww.capture import fourcc_to_str

    assert fourcc_to_str(1196444237.0) == "MJPG"
    assert fourcc_to_str(844715353.0) == "YUY2"
    assert fourcc_to_str(0.0) == "?"


def test_bench_model_only_reports_missing_models(tmp_path, capsys):
    assert main(["bench", "--skip-camera", "--models-dir", str(tmp_path)]) == 1
    assert "not downloaded" in capsys.readouterr().out


class FakeRunningTracker(FakeTracker):
    """Stands for 1 s, runs in place for 3 s, then stands (legs visible)."""

    def __init__(self, model_path, **kwargs):
        from synthetic import motion_stream

        stream = motion_stream([("stand", 1000), ("run", 3000), ("stand", 2000)])
        self._frames = {t: f for f, t in stream}

    def process(self, image, timestamp_ms):
        return self._frames.get(timestamp_ms)


def test_run_loop_holds_w_while_running_and_releases(monkeypatch, capsys):
    monkeypatch.setattr(sww.capture, "LatestFrameCamera", lambda *a, **k: FakeCamera(n_frames=180))
    monkeypatch.setattr(sww.tracking, "PoseTracker", FakeRunningTracker)
    assert main(["run", "--no-preview", "--no-pause-hotkey", "--stats-every", "60"]) == 0
    out = capsys.readouterr().out
    assert out.count("[dry run] DOWN 'w'") == 1
    assert out.count("[dry run] UP 'w'") == 1
    assert "RELEASE" not in out  # ended normally, nothing left to release at exit


def test_run_refuses_send_without_pause_hotkey(capsys):
    assert main(["run", "--send", "--no-pause-hotkey", "--no-preview"]) == 2
    assert "kill switch" in capsys.readouterr().err


def test_record_saves_landmarks(monkeypatch, tmp_path, capsys):
    from sww.recording import Recording

    monkeypatch.setattr(sww.capture, "LatestFrameCamera", lambda *a, **k: FakeCamera(n_frames=500))
    monkeypatch.setattr(sww.tracking, "PoseTracker", FakeTracker)
    # Fake clock: the countdown and duration are measured against frame timestamps.
    monkeypatch.setattr(sww.capture, "now_ms", lambda: 0)
    out = tmp_path / "r.npz"
    args = ["record", "--no-preview", "--countdown", "1", "--seconds", "2", "--out", str(out)]
    assert main([*args, "--label", "idle"]) == 0
    rec = Recording.load(out)
    assert rec.meta["label"] == "idle"
    assert rec.timestamps_ms[0] >= 1000 and rec.timestamps_ms[-1] < 3000
    assert 55 <= len(rec) <= 62
    assert "Saved" in capsys.readouterr().out
