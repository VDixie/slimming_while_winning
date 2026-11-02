import numpy as np
import pytest
from synthetic import make_frame

from sww.features import to_body_frame
from sww.gestures import HandOnHead
from sww.gestures.base import falling, rising
from sww.landmarks import Pose
from sww.window import FeatureWindow


def score(**kwargs) -> float | None:
    frame = to_body_frame(make_frame(**kwargs))
    return HandOnHead().evaluate(FeatureWindow.of(frame)).score


def test_ramps():
    assert rising(0.0, 0.1, 0.3) == 0.0
    assert rising(0.2, 0.1, 0.3) == pytest.approx(0.5)
    assert rising(1.0, 0.1, 0.3) == 1.0
    assert falling(0.2, 0.1, 0.3) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        rising(0.0, 0.3, 0.1)


def test_neutral_pose_scores_zero():
    assert score() == 0.0


@pytest.mark.parametrize("side", ["left", "right"])
def test_either_hand_on_head_scores_high(side):
    assert score(**{side: "on_head"}) == pytest.approx(1.0)


@pytest.mark.parametrize("scale", [0.5, 0.75, 1.0, 1.2])
def test_score_independent_of_distance(scale):
    assert score(right="on_head", scale=scale) == pytest.approx(1.0)


def test_arm_raised_overhead_is_not_hand_on_head():
    assert score(right="overhead") < 0.4
    assert score(left="overhead", right="overhead") < 0.4


def test_hand_on_chin_is_not_hand_on_head():
    assert score(right="chin") == 0.0


def test_hidden_hand_scores_zero():
    hidden = (Pose.RIGHT_WRIST, Pose.RIGHT_INDEX, Pose.RIGHT_PINKY)
    assert score(right="on_head", hidden=hidden) == 0.0


def test_falls_back_to_ears_when_nose_hidden():
    assert score(right="on_head", hidden=(Pose.NOSE,)) == pytest.approx(1.0, abs=0.05)


def test_no_head_scores_zero():
    hidden = (Pose.NOSE, Pose.LEFT_EAR, Pose.RIGHT_EAR)
    assert score(right="on_head", hidden=hidden) == 0.0


def test_no_person_gives_none():
    assert HandOnHead().evaluate(FeatureWindow.of(None)).score is None


def test_robust_to_landmark_jitter():
    rng = np.random.default_rng(42)
    on = [score(right="on_head", jitter_px=4.0, rng=rng) for _ in range(50)]
    off = [score(jitter_px=4.0, rng=rng) for _ in range(50)]
    assert min(on) > 0.6  # above the default enter threshold
    assert max(off) < 0.4  # below the default exit threshold


def test_details_expose_tuning_values():
    ev = HandOnHead().evaluate(FeatureWindow.of(to_body_frame(make_frame(right="on_head"))))
    assert {"right.dy", "right.dx", "right.elbow_deg", "right.score"} <= ev.details.keys()
