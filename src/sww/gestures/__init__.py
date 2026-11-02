"""Gesture detectors. All implement :class:`sww.gestures.base.GestureDetector`."""

from sww.gestures.base import Evaluation, GestureDetector
from sww.gestures.hand_on_head import HandOnHead, HandOnHeadParams

__all__ = ["Evaluation", "GestureDetector", "HandOnHead", "HandOnHeadParams"]
