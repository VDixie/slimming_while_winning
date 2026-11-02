"""Gesture detectors. All implement :class:`sww.gestures.base.GestureDetector`."""

from sww.gestures.alternating import (
    PUMPING_ARMS,
    RUNNING_IN_PLACE,
    AlternatingMotion,
    AlternatingParams,
)
from sww.gestures.base import Evaluation, GestureDetector
from sww.gestures.hand_on_head import HandOnHead, HandOnHeadParams

__all__ = [
    "PUMPING_ARMS",
    "RUNNING_IN_PLACE",
    "AlternatingMotion",
    "AlternatingParams",
    "Evaluation",
    "GestureDetector",
    "HandOnHead",
    "HandOnHeadParams",
]
