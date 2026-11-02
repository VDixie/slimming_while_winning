"""Webcam capture on a background thread, keeping only the newest frame.

Why a thread: ``cv2.VideoCapture.read()`` blocks until the camera delivers the
next frame (~33 ms at 30 fps). Reading on a separate thread lets the main loop
spend that time on tracking instead of waiting.

Why "latest frame only": if tracking ever runs slower than the camera, a queue
would fill up and every keypress would be based on an increasingly old image.
Overwriting a single slot means we drop frames instead of adding latency.
That's the right trade-off for a game controller.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

CAPTURE_APIS: dict[str, int] = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}


def fourcc_to_str(code: float) -> str:
    """Decode OpenCV's numeric FOURCC (e.g. 1196444237.0) into text like "MJPG"."""
    n = int(code)
    chars = [chr((n >> (8 * i)) & 0xFF) for i in range(4)]
    return "".join(chars) if all(c.isprintable() for c in chars) and n else "?"


def now_ms() -> int:
    """Monotonic clock in integer milliseconds (never goes backwards)."""
    return time.monotonic_ns() // 1_000_000


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """One BGR image (OpenCV's channel order) plus when it was read."""

    image: np.ndarray
    timestamp_ms: int
    seq: int


class LatestFrameCamera:
    """Open a webcam and continuously grab frames on a daemon thread.

    Args:
        index: Camera index (0 = first webcam).
        width, height, fps: Requested mode. The driver may pick the nearest
            supported one; check :attr:`actual_size` / :attr:`actual_fps`.
        api: Windows capture backend, "dshow" (DirectShow) or "msmf" (Media
            Foundation). They negotiate camera modes differently, so one may
            reach 30 fps where the other doesn't.
        mjpg: Ask for MJPG (compressed) frames. Over USB 2.0, uncompressed
            YUY2 at 1280x720 is often limited to 5-10 fps; MJPG allows 30.
    """

    def __init__(
        self,
        index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        api: str = "dshow",
        mjpg: bool = True,
    ):
        if api not in CAPTURE_APIS:
            raise ValueError(f"api must be one of {sorted(CAPTURE_APIS)}")
        self.index = index
        self.requested = (width, height, fps)
        self.api = api
        self.mjpg = mjpg
        self.actual_fourcc: str = ""
        self._cap: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._cond = threading.Condition()
        self._latest: CapturedFrame | None = None
        self._running = False
        self._error: str | None = None
        self.actual_size: tuple[int, int] = (0, 0)
        self.actual_fps: float = 0.0

    def start(self) -> None:
        """Open the camera and start the reader thread."""
        api = CAPTURE_APIS[self.api] if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.index, api)
        if not cap.isOpened():
            raise RuntimeError(f"could not open camera {self.index} with {self.api}")
        width, height, fps = self.requested
        mjpg = cv2.VideoWriter_fourcc(*"MJPG")
        # Some drivers only honour FOURCC if it's set before the size, others
        # only after; setting it both times is the usual workaround.
        if self.mjpg:
            cap.set(cv2.CAP_PROP_FOURCC, mjpg)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        if self.mjpg:
            cap.set(cv2.CAP_PROP_FOURCC, mjpg)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # ask the driver not to queue old frames
        self.actual_fourcc = fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))
        self.actual_size = (
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        self.actual_fps = float(cap.get(cv2.CAP_PROP_FPS))
        self._cap = cap
        self._running = True
        self._thread = threading.Thread(target=self._reader, name="camera", daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        assert self._cap is not None
        seq = 0
        while self._running:
            ok, image = self._cap.read()
            if not ok:
                with self._cond:
                    self._error = "camera read failed (unplugged or in use by another app?)"
                    self._cond.notify_all()
                time.sleep(0.05)
                continue
            seq += 1
            frame = CapturedFrame(image=image, timestamp_ms=now_ms(), seq=seq)
            with self._cond:
                self._latest = frame
                self._error = None
                self._cond.notify_all()

    def read_latest(self, after_seq: int = 0, timeout_s: float = 1.0) -> CapturedFrame | None:
        """Block until a frame newer than ``after_seq`` exists; return it.

        Returns None on timeout. Raises RuntimeError if the camera is failing.
        """
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while self._latest is None or self._latest.seq <= after_seq:
                if self._error:
                    raise RuntimeError(self._error)
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self._cond.wait(remaining):
                    return None
            return self._latest

    def stop(self) -> None:
        """Stop the thread and release the camera."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()
        self._cap = None
        self._thread = None

    def __enter__(self) -> LatestFrameCamera:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
