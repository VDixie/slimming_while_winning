"""Draw the live preview: skeleton, gesture scores, status text and debug graphs."""

from __future__ import annotations

from collections import deque

import cv2
import numpy as np

from sww.engine import StepResult
from sww.landmarks import POSE_CONNECTIONS, PoseFrame

_GREEN = (80, 220, 80)
_GREY = (160, 160, 160)
_WHITE = (255, 255, 255)
_ORANGE = (0, 165, 255)
_BLACK = (0, 0, 0)


def _text(img: np.ndarray, text: str, org: tuple[int, int], color=_WHITE, scale=0.55) -> None:
    # Black outline first so text is readable on any background.
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, _BLACK, 3, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def draw_skeleton(img: np.ndarray, frame: PoseFrame, min_visibility: float = 0.5) -> None:
    """Draw pose landmarks onto ``img`` in place (unmirrored image coordinates)."""
    pts = frame.pixels().astype(int)
    vis = frame.visibility
    for a, b in POSE_CONNECTIONS:
        if vis[a] >= min_visibility and vis[b] >= min_visibility:
            cv2.line(img, tuple(pts[a]), tuple(pts[b]), _GREEN, 2, cv2.LINE_AA)
    for i, (x, y) in enumerate(pts):
        color = _GREEN if vis[i] >= min_visibility else _GREY
        cv2.circle(img, (int(x), int(y)), 3, color, -1, cv2.LINE_AA)


class History:
    """Last ``length`` frames of each gesture's score and, if present, its ``signal`` detail.

    Feeds the rolling graphs drawn with ``--debug`` (about 5 s at 30 fps).
    """

    def __init__(self, length: int = 150):
        self.length = length
        self.series: dict[str, deque[float | None]] = {}

    def _add(self, key: str, value: float | None) -> None:
        self.series.setdefault(key, deque(maxlen=self.length)).append(value)

    def update(self, step: StepResult) -> None:
        for name, ev in step.evaluations.items():
            self._add(f"{name} score", ev.score)
            if "signal" in ev.details or f"{name} signal" in self.series:
                self._add(f"{name} signal", ev.details.get("signal"))


def _draw_plot(
    img: np.ndarray, values: deque[float | None], label: str, box: tuple[int, int, int, int]
) -> None:
    """Line plot of ``values`` in ``box`` = (x, y, w, h). Scores use 0..1, other series ±range."""
    x0, y0, w, h = box
    overlay = img[y0 : y0 + h, x0 : x0 + w]
    overlay[:] = (overlay * 0.4).astype(img.dtype)  # darken the background
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), _GREY, 1)
    known = [v for v in values if v is not None]
    if label.endswith("score"):
        lo, hi = 0.0, 1.0
    else:
        span = max(0.5, max((abs(v) for v in known), default=0.0))
        lo, hi = -span, span
        mid = y0 + h // 2
        cv2.line(img, (x0, mid), (x0 + w, mid), _GREY, 1)
    pts = []
    n = max(len(values), 2)
    for i, v in enumerate(values):
        if v is None:
            if len(pts) > 1:
                cv2.polylines(img, [np.array(pts, np.int32)], False, _ORANGE, 1, cv2.LINE_AA)
            pts = []
            continue
        frac = (min(max(v, lo), hi) - lo) / (hi - lo)
        pts.append((x0 + int(i * (w - 1) / (n - 1)), y0 + h - 1 - int(frac * (h - 1))))
    if len(pts) > 1:
        cv2.polylines(img, [np.array(pts, np.int32)], False, _ORANGE, 1, cv2.LINE_AA)
    scale = "" if label.endswith("score") else f" (+/-{hi:.2f})"
    _text(img, label + scale, (x0 + 4, y0 + 14), _WHITE, 0.4)


def render(
    image_bgr: np.ndarray,
    frame: PoseFrame | None,
    step: StepResult,
    status_lines: list[str],
    mirror: bool = True,
    debug: bool = False,
    history: History | None = None,
) -> np.ndarray:
    """Return a new image with the overlay drawn.

    ``mirror`` flips the picture horizontally so it behaves like a mirror,
    which is easier to act in front of. Only the display is flipped; the
    landmarks used for detection are untouched.
    """
    img = image_bgr.copy()
    if frame is not None:
        draw_skeleton(img, frame)
    if mirror:
        img = cv2.flip(img, 1)

    y = 24
    for line in status_lines:
        _text(img, line, (10, y))
        y += 22

    for name, ev in step.evaluations.items():
        active = step.active.get(name, False)
        score = ev.score
        label = f"{name}: {'--' if score is None else f'{score:.2f}'}"
        if active:
            label += "  ACTIVE"
        # Score bar, 200 px = 1.0
        cv2.rectangle(img, (10, y - 12), (210, y + 4), _GREY, 1)
        if score is not None:
            cv2.rectangle(img, (10, y - 12), (10 + int(200 * score), y + 4), _ORANGE, -1)
        _text(img, label, (220, y), _GREEN if active else _WHITE)
        y += 24
        if debug:
            for key, value in sorted(ev.details.items()):
                _text(img, f"  {key} = {value:+.2f}", (10, y), _GREY, 0.45)
                y += 18

    if debug and history is not None:
        # Stack graphs in the bottom-right corner, newest sample on the right.
        w, h, gap = 300, 60, 6
        x0 = img.shape[1] - w - 10
        y0 = img.shape[0] - 10 - h
        for label, values in reversed(list(history.series.items())):
            if y0 < 0:
                break
            _draw_plot(img, values, label, (x0, y0, w, h))
            y0 -= h + gap
    return img


def draw_banner(img: np.ndarray, text: str) -> None:
    """Large text at the bottom of the image (e.g. the last key sent)."""
    _text(img, text, (10, img.shape[0] - 16), _ORANGE, 0.8)
