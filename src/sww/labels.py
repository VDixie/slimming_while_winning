"""Ground-truth labels for recordings: when was an activity *really* being done?

A recording ``recordings/running_20261102-175705.npz`` can have a hand-written
labels file next to it, ``recordings/running_20261102-175705.labels.json``::

    {"running": [[4.0, 13.4]]}

Each key is an activity, each value a list of ``[start, end]`` intervals in
**seconds from the first frame of the recording** (the times ``sww replay``
prints). ``end`` may be ``null``: still going when the recording ended. An
empty list means "never done" (e.g. an idle recording). Labels written by eye
from the replay graphs are good to ~0.2 s, which the tolerances below allow.

Labels are used to:

- check detectors against reality (:func:`compare`): one activation per
  interval, none outside, and how long it took to start and stop;
- add a per-frame ``label.<activity>`` column to the replay CSV, which is the
  training target for a learned model later (roadmap step 4).

Which gestures are checked against which activity: :data:`ACTIVITY_FOR_GESTURE`.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

LABELS_SUFFIX = ".labels.json"

ACTIVITY_FOR_GESTURE: dict[str, str] = {
    "running_in_place": "running",
    "pumping_arms": "running",  # seated variant: arm swing while running counts too
}
"""Gesture (detector name) -> labelled activity it should follow."""

# Allowed delays (seconds). Rhythm detection needs ~0.5 s to start and to stop
# (see sww.gestures.oscillation); the rest is slack for labels set by eye.
MAX_START_DELAY_S = 1.2
MAX_STOP_DELAY_S = 1.0
EARLY_TOLERANCE_S = 0.4
"""How much earlier than the labelled time a start/stop may be (label imprecision)."""


@dataclass(frozen=True, slots=True)
class Interval:
    """One labelled stretch of an activity (seconds from the recording start)."""

    start_s: float
    end_s: float | None = None  # None = until the end of the recording

    def __post_init__(self) -> None:
        if self.end_s is not None and self.end_s <= self.start_s:
            raise ValueError(f"interval end {self.end_s} must be after start {self.start_s}")

    def contains(self, t_s: float) -> bool:
        return t_s >= self.start_s and (self.end_s is None or t_s < self.end_s)


Labels = dict[str, list[Interval]]


def labels_path(recording_path: Path) -> Path:
    """``x.npz`` -> ``x.labels.json`` (same folder)."""
    path = Path(recording_path)
    return path.with_name(path.stem + LABELS_SUFFIX)


def parse_labels(data: object) -> Labels:
    """Validate the JSON structure (see module docstring) and build intervals."""
    if not isinstance(data, dict):
        raise ValueError("labels must be a JSON object: {activity: [[start, end], ...]}")
    labels: Labels = {}
    for activity, raw in data.items():
        if not isinstance(raw, list):
            raise ValueError(f"{activity!r}: expected a list of [start, end] pairs")
        intervals = []
        for pair in raw:
            if not (isinstance(pair, list) and len(pair) == 2):
                raise ValueError(f"{activity!r}: expected [start, end], got {pair!r}")
            start, end = pair
            intervals.append(Interval(float(start), None if end is None else float(end)))
        intervals.sort(key=lambda i: i.start_s)
        for a, b in itertools.pairwise(intervals):
            if a.end_s is None or a.end_s > b.start_s:
                raise ValueError(f"{activity!r}: intervals overlap")
        labels[activity] = intervals
    return labels


def load_labels(recording_path: Path) -> Labels | None:
    """Labels for a recording, or None if it has no labels file."""
    path = labels_path(recording_path)
    if not path.exists():
        return None
    return parse_labels(json.loads(path.read_text(encoding="utf-8")))


def frame_labels(intervals: Sequence[Interval], times_s: Sequence[float]) -> list[bool]:
    """Per frame: is the activity labelled as happening? (training target)"""
    return [any(i.contains(t) for i in intervals) for t in times_s]


# --------------------------------------------------------------------- compare


@dataclass(frozen=True, slots=True)
class Segment:
    """One stretch where a gesture was active (seconds from the recording start)."""

    start_s: float
    end_s: float | None  # None = still active when the recording ended


def active_segments(times_s: Sequence[float], active: Sequence[bool]) -> list[Segment]:
    """Turn per-frame active flags into on/off segments."""
    segments: list[Segment] = []
    on_since: float | None = None
    for t, a in zip(times_s, active, strict=True):
        if a and on_since is None:
            on_since = t
        elif not a and on_since is not None:
            segments.append(Segment(on_since, t))
            on_since = None
    if on_since is not None:
        segments.append(Segment(on_since, None))
    return segments


@dataclass(slots=True)
class IntervalResult:
    """How the detector did on one labelled interval."""

    interval: Interval
    segments: list[Segment] = field(default_factory=list)

    @property
    def start_delay_s(self) -> float | None:
        """First activation minus labelled start (None if never activated)."""
        return self.segments[0].start_s - self.interval.start_s if self.segments else None

    @property
    def stop_delay_s(self) -> float | None:
        """Last deactivation minus labelled end (None if either is open-ended)."""
        if not self.segments or self.interval.end_s is None or self.segments[-1].end_s is None:
            return None
        return self.segments[-1].end_s - self.interval.end_s

    def problems(self) -> list[str]:
        end = "end" if self.interval.end_s is None else f"{self.interval.end_s:g}"
        where = f"[{self.interval.start_s:g}, {end}]"
        if not self.segments:
            return [f"{where}: never activated"]
        out = []
        if len(self.segments) > 1:
            out.append(f"{where}: activated {len(self.segments)} times (flicker)")
        d = self.start_delay_s
        if d is not None and not -EARLY_TOLERANCE_S <= d <= MAX_START_DELAY_S:
            out.append(f"{where}: start delay {d:+.2f} s")
        d = self.stop_delay_s
        if d is not None and not -EARLY_TOLERANCE_S <= d <= MAX_STOP_DELAY_S:
            out.append(f"{where}: stop delay {d:+.2f} s")
        if self.interval.end_s is None and self.segments[-1].end_s is not None:
            out.append(f"{where}: stopped at {self.segments[-1].end_s:.2f} s before the end")
        return out


@dataclass(slots=True)
class Comparison:
    """Detector activity vs labels for one activity."""

    intervals: list[IntervalResult]
    extra: list[Segment]  # activations outside every labelled interval (false positives)

    def problems(self) -> list[str]:
        out = [p for r in self.intervals for p in r.problems()]
        out += [f"active outside the labels at {s.start_s:.2f} s" for s in self.extra]
        return out

    @property
    def ok(self) -> bool:
        return not self.problems()


def compare(intervals: Sequence[Interval], segments: Sequence[Segment]) -> Comparison:
    """Assign each active segment to the labelled interval it overlaps (allowing the
    stop delay after the labelled end); segments overlapping none are false positives."""
    results = [IntervalResult(i) for i in intervals]
    extra: list[Segment] = []
    for seg in segments:
        for r in results:
            i = r.interval
            seg_end = float("inf") if seg.end_s is None else seg.end_s
            lab_end = float("inf") if i.end_s is None else i.end_s + MAX_STOP_DELAY_S
            if seg.start_s < lab_end and seg_end > i.start_s - EARLY_TOLERANCE_S:
                r.segments.append(seg)
                break
        else:
            extra.append(seg)
    return Comparison(results, extra)
