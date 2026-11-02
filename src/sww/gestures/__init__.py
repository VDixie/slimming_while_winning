"""Gesture detectors. All implement :class:`sww.gestures.base.GestureDetector`."""

from sww.gestures.base import Evaluation, GestureDetector
from sww.gestures.hand_on_head import HandOnHead, HandOnHeadParams
from sww.gestures.oscillation import OscillationDetector, OscillationParams, oscillation
from sww.gestures.running import (
    ARM_SWING,
    BOUNCE,
    RunningInPlace,
    arm_swing,
    pumping_arms,
    shoulder_height_px,
)

__all__ = [
    "ARM_SWING",
    "BOUNCE",
    "Evaluation",
    "GestureDetector",
    "HandOnHead",
    "HandOnHeadParams",
    "OscillationDetector",
    "OscillationParams",
    "RunningInPlace",
    "arm_swing",
    "oscillation",
    "pumping_arms",
    "shoulder_height_px",
]
