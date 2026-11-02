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
    assert main(["run", "--no-preview", "--stats-every", "0.5"]) == 0
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
